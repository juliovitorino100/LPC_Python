"""Testes do decodificador, incluindo comparação de estado completo com o Java."""

from __future__ import annotations

from pathlib import Path

import pytest

from lpc_sim import CorrectionModel, LoopType, Lpc, LpcWithError, decoding_de, decoding_se

ZERO = [[0] * 4 for _ in range(4)]


@pytest.mark.parametrize("model", list(CorrectionModel))
@pytest.mark.parametrize("loop", list(LoopType))
@pytest.mark.parametrize("position", range(16))
def test_single_data_error_is_corrected(model: CorrectionModel, loop: LoopType, position: int) -> None:
    initial = Lpc(ZERO)
    received = LpcWithError(initial, [position])
    decoding_se(0, loop, model, received)
    assert initial.is_equal(received)


def test_drc_corrects_check_bit_but_dco_does_not() -> None:
    initial = Lpc(ZERO)
    for model, expected in ((CorrectionModel.DCO, 1), (CorrectionModel.DRC, 0)):
        received = LpcWithError(initial, [16])  # Cr[0][0]
        decoding_se(0, LoopType.BASIC_LOOP, model, received)
        assert received.Cr[0][0] == expected


def test_int_codes_match_enums() -> None:
    a = LpcWithError(Lpc(ZERO), [0, 5, 17])
    b = LpcWithError(Lpc(ZERO), [0, 5, 17])
    decoding_se(2, 3, 1, a)
    decoding_se(2, LoopType.FAIR_PRIORITY_LOOP, CorrectionModel.DCOC, b)
    assert str(a) == str(b)


def test_unknown_codes_are_noop_like_java_switch() -> None:
    received = LpcWithError(Lpc(ZERO), [0])
    before = str(received)
    decoding_se(3, 99, CorrectionModel.DCO, received)
    decoding_se(3, LoopType.BASIC_LOOP, 42, received)
    assert str(received) == before


def _run_state_case(line: str) -> str:
    parts = line.strip().split(";")
    bits = list(map(int, parts[0].split(",")))
    data = [bits[i * 4 : i * 4 + 4] for i in range(4)]
    iterations, loop, model = int(parts[1]), int(parts[2]), int(parts[3])
    pattern = [int(x) for x in parts[4].split(",")] if len(parts) > 4 and parts[4] else []

    initial = Lpc(data)
    received = LpcWithError(initial, pattern)
    out = ["#INIT\n", str(initial), "#RECV\n", str(received)]
    decoding_se(iterations, loop, model, received)
    out += ["#SE\n", str(received)]
    decoding_de(received)
    out += ["#DE\n", str(received)]
    return "".join(out)


def test_full_state_matches_java(golden: Path) -> None:
    """300 casos aleatórios (dados ≠ 0, até 10 erros, repetições, códigos inválidos).

    ``java_states.txt`` foi gerado executando as classes Java originais.
    """
    cases = (golden / "state_cases.txt").read_text().splitlines()
    produced = "".join(_run_state_case(c) for c in cases)
    assert produced == (golden / "java_states.txt").read_text()
