"""Conjunto de dados de treinamento: uma linha por decodificação.

Cada padrão de erro testado pela varredura vira uma linha com:

* a identificação do teste (modelo, laço, iterações do AlgSE, nº de erros);
* os 48 bits da palavra **recebida**, isto é, já com os erros e antes de
  qualquer correção: ``D``, ``Cr``, ``Pr``, ``Cc`` e ``Pc``;
* o rótulo: ``1`` se ``D`` foi recuperado após AlgSE + AlgDE, ``-1`` se não.

Ordem dos bits (``layout``):

``matriz`` (padrão)
    A leitura da matriz estendida, linha a linha, como no diagrama de
    :mod:`lpc_sim.lpc`: para cada linha ``r``, ``D[r][0..3]``, ``Cr[r][0..2]``
    e ``Pr[r]`` (8 bits); depois ``Cc0``, ``Cc1``, ``Cc2`` e ``Pc``, cada um com
    as 4 colunas. Cada linha de dados fica vizinha dos seus próprios bits de
    verificação.

``blocos``
    Todos os ``D``, depois todos os ``Cr``, ``Pr``, ``Cc`` e ``Pc``.

Nomes das colunas: ``D12`` = ``D[1][2]``; ``Cr30`` = ``Cr[3][0]`` (linha 3,
bit C0); ``Cc02`` = ``Cc[0][2]`` (bit C0, coluna 2); ``Pr1``/``Pc1`` = paridade
da linha/coluna 1.

Por padrão os dados transmitidos são todos zero, como na simulação. Nesse caso
a palavra recebida é o próprio padrão de erro. Com ``rng``, cada padrão usa um
``D`` aleatório, e a palavra recebida passa a ser ``codificação(D) ⊕ erro``.
O rótulo é o mesmo nos dois casos, porque o decodificador só depende das
síndromes (ver COMO_FUNCIONA.md, seção 3.5).
"""

from __future__ import annotations

import csv
import math
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import TextIO

from .enums import CorrectionModel, LoopType
from .lpc import CHECK_BITS, DATA_SIZE, Lpc
from .lpc_with_error import NUM_ELEMENTS_LPC, LpcWithError
from .simulation_system import SweepConfig, decode_received

DEFAULT_FILE_NAME = "Dados de Treinamento.csv"

CORRECTED = 1
NOT_CORRECTED = -1

META_COLUMNS = ("correction_model", "loop_type", "iterations_se", "num_errors")
LABEL_COLUMN = "label"

type Row = list[str | int]


def _matrix_bits(lpc: Lpc) -> list[int]:
    bits: list[int] = []
    for r in range(DATA_SIZE):
        bits += lpc.D[r]
        bits += lpc.Cr[r]
        bits.append(lpc.Pr[r])
    for t in range(CHECK_BITS):
        bits += lpc.Cc[t]
    bits += lpc.Pc
    return bits


def _matrix_names() -> list[str]:
    names: list[str] = []
    for r in range(DATA_SIZE):
        names += [f"D{r}{c}" for c in range(DATA_SIZE)]
        names += [f"Cr{r}{t}" for t in range(CHECK_BITS)]
        names.append(f"Pr{r}")
    for t in range(CHECK_BITS):
        names += [f"Cc{t}{c}" for c in range(DATA_SIZE)]
    names += [f"Pc{c}" for c in range(DATA_SIZE)]
    return names


def _block_bits(lpc: Lpc) -> list[int]:
    bits: list[int] = []
    for r in range(DATA_SIZE):
        bits += lpc.D[r]
    for r in range(DATA_SIZE):
        bits += lpc.Cr[r]
    bits += lpc.Pr
    for t in range(CHECK_BITS):
        bits += lpc.Cc[t]
    bits += lpc.Pc
    return bits


def _block_names() -> list[str]:
    return (
        [f"D{r}{c}" for r in range(DATA_SIZE) for c in range(DATA_SIZE)]
        + [f"Cr{r}{t}" for r in range(DATA_SIZE) for t in range(CHECK_BITS)]
        + [f"Pr{r}" for r in range(DATA_SIZE)]
        + [f"Cc{t}{c}" for t in range(CHECK_BITS) for c in range(DATA_SIZE)]
        + [f"Pc{c}" for c in range(DATA_SIZE)]
    )


@dataclass(frozen=True, slots=True)
class Layout:
    bits: Callable[[Lpc], list[int]]
    names: Callable[[], list[str]]


LAYOUTS: dict[str, Layout] = {
    "matriz": Layout(_matrix_bits, _matrix_names),
    "blocos": Layout(_block_bits, _block_names),
}


def header(layout: str = "matriz") -> list[str]:
    return [*META_COLUMNS, *LAYOUTS[layout].names(), LABEL_COLUMN]


def count_rows(config: SweepConfig) -> int:
    """Nº de linhas que a varredura gera (uma por padrão de erro testado)."""
    start, end = config.error_interval
    patterns = sum(math.comb(end - start, n) for n in range(config.max_errors + 1))
    return len(config.correction_models) * len(config.loop_types) * (config.max_iterations + 1) * patterns


def _random_lpc(rng: random.Random) -> Lpc:
    value = rng.getrandbits(DATA_SIZE * DATA_SIZE)
    return Lpc([[(value >> (DATA_SIZE * r + c)) & 1 for c in range(DATA_SIZE)] for r in range(DATA_SIZE)])


def rows_for_test(
    correction_model: CorrectionModel,
    loop_type: LoopType,
    num_errors: int,
    iterations_se: int,
    *,
    layout: str = "matriz",
    error_interval: tuple[int, int] = (0, NUM_ELEMENTS_LPC),
    rng: random.Random | None = None,
) -> Iterator[Row]:
    """Linhas de um teste: todos os C(n, ``num_errors``) padrões do intervalo."""
    to_bits = LAYOUTS[layout].bits
    meta: list[str | int] = [correction_model.label, loop_type.label, iterations_se, num_errors]
    zero_lpc = Lpc([[0] * DATA_SIZE for _ in range(DATA_SIZE)])
    for pattern in combinations(range(*error_interval), num_errors):
        initial_lpc = _random_lpc(rng) if rng is not None else zero_lpc
        received = LpcWithError(initial_lpc, pattern)
        bits = to_bits(received)  # capturado antes da decodificação, que altera ``received``
        _, de_failed = decode_received(initial_lpc, received, iterations_se, loop_type, correction_model)
        yield [*meta, *bits, NOT_CORRECTED if de_failed else CORRECTED]


def write_training_data(
    path: str | Path,
    config: SweepConfig,
    *,
    layout: str = "matriz",
    rng: random.Random | None = None,
    progress: TextIO | None = None,
) -> tuple[int, int]:
    """Acrescenta ao CSV ``path`` as linhas de toda a varredura ``config``.

    O cabeçalho só é escrito se o arquivo for novo ou vazio. Se o arquivo já
    tiver outro cabeçalho (ex.: outro ``layout``), levanta ``ValueError`` em vez
    de misturar colunas. Retorna ``(linhas, linhas_com_rotulo_-1)``.
    """
    path = Path(path)
    columns = header(layout)
    existing = path.read_text(encoding="utf-8").splitlines()[:1] if path.exists() else []
    if existing and existing[0] != ",".join(columns):
        raise ValueError(
            f"'{path}' já existe com outras colunas (outro layout?). Use outro arquivo ou o mesmo --layout."
        )

    total = failures = 0
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not existing:
            writer.writerow(columns)
        for model in config.correction_models:
            for loop_type in config.loop_types:
                for n in range(config.max_errors + 1):
                    for iterations in range(config.max_iterations + 1):
                        rows = failures_here = 0
                        for row in rows_for_test(
                            model, loop_type, n, iterations,
                            layout=layout, error_interval=config.error_interval, rng=rng,
                        ):  # fmt: skip
                            writer.writerow(row)
                            rows += 1
                            failures_here += row[-1] == NOT_CORRECTED
                        total += rows
                        failures += failures_here
                        if progress is not None:
                            print(
                                f"AlgSE{iterations}_{model.label} ({loop_type.label}) #Errors={n}: "
                                f"{rows} linhas, {failures_here} com rótulo -1",
                                file=progress,
                                flush=True,
                            )
    return total, failures
