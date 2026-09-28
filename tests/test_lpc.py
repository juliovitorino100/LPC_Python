"""Testes unitários de codificação e injeção de erros."""

from __future__ import annotations

import itertools

import pytest

from lpc_sim import NUM_ELEMENTS_LPC, InvalidErrorPositionError, Lpc, LpcWithError, LpcWithErrror

ZERO = [[0] * 4 for _ in range(4)]
SAMPLE = [[1, 0, 1, 1], [0, 1, 1, 0], [1, 1, 1, 1], [0, 0, 0, 1]]


def test_encoding_of_zero_matrix_is_all_zero() -> None:
    lpc = Lpc(ZERO)
    assert lpc.Cr == [[0] * 3] * 4
    assert lpc.Cc == [[0] * 4] * 3
    assert lpc.Pr == [0] * 4
    assert lpc.Pc == [0] * 4


@pytest.mark.parametrize("bits", list(itertools.product((0, 1), repeat=4)))
def test_row_hamming_equations(bits: tuple[int, ...]) -> None:
    d0, d1, d2, d3 = bits
    lpc = Lpc([list(bits)] * 4)
    assert lpc.Cr[0] == [d1 ^ d2 ^ d3, d0 ^ d2 ^ d3, d0 ^ d1 ^ d3]
    assert lpc.Pr[0] == d0 ^ d1 ^ d2 ^ d3 ^ lpc.Cr[0][0] ^ lpc.Cr[0][1] ^ lpc.Cr[0][2]


def test_constructor_copies_data() -> None:
    source = [row[:] for row in SAMPLE]
    lpc = Lpc(source)
    source[0][0] = 99
    assert lpc.D[0][0] == 1


def test_valid_codeword_has_zero_syndromes() -> None:
    received = LpcWithError(Lpc(SAMPLE), [])
    assert not any(received.SEr + received.SEc + received.DEr + received.DEc)
    assert received.EAr == [0] * 4 and received.EAc == [0] * 4


@pytest.mark.parametrize("position", range(NUM_ELEMENTS_LPC))
def test_each_position_flips_exactly_one_bit(position: int) -> None:
    initial = Lpc(SAMPLE)
    received = LpcWithError(initial, [position])

    def flat(lpc: Lpc) -> list[int]:
        # Ordem das posições do Java: D, Cr, Pc, Cc, Pr
        return [
            *itertools.chain.from_iterable(lpc.D),
            *itertools.chain.from_iterable(lpc.Cr),
            *lpc.Pc,
            *itertools.chain.from_iterable(lpc.Cc),
            *lpc.Pr,
        ]

    diff = [i for i, (a, b) in enumerate(zip(flat(initial), flat(received), strict=True)) if a != b]
    assert diff == [position]


@pytest.mark.parametrize("position", [48, 100, -1, -16])
def test_invalid_position_raises(position: int) -> None:
    with pytest.raises(InvalidErrorPositionError, match=f"Error position = {position}"):
        LpcWithError(Lpc(ZERO), [position])


def test_invalid_position_is_also_value_error() -> None:
    with pytest.raises(ValueError):
        LpcWithError(Lpc(ZERO), [48])


def test_is_equal_compares_only_data() -> None:
    initial = Lpc(ZERO)
    assert initial.is_equal(LpcWithError(initial, [20, 30, 40]))  # só bits C/P
    assert not initial.is_equal(LpcWithError(initial, [5]))


def test_java_alias() -> None:
    assert LpcWithErrror is LpcWithError
