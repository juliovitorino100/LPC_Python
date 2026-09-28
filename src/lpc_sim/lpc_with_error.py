"""LPC com padrão de erros injetado — equivalente a ``LpcWithErrror.java``.

A classe Java tinha um erro de digitação no nome (``Errror``, com três "r").
Em Python ela se chama :class:`LpcWithError`, e o alias ``LpcWithErrror`` é
exportado para facilitar a comparação com o código original.

Mapa das 48 posições de erro (mantido **exatamente** como no Java, inclusive a
ordem pouco intuitiva em que ``Pc`` vem antes de ``Cc`` e ``Pr`` fica no fim):

======  ==========================  ===========================
Faixa   Elemento                    Índice
======  ==========================  ===========================
0-15    ``D[linha][coluna]``        ``linha = p // 4``, ``coluna = p % 4``
16-27   ``Cr[linha][bit]``          ``p -= 16``; ``linha = p // 3``, ``bit = p % 3``
28-31   ``Pc[coluna]``              ``p - 28``
32-43   ``Cc[bit][coluna]``         ``p -= 32``; ``bit = p // 4``, ``coluna = p % 4``
44-47   ``Pr[linha]``               ``p - 44``
======  ==========================  ===========================
"""

from __future__ import annotations

from collections.abc import Iterable

from .exceptions import InvalidErrorPositionError
from .lpc import CHECK_BITS, DATA_SIZE, BitMatrix, BitVector, Lpc, _join

NUM_ELEMENTS_LPC = 48
"""Total de bits de uma palavra LPC (16 D + 12 Cr + 4 Pc + 12 Cc + 4 Pr)."""


def invert_bit(value: int) -> int:
    """Igual a ``invertBit`` do Java: ``value == 0 ? 1 : 0``."""
    return 1 if value == 0 else 0


class LpcWithError(Lpc):
    """Palavra LPC recebida (com erros), com síndromes e sinalizadores.

    Atributos de controle (nomes idênticos ao Java):

    * ``recCr``/``recPr``/``recCc``/``recPc`` – bits recalculados a partir de ``D``;
    * ``sCr``/``sPr``/``sCc``/``sPc`` – síndromes (1 = divergência);
    * ``sCrq``/``sCcq`` – 1 se alguma síndrome Hamming da linha/coluna é 1;
    * ``EAr``/``EAc`` – endereço do erro (``sC0*4 + sC1*2 + sC2``);
    * ``SEr``/``SEc`` – erro simples detectado; ``DEr``/``DEc`` – erro duplo.
    """

    def __init__(self, initial_lpc: Lpc, error_pattern: Iterable[int]) -> None:
        # super(initialLpc.D): copia D e recodifica C/P a partir dele.
        super().__init__(initial_lpc.D)

        self.recCr: BitMatrix = [[0] * CHECK_BITS for _ in range(DATA_SIZE)]
        self.recPr: BitVector = [0] * DATA_SIZE
        self.recCc: BitMatrix = [[0] * DATA_SIZE for _ in range(CHECK_BITS)]
        self.recPc: BitVector = [0] * DATA_SIZE

        self.sCr: BitMatrix = [[0] * CHECK_BITS for _ in range(DATA_SIZE)]
        self.sPr: BitVector = [0] * DATA_SIZE
        self.sCc: BitMatrix = [[0] * DATA_SIZE for _ in range(CHECK_BITS)]
        self.sPc: BitVector = [0] * DATA_SIZE
        self.EAr: BitVector = [0] * DATA_SIZE
        self.EAc: BitVector = [0] * DATA_SIZE
        self.SEr: list[bool] = [False] * DATA_SIZE
        self.DEr: list[bool] = [False] * DATA_SIZE
        self.SEc: list[bool] = [False] * DATA_SIZE
        self.DEc: list[bool] = [False] * DATA_SIZE
        self.sCrq: BitVector = [0] * DATA_SIZE
        self.sCcq: BitVector = [0] * DATA_SIZE

        self._set_error_pattern(error_pattern)
        self.recompute_control_variables()

    # ------------------------------------------------------------------ #
    # Variáveis de controle
    # ------------------------------------------------------------------ #
    def recompute_control_variables(self) -> None:
        self.recompute_check_bits_and_parity()
        self.compute_syndromes()
        self.compute_error_address()
        self.compute_se_de()

    def recompute_check_bits_and_parity(self) -> None:
        D, Cr, Cc = self.D, self.Cr, self.Cc  # noqa: N806
        for k in range(DATA_SIZE):
            row, rec = D[k], self.recCr[k]
            rec[0] = row[1] ^ row[2] ^ row[3]
            rec[1] = row[0] ^ row[2] ^ row[3]
            rec[2] = row[0] ^ row[1] ^ row[3]
            # Observação fiel ao original: a paridade recalculada usa os bits C
            # *recebidos* (Cr), e não os recalculados (recCr).
            self.recPr[k] = row[0] ^ row[1] ^ row[2] ^ row[3] ^ Cr[k][0] ^ Cr[k][1] ^ Cr[k][2]
        rec_c = self.recCc
        for k in range(DATA_SIZE):
            rec_c[0][k] = D[1][k] ^ D[2][k] ^ D[3][k]
            rec_c[1][k] = D[0][k] ^ D[2][k] ^ D[3][k]
            rec_c[2][k] = D[0][k] ^ D[1][k] ^ D[3][k]
            self.recPc[k] = D[0][k] ^ D[1][k] ^ D[2][k] ^ D[3][k] ^ Cc[0][k] ^ Cc[1][k] ^ Cc[2][k]

    def compute_syndromes(self) -> None:
        for k in range(DATA_SIZE):
            self.sPr[k] = 0 if self.Pr[k] == self.recPr[k] else 1
            self.sPc[k] = 0 if self.Pc[k] == self.recPc[k] else 1
            for t in range(CHECK_BITS):
                self.sCr[k][t] = 0 if self.Cr[k][t] == self.recCr[k][t] else 1
                self.sCc[t][k] = 0 if self.Cc[t][k] == self.recCc[t][k] else 1
        for k in range(DATA_SIZE):
            self.sCrq[k] = 1 if 1 in self.sCr[k] else 0
            self.sCcq[k] = 1 if (self.sCc[0][k] == 1 or self.sCc[1][k] == 1 or self.sCc[2][k] == 1) else 0

    def compute_error_address(self) -> None:
        for k in range(DATA_SIZE):
            self.EAr[k] = self.sCr[k][0] * 4 + self.sCr[k][1] * 2 + self.sCr[k][2]
            self.EAc[k] = self.sCc[0][k] * 4 + self.sCc[1][k] * 2 + self.sCc[2][k]

    def compute_se_de(self) -> None:
        """Equivalente a ``computeSE_DE``."""
        for k in range(DATA_SIZE):
            self.SEr[k] = self.sCrq[k] == 1 and self.sPr[k] == 1
            self.DEr[k] = self.sCrq[k] == 1 and self.sPr[k] == 0
            self.SEc[k] = self.sCcq[k] == 1 and self.sPc[k] == 1
            self.DEc[k] = self.sCcq[k] == 1 and self.sPc[k] == 0

    # ------------------------------------------------------------------ #
    # Injeção de erros
    # ------------------------------------------------------------------ #
    def _set_error_pattern(self, error_pattern: Iterable[int]) -> None:
        for position in error_pattern:
            self._set_error(position)

    def _set_error(self, error_position: int) -> None:
        p = error_position
        if 0 <= p < 16:
            row, column = divmod(p, 4)
            self.D[row][column] = invert_bit(self.D[row][column])
        elif 16 <= p < 28:
            row, column = divmod(p - 16, 3)
            self.Cr[row][column] = invert_bit(self.Cr[row][column])
        elif 28 <= p < 32:
            self.Pc[p - 28] = invert_bit(self.Pc[p - 28])
        elif 32 <= p < 44:
            row, column = divmod(p - 32, 4)
            self.Cc[row][column] = invert_bit(self.Cc[row][column])
        elif 44 <= p < 48:
            self.Pr[p - 44] = invert_bit(self.Pr[p - 44])
        else:
            # Negativos também caem aqui (ver InvalidErrorPositionError).
            raise InvalidErrorPositionError(error_position)

    # ------------------------------------------------------------------ #
    # Representação textual (idêntica a LpcWithErrror.toString())
    # ------------------------------------------------------------------ #
    def __str__(self) -> str:
        out = ["   D0 1 2 3 C0 1 2 P sC0 1 2 sP sCq SE DE Add\n"]
        for k in range(DATA_SIZE):
            out.append(
                f"D{k} [{_join(self.D[k])}][{_join(self.Cr[k])}]{self.Pr[k]}"
                f"  [{_join(self.sCr[k])}  {self.sPr[k]}]"
                f" {self.sCrq[k]}  "
                f"[{int(self.SEr[k])} {int(self.DEr[k])}] {self.EAr[k]}\n"
            )
        out += [f"C{k} [{_join(self.Cc[k])}]\n" for k in range(CHECK_BITS)]
        out.append(f"P   {_join(self.Pc)}\n")
        out += [f"sC{k}[{_join(self.sCc[k])}]\n" for k in range(CHECK_BITS)]
        out.append(f"sP [{_join(self.sPc)}]\n")
        out.append(f"sCq {_join(self.sCcq)}\n")
        out.append(f"SE [{_join(self.SEc)}]\n")
        out.append(f"DE [{_join(self.DEc)}]\n")
        out.append(f"Add {_join(self.EAc)}\n")
        return "".join(out)


LpcWithErrror = LpcWithError
"""Alias com o nome original do Java (com o erro de digitação)."""
