"""Código de produto LPC 4x4 — equivalente a ``Lpc.java``.

Layout (48 bits no total)::

            col0 col1 col2 col3 | Cr0 Cr1 Cr2 | Pr
    linha0   D    D    D    D   |  .   .   .  | .
    ...                          (Hamming(7,4) + paridade em cada linha)
    linha3   D    D    D    D   |  .   .   .  | .
    Cc0      .    .    .    .
    Cc1      .    .    .    .       (Hamming(7,4) + paridade em cada coluna)
    Cc2      .    .    .    .
    Pc       .    .    .    .

Nomes de atributos: ``D``, ``Cr``, ``Pr``, ``Cc`` e ``Pc`` foram mantidos
exatamente como no Java (fogem do snake_case da PEP 8 de propósito), porque são
a notação matemática do código e facilitam comparar linha a linha com o
original e com a literatura.
"""

from __future__ import annotations

from collections.abc import Sequence

type BitMatrix = list[list[int]]
type BitVector = list[int]

DATA_SIZE = 4
"""Dimensão da matriz de dados (4x4)."""

CHECK_BITS = 3
"""Bits de verificação Hamming por linha/coluna."""


def _join(values: Sequence[int | bool]) -> str:
    return " ".join(str(int(v)) for v in values)


class Lpc:
    """Palavra-código LPC sem erros, codificada a partir da matriz de dados."""

    def __init__(self, data_bits: Sequence[Sequence[int]]) -> None:
        # Cópia explícita 4x4, como os dois ``for`` do construtor Java: linhas
        # ou colunas extras são ignoradas; faltantes geram IndexError (no Java,
        # ArrayIndexOutOfBoundsException). ``throws Exception`` do Java nunca
        # era de fato disparado aqui, então não há exceção customizada.
        self.D: BitMatrix = [[data_bits[r][c] for c in range(DATA_SIZE)] for r in range(DATA_SIZE)]
        self.Cr: BitMatrix = [[0] * CHECK_BITS for _ in range(DATA_SIZE)]
        self.Pr: BitVector = [0] * DATA_SIZE
        self.Cc: BitMatrix = [[0] * DATA_SIZE for _ in range(CHECK_BITS)]
        self.Pc: BitVector = [0] * DATA_SIZE
        self._encode_column()
        self._encode_row()

    def _encode_column(self) -> None:
        D, Cc, Pc = self.D, self.Cc, self.Pc  # noqa: N806 - notação de domínio
        for k in range(DATA_SIZE):
            Cc[0][k] = D[1][k] ^ D[2][k] ^ D[3][k]
            Cc[1][k] = D[0][k] ^ D[2][k] ^ D[3][k]
            Cc[2][k] = D[0][k] ^ D[1][k] ^ D[3][k]
            Pc[k] = D[0][k] ^ D[1][k] ^ D[2][k] ^ D[3][k] ^ Cc[0][k] ^ Cc[1][k] ^ Cc[2][k]

    def _encode_row(self) -> None:
        D, Cr, Pr = self.D, self.Cr, self.Pr  # noqa: N806
        for k in range(DATA_SIZE):
            row, check = D[k], Cr[k]
            check[0] = row[1] ^ row[2] ^ row[3]
            check[1] = row[0] ^ row[2] ^ row[3]
            check[2] = row[0] ^ row[1] ^ row[3]
            Pr[k] = row[0] ^ row[1] ^ row[2] ^ row[3] ^ check[0] ^ check[1] ^ check[2]

    def is_equal(self, other: Lpc) -> bool:
        """Compara **somente** a matriz de dados ``D`` (como ``isEqual`` no Java).

        Não foi transformado em ``__eq__`` de propósito: redefinir ``__eq__``
        tornaria a classe não-hashable e sugeriria igualdade total do objeto,
        o que não é o que o método original faz.
        """
        return self.D == other.D

    def __str__(self) -> str:
        """Mesmo formato de ``Lpc.toString()``."""
        lines = [f"[{_join(self.D[k])}][{_join(self.Cr[k])}] {self.Pr[k]}" for k in range(DATA_SIZE)]
        lines += [f"[{_join(self.Cc[k])}]" for k in range(CHECK_BITS)]
        lines.append(f" {_join(self.Pc)}")
        return "\n".join(lines) + "\n"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(D={self.D!r})"
