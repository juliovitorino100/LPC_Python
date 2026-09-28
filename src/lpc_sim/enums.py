"""Enumerações de domínio.

No Java original, o tipo de laço e o modelo de correção eram códigos ``int``
(0 a 3) documentados apenas em comentários de ``LpcSimulationSystem``. Aqui eles
viram ``IntEnum``: continuam sendo inteiros (``LoopType.INVERT_LOOP == 1`` é
``True``), então comparações e ``match`` com os valores numéricos originais
seguem funcionando, mas ganham nome e rótulo legíveis.
"""

from __future__ import annotations

from enum import IntEnum


class LoopType(IntEnum):
    """Estratégia de iteração do decodificador de erro simples (AlgSE)."""

    BASIC_LOOP = 0
    INVERT_LOOP = 1
    PRIORITY_LOOP = 2
    FAIR_PRIORITY_LOOP = 3

    @property
    def label(self) -> str:
        """Rótulo idêntico ao impresso pelo Java (ex.: ``"BasicLoop"``)."""
        return _LOOP_LABELS[self]

    @classmethod
    def from_label(cls, text: str) -> LoopType:
        """Aceita o rótulo Java (``BasicLoop``), o nome Python ou o número."""
        return _parse(cls, text, {v.lower(): k for k, v in _LOOP_LABELS.items()})


class CorrectionModel(IntEnum):
    """Modelo de correção aplicado pelo código de Hamming em linhas/colunas."""

    DCO = 0  # Data Correction Only
    DCOC = 1  # Data Correction Only Cross-check
    DRC = 2  # Data and Redundancy Correction
    DRCC = 3  # Data and Redundancy Correction Cross-check

    @property
    def label(self) -> str:
        return self.name

    @property
    def corrects_redundancy(self) -> bool:
        """``True`` quando o modelo também corrige bits de verificação (C)."""
        return self in (CorrectionModel.DRC, CorrectionModel.DRCC)

    @property
    def cross_check(self) -> bool:
        """``True`` quando a correção de dado exige confirmação cruzada."""
        return self in (CorrectionModel.DCOC, CorrectionModel.DRCC)

    @classmethod
    def from_label(cls, text: str) -> CorrectionModel:
        return _parse(cls, text, {m.name.lower(): m for m in cls})


_LOOP_LABELS: dict[LoopType, str] = {
    LoopType.BASIC_LOOP: "BasicLoop",
    LoopType.INVERT_LOOP: "InvertLoop",
    LoopType.PRIORITY_LOOP: "PriorityLoop",
    LoopType.FAIR_PRIORITY_LOOP: "FairPriorityLoop",
}


def _parse[E: IntEnum](enum_cls: type[E], text: str, labels: dict[str, E]) -> E:
    key = text.strip()
    if key.lstrip("-").isdigit():
        return enum_cls(int(key))
    # Atenção: não usar ``labels.get(...) or ...`` — o membro de valor 0 é "falsy".
    member = labels.get(key.lower())
    if member is not None:
        return member
    try:
        return enum_cls[key.upper()]
    except KeyError:
        valid = ", ".join(sorted({*labels, *(m.name for m in enum_cls)}))
        raise ValueError(f"Valor inválido para {enum_cls.__name__}: {text!r}. Use: {valid}") from None
