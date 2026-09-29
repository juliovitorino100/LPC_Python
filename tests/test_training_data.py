"""Conjunto de dados de treinamento (uma linha por decodificação)."""

from __future__ import annotations

import csv
import random
from pathlib import Path

import pytest

from lpc_sim import CorrectionModel, LoopType, Lpc, LpcWithError, SweepConfig
from lpc_sim.cli import main as cli_main
from lpc_sim.training_data import (
    LAYOUTS,
    META_COLUMNS,
    count_rows,
    header,
    rows_for_test,
    write_training_data,
)

DCOC, INVERT = CorrectionModel.DCOC, LoopType.INVERT_LOOP


@pytest.mark.parametrize("layout", LAYOUTS)
def test_header_has_48_distinct_bits(layout: str) -> None:
    columns = header(layout)
    assert len(columns) == len(META_COLUMNS) + 48 + 1
    assert len(set(columns)) == len(columns)
    assert set(header("matriz")) == set(header("blocos"))


def test_matrix_layout_order() -> None:
    row0 = ["D00", "D01", "D02", "D03", "Cr00", "Cr01", "Cr02", "Pr0"]
    assert header("matriz")[4:16] == [*row0, "D10", "D11", "D12", "D13"]
    assert header("matriz")[-17:-1] == [f"Cc{t}{c}" for t in range(3) for c in range(4)] + [f"Pc{c}" for c in range(4)]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_each_error_position_sets_its_named_column(layout: str) -> None:
    """Com dados zero, um erro na posição p acende só a coluna do bit p."""
    expected = [f"D{p // 4}{p % 4}" for p in range(16)]
    expected += [f"Cr{(p - 16) // 3}{(p - 16) % 3}" for p in range(16, 28)]
    expected += [f"Pc{p - 28}" for p in range(28, 32)]
    expected += [f"Cc{(p - 32) // 4}{(p - 32) % 4}" for p in range(32, 44)]
    expected += [f"Pr{p - 44}" for p in range(44, 48)]
    columns = header(layout)
    rows = list(rows_for_test(DCOC, INVERT, 1, 0, layout=layout))
    for p, row in enumerate(rows):
        lit = [name for name, value in zip(columns[4:-1], row[4:-1], strict=True) if value == 1]
        assert lit == [expected[p]]


@pytest.mark.parametrize("rng", [None, random.Random(7)], ids=["zeros", "aleatorio"])
def test_labels_match_simulation_counters(rng: random.Random | None) -> None:
    """DCOC/InvertLoop, 3 erros, 1 iteração: 192 falhas finais (golden do Java)."""
    rows = list(rows_for_test(DCOC, INVERT, 3, 1, rng=rng))
    assert len(rows) == 17296
    assert sum(row[-1] == -1 for row in rows) == 192
    assert {row[-1] for row in rows} == {1, -1}


def test_random_data_rows_are_received_codewords() -> None:
    rng = random.Random(1)
    row = next(rows_for_test(DCOC, INVERT, 0, 0, rng=rng))
    data = random.Random(1).getrandbits(16)
    lpc = Lpc([[(data >> (4 * r + c)) & 1 for c in range(4)] for r in range(4)])
    assert row[4:-1] == LAYOUTS["matriz"].bits(LpcWithError(lpc, ()))
    assert row[-1] == 1


def test_file_is_appended_with_single_header(tmp_path: Path) -> None:
    path = tmp_path / "Dados de Treinamento.csv"
    config = SweepConfig((DCOC,), (INVERT,), max_errors=1, max_iterations=0)
    assert count_rows(config) == 49
    assert write_training_data(path, config) == (49, 0)
    assert write_training_data(path, config) == (49, 0)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == header()
    assert len(rows) == 1 + 2 * 49
    with pytest.raises(ValueError, match="outras colunas"):
        write_training_data(path, config, layout="blocos")


def test_cli_training_data(tmp_path: Path) -> None:
    path = tmp_path / "saida.csv"
    args = ["--max-errors", "2", "--max-iterations", "0", "--dados-treinamento", str(path)]
    assert cli_main(args) == 0
    labels = [row[-1] for row in csv.reader(path.open(encoding="utf-8"))][1:]
    assert len(labels) == 1 + 48 + 1128
    assert labels.count("-1") == 88  # DCOC/InvertLoop, 2 erros, 0 iterações


def test_cli_training_data_refuses_huge_sweep(tmp_path: Path) -> None:
    path = tmp_path / "saida.csv"
    assert cli_main(["--dados-treinamento", str(path)]) == 1  # preset main: ~703 milhões de linhas
    assert not path.exists()
