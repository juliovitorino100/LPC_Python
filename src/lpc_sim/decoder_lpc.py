"""Algoritmos de decodificação — equivalente a ``DecoderLpc.java``.

A classe Java continha apenas métodos ``static``; em Python o idiomático é um
módulo de funções. Correspondência de nomes:

=====================================  =========================================
Java (``DecoderLpc``)                  Python (``lpc_sim.decoder_lpc``)
=====================================  =========================================
``decodingSE``                         :func:`decoding_se`
``decodingSE_BasicLoop``               :func:`decoding_se_basic_loop`
``decodingSE_InvertLoop``              :func:`decoding_se_invert_loop`
``decodingSE_PriorityLoop``            :func:`decoding_se_priority_loop`
``decodingSE_FairPriorityLoop``        :func:`decoding_se_fair_priority_loop`
``ApplyHammingOnRows/Columns``         :func:`_apply_hamming_on_rows` / ``_columns``
``ApplyHammingOn{Rows,Columns}DCO``    ``_apply_hamming(..., DCO)``
``...DCOC`` / ``...DRC`` / ``...DRCC`` ``_apply_hamming(..., <modelo>)``
``decodingDE``                         :func:`decoding_de`
=====================================  =========================================

**Refatoração explicada.** Os oito métodos ``ApplyHammingOn*`` do Java eram
cópias quase idênticas que variavam em apenas dois eixos:

* ``cross_check`` (DCOC, DRCC): o bit de *dado* só é corrigido se a
  coluna/linha cruzada também acusar algo (``SE`` ou ``DE`` ou paridade ≠ 0);
* ``corrects_redundancy`` (DRC, DRCC): endereços 4, 2 e 1 corrigem os bits de
  verificação ``C0``, ``C1`` e ``C2``. Essa correção **nunca** usa verificação
  cruzada, nem no DRCC — comportamento preservado.

Eles foram unificados em :func:`_apply_hamming`, parametrizado pelo
:class:`~lpc_sim.enums.CorrectionModel` e pela orientação (linha/coluna). A
equivalência com o Java foi verificada exaustivamente (ver README).
"""

from __future__ import annotations

from typing import Final

from .enums import CorrectionModel, LoopType
from .lpc import DATA_SIZE
from .lpc_with_error import LpcWithError, invert_bit

# Endereço de síndrome Hamming -> posição do bit de dado (0..3).
# Java: ``if (add==3 || (add>=5 && add<=7)) add = (add==3) ? 0 : add - 4;``
_DATA_ADDRESS: Final[dict[int, int]] = {3: 0, 5: 1, 6: 2, 7: 3}

# Endereço de síndrome Hamming -> índice do bit de verificação C (DRC/DRCC).
# Java: add==4 -> C[0], add==2 -> C[1], add==1 -> C[2].
_CHECK_ADDRESS: Final[dict[int, int]] = {4: 0, 2: 1, 1: 2}

# Tabela ``tab[7][3][2]`` do Java, usada por decodingDE. Para cada endereço de
# erro duplo (EA-1), lista os 3 pares de posições (0..3 = dado, 4..6 = bits de
# verificação) cuja combinação produz aquela síndrome. Mantida sem alterações.
TAB: Final[tuple[tuple[tuple[int, int], ...], ...]] = (
    ((2, 3), (0, 5), (1, 4)),
    ((1, 3), (0, 6), (2, 4)),
    ((1, 3), (3, 4), (5, 6)),
    ((0, 3), (1, 5), (2, 5)),
    ((0, 2), (3, 5), (4, 6)),
    ((0, 1), (3, 6), (4, 5)),
    ((0, 4), (1, 5), (2, 6)),
)


# ---------------------------------------------------------------------- #
# Decodificação de erro simples (AlgSE)
# ---------------------------------------------------------------------- #
def decoding_se(
    iterations_se: int,
    loop_type: LoopType | int,
    correction_model: CorrectionModel | int,
    lpc: LpcWithError,
) -> None:
    """Despacha para a estratégia de laço escolhida (modifica ``lpc`` in-place).

    Como o ``switch`` Java não tinha ``default``, um ``loop_type`` desconhecido
    simplesmente não faz nada. ``IntEnum`` casa com os inteiros 0..3, então
    chamadas com os códigos numéricos originais também funcionam.
    """
    match loop_type:
        case LoopType.BASIC_LOOP:
            decoding_se_basic_loop(iterations_se, correction_model, lpc)
        case LoopType.INVERT_LOOP:
            decoding_se_invert_loop(iterations_se, correction_model, lpc)
        case LoopType.PRIORITY_LOOP:
            decoding_se_priority_loop(iterations_se, correction_model, lpc)
        case LoopType.FAIR_PRIORITY_LOOP:
            decoding_se_fair_priority_loop(iterations_se, correction_model, lpc)
        case _:
            return


def decoding_se_basic_loop(iterations_se: int, correction_model: CorrectionModel | int, lpc: LpcWithError) -> None:
    # Java: for (cont = 0; cont <= iterationsSE; cont++) -> iterationsSE + 1 voltas.
    for _ in range(iterations_se + 1):
        _apply_hamming_on_rows(correction_model, lpc)
        _apply_hamming_on_columns(correction_model, lpc)


def decoding_se_invert_loop(iterations_se: int, correction_model: CorrectionModel | int, lpc: LpcWithError) -> None:
    # Alterna colunas / linhas, começando pelas colunas (tf = true no Java).
    columns_turn = True
    for _ in range(iterations_se + 1):
        if columns_turn:
            _apply_hamming_on_columns(correction_model, lpc)
        else:
            _apply_hamming_on_rows(correction_model, lpc)
        columns_turn = not columns_turn


def decoding_se_priority_loop(iterations_se: int, correction_model: CorrectionModel | int, lpc: LpcWithError) -> None:
    # Java: cont <= 2*iterationsSE + 1  ->  2*iterationsSE + 2 voltas.
    for _ in range(2 * iterations_se + 2):
        se_columns, se_rows = sum(lpc.SEc), sum(lpc.SEr)
        if se_columns == 0 and se_rows == 0:
            continue  # Mantido como ``continue`` (não ``break``), como no Java.
        if se_columns >= se_rows:
            _apply_hamming_on_columns(correction_model, lpc)
        else:
            _apply_hamming_on_rows(correction_model, lpc)


def decoding_se_fair_priority_loop(
    iterations_se: int, correction_model: CorrectionModel | int, lpc: LpcWithError
) -> None:
    for _ in range(iterations_se + 1):
        se_columns, se_rows = sum(lpc.SEc), sum(lpc.SEr)
        if se_columns == 0 and se_rows == 0:
            continue
        if se_columns >= se_rows:
            _apply_hamming_on_columns(correction_model, lpc)
            _apply_hamming_on_rows(correction_model, lpc)
        else:
            _apply_hamming_on_rows(correction_model, lpc)
            _apply_hamming_on_columns(correction_model, lpc)


def _apply_hamming_on_rows(correction_model: CorrectionModel | int, lpc: LpcWithError) -> None:
    model = _as_model(correction_model)
    if model is not None:  # switch Java sem default: modelo desconhecido = no-op
        _apply_hamming(lpc, model, on_rows=True)


def _apply_hamming_on_columns(correction_model: CorrectionModel | int, lpc: LpcWithError) -> None:
    model = _as_model(correction_model)
    if model is not None:
        _apply_hamming(lpc, model, on_rows=False)


def _as_model(value: CorrectionModel | int) -> CorrectionModel | None:
    try:
        return CorrectionModel(value)
    except ValueError:
        return None


def _apply_hamming(lpc: LpcWithError, model: CorrectionModel, *, on_rows: bool) -> None:
    """Núcleo único dos oito ``ApplyHammingOn{Rows,Columns}{DCO,DCOC,DRC,DRCC}``.

    Assim como no Java, as síndromes são lidas do estado *anterior* a todas as
    correções desta passada; ``recompute_control_variables`` só é chamado no
    final, e apenas se algum bit foi invertido.
    """
    if on_rows:
        single_error, address = lpc.SEr, lpc.EAr
        cross_se, cross_de, cross_parity = lpc.SEc, lpc.DEc, lpc.sPc
    else:
        single_error, address = lpc.SEc, lpc.EAc
        cross_se, cross_de, cross_parity = lpc.SEr, lpc.DEr, lpc.sPr

    cross_check = model.cross_check
    corrects_redundancy = model.corrects_redundancy
    D = lpc.D  # noqa: N806
    done = False

    for k in range(DATA_SIZE):
        if not single_error[k]:
            continue
        add = address[k]
        position = _DATA_ADDRESS.get(add)
        if position is not None:
            if cross_check and not (cross_se[position] or cross_de[position] or cross_parity[position] != 0):
                continue  # Dado não confirmado pelo cruzamento: nada é corrigido.
            r, c = (k, position) if on_rows else (position, k)
            D[r][c] = invert_bit(D[r][c])
            done = True
        elif corrects_redundancy and (bit := _CHECK_ADDRESS.get(add)) is not None:
            if on_rows:
                lpc.Cr[k][bit] = invert_bit(lpc.Cr[k][bit])
            else:
                lpc.Cc[bit][k] = invert_bit(lpc.Cc[bit][k])
            done = True

    if done:
        lpc.recompute_control_variables()


# ---------------------------------------------------------------------- #
# Decodificação de erro duplo (AlgDE)
# ---------------------------------------------------------------------- #
def decoding_de(lpc: LpcWithError) -> None:
    """Tenta corrigir erros duplos por votação cruzada linhas x colunas.

    Cada candidato recebe um voto da análise de linha e/ou da de coluna; só os
    bits com exatamente **2** votos (``== 2``, como no Java) são invertidos.
    Fiel ao original, as variáveis de controle **não** são recalculadas ao
    final (o simulador só compara ``D`` depois desta chamada).
    """
    votes = [[0] * DATA_SIZE for _ in range(DATA_SIZE)]

    for on_rows in (True, False):  # rc == 0 -> linhas; rc == 1 -> colunas
        double_error = lpc.DEr if on_rows else lpc.DEc
        address = lpc.EAr if on_rows else lpc.EAc
        crossing_de = lpc.DEc if on_rows else lpc.DEr

        def vote(k: int, position: int, on_rows: bool = on_rows) -> None:
            if on_rows:
                votes[k][position] += 1
            else:
                votes[position][k] += 1

        for k in range(DATA_SIZE):
            if not double_error[k]:
                continue
            add = address[k] - 1
            if add < 0:
                # Inalcançável (DE implica síndrome ≠ 0), mas no Java tab[-1]
                # lançaria ArrayIndexOutOfBoundsException; em Python, tab[-1]
                # leria a última linha silenciosamente. Mantemos a falha.
                raise IndexError(f"Endereço de erro duplo inválido: {address[k]}")

            expt = False
            for b1, b2 in TAB[add]:
                e1 = crossing_de[b1] if b1 <= 3 else False
                e2 = crossing_de[b2] if b2 <= 3 else False
                if (b1 >= 4 or e1) and (b2 >= 4 or e2):
                    if b1 <= 3:
                        vote(k, b1)
                        expt = True
                    if b2 <= 3:
                        vote(k, b2)
                        expt = True

            if not expt and (add == 2 or 4 <= add <= 6):
                vote(k, 0 if add == 2 else add - 3)

    for j in range(DATA_SIZE):
        for k in range(DATA_SIZE):
            if votes[j][k] == 2:
                lpc.D[j][k] = invert_bit(lpc.D[j][k])
