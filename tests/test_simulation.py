"""Comparação byte a byte da saída do simulador com a saída do Java original."""

from __future__ import annotations

import io
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from lpc_sim import MAIN2_CONFIG, MAIN_CONFIG, CorrectionModel, LoopType, LpcSimulationSystem, SweepConfig, run_sweep
from lpc_sim.cli import main as cli_main


def _run(config: SweepConfig, **kwargs: object) -> str:
    buffer = io.StringIO()
    run_sweep(config, LpcSimulationSystem(output=buffer, **kwargs))  # type: ignore[arg-type]
    return buffer.getvalue()


def _counts_only(text: str) -> list[str]:
    return [line for line in text.splitlines() if not line[:1].isdigit()]


def test_main_preset_matches_java(golden: Path) -> None:
    config = SweepConfig(MAIN_CONFIG.correction_models, MAIN_CONFIG.loop_types, max_errors=3, max_iterations=7)
    assert _run(config) == (golden / "java_main_e3_i7.txt").read_text()


def test_main2_preset_matches_java(golden: Path) -> None:
    config = SweepConfig(MAIN2_CONFIG.correction_models, MAIN2_CONFIG.loop_types, max_errors=2, max_iterations=3)
    assert _run(config) == (golden / "java_main2_e2_i3.txt").read_text()


def test_error_interval_quirk_matches_java(golden: Path) -> None:
    """Com intervalo (10, 40) o progresso não chega a 100%, como no Java."""
    config = SweepConfig((CorrectionModel.DCOC,), (LoopType.INVERT_LOOP,), 2, 2, error_interval=(10, 40))
    assert _run(config) == (golden / "java_main_interval_10_40_e2_i2.txt").read_text()


@pytest.mark.slow
def test_main2_three_errors_matches_java(golden: Path) -> None:
    config = SweepConfig(MAIN2_CONFIG.correction_models, MAIN2_CONFIG.loop_types, max_errors=3, max_iterations=3)
    assert _run(config) == (golden / "java_main2_e3_i3.txt").read_text()


@pytest.mark.slow
def test_parallel_counts_match_sequential() -> None:
    config = SweepConfig((CorrectionModel.DRCC,), (LoopType.PRIORITY_LOOP,), max_errors=4, max_iterations=0)
    sequential = _run(config)
    with ProcessPoolExecutor(max_workers=2) as executor:
        parallel = _run(config, executor=executor)
    assert _counts_only(parallel) == _counts_only(sequential)


def test_cli_quick_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["--max-errors", "1", "--max-iterations", "0"]) == 0
    out = capsys.readouterr().out
    assert "AlgSE0_DCOC (InvertLoop) + AlgDE : #Errors=1" in out
    assert "numberOfDecodigns = 48" in out


def test_cli_csv_output(tmp_path: Path) -> None:
    csv_path = tmp_path / "dados.csv"
    assert cli_main(["--max-errors", "1", "--max-iterations", "0", "--csv", str(csv_path)]) == 0
    rows = csv_path.read_text().splitlines()
    assert rows[0] == (
        "correction_model,loop_type,num_errors,iterations_se,"
        "number_of_decodings,error_se_decoding,error_de_decoding"
    )
    assert rows[1] == "DCOC,InvertLoop,0,0,1,0,0"
    assert rows[2] == "DCOC,InvertLoop,1,0,48,0,0"
