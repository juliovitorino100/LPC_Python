"""Simulação exaustiva — equivalente a ``LpcSimulationSystem.java``.

O Java guardava todo o estado em campos ``static`` e era dirigido por
``main``/``main2``. Aqui o estado vive numa instância de
:class:`LpcSimulationSystem` (evita estado global e permite testes isolados),
com os mesmos *setters* e a mesma saída de console, caractere por caractere.

Para cada teste (modelo, laço, nº de erros, nº de iterações), todos os
C(48, n) padrões de ``n`` erros são gerados; cada um é decodificado com AlgSE e,
se ``D`` não voltar ao original, com AlgDE. São contados:

* ``numberOfDecodigns`` – total de decodificações (grafia do Java preservada
  na saída impressa, inclusive o erro de digitação);
* ``errorSeDecoding``  – falhas após AlgSE;
* ``errorDeDecoding``  – falhas após AlgSE + AlgDE.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass
from itertools import combinations
from typing import TextIO

from . import decoder_lpc
from .enums import CorrectionModel, LoopType
from .lpc import Lpc
from .lpc_with_error import NUM_ELEMENTS_LPC, LpcWithError

# Número de erros a partir do qual vale a pena distribuir entre processos.
_PARALLEL_MIN_ERRORS = 4
# Tamanho do prefixo usado para fatiar as combinações (C(48,2) = 1128 fatias).
_SHARD_PREFIX = 2


@dataclass(slots=True)
class DecodingCounters:
    """Contadores de um teste (ou de uma fatia dele, no modo paralelo)."""

    number_of_decodings: int = 0
    error_se_decoding: int = 0
    error_de_decoding: int = 0

    def __iadd__(self, other: DecodingCounters) -> DecodingCounters:
        self.number_of_decodings += other.number_of_decodings
        self.error_se_decoding += other.error_se_decoding
        self.error_de_decoding += other.error_de_decoding
        return self


def decode_pattern(
    initial_lpc: Lpc,
    error_pattern: Sequence[int],
    iterations_se: int,
    loop_type: LoopType | int,
    correction_model: CorrectionModel | int,
) -> tuple[bool, bool]:
    """Decodifica um padrão de erros; retorna ``(falhou_SE, falhou_DE)``.

    Corpo do ramo ``if (errorIndex == numErrors)`` de ``errorGenerator``.
    Função única usada pelos modos sequencial e paralelo, para que a regra de
    negócio exista num só lugar.
    """
    lpc_with_errors = LpcWithError(initial_lpc, error_pattern)
    return decode_received(initial_lpc, lpc_with_errors, iterations_se, loop_type, correction_model)


def decode_received(
    initial_lpc: Lpc,
    lpc_with_errors: LpcWithError,
    iterations_se: int,
    loop_type: LoopType | int,
    correction_model: CorrectionModel | int,
) -> tuple[bool, bool]:
    """Como :func:`decode_pattern`, mas recebe a palavra já com os erros.

    ``lpc_with_errors`` é **modificada** pela decodificação. Existe para quem
    precisa ler a palavra recebida antes de decodificá-la (ver
    :mod:`lpc_sim.training_data`) sem construí-la duas vezes.
    """
    decoder_lpc.decoding_se(iterations_se, loop_type, correction_model, lpc_with_errors)
    if initial_lpc.is_equal(lpc_with_errors):
        return False, False
    decoder_lpc.decoding_de(lpc_with_errors)
    return True, not initial_lpc.is_equal(lpc_with_errors)


def _decode_shard(
    task: tuple[list[list[int]], tuple[int, ...], int, int, int, int, int],
) -> DecodingCounters:
    """Processa todas as combinações que começam com ``prefix`` (worker)."""
    initial_d, prefix, end, remaining, iterations_se, loop_type, correction_model = task
    initial_lpc = Lpc(initial_d)
    counters = DecodingCounters()
    for suffix in combinations(range(prefix[-1] + 1, end), remaining):
        se_failed, de_failed = decode_pattern(initial_lpc, prefix + suffix, iterations_se, loop_type, correction_model)
        counters.number_of_decodings += 1
        counters.error_se_decoding += se_failed
        counters.error_de_decoding += de_failed
    return counters


class LpcSimulationSystem:
    """Estado e passos da simulação (antes: campos e métodos ``static``)."""

    def __init__(self, *, output: TextIO | None = None, executor: Executor | None = None) -> None:
        self._out = output if output is not None else sys.stdout
        self._executor = executor

        # Valores iniciais iguais aos dos campos static do Java.
        self.iterations_se = 0
        self.correction_model: CorrectionModel | int = CorrectionModel.DCO
        self.loop_type: LoopType | int = LoopType.BASIC_LOOP
        self.num_errors = 0
        self.elemento_inicial = 0
        self.num_elements_lpc = NUM_ELEMENTS_LPC
        self.counters = DecodingCounters()
        self.initial_lpc: Lpc | None = None
        self.num_combinations = 0
        # ``percentageLP = ~0`` (== -1). Nunca é zerado entre testes no Java, e
        # isso é preservado: se um teste termina em 100% e o seguinte também só
        # atinge 100% (ex.: 0 erros), o segundo não imprime nada.
        self.percentage_lp = ~0

    # ------------------------------------------------------------------ #
    # Configuração (setters do Java)
    # ------------------------------------------------------------------ #
    def set_initial_lpc(self, data_bits: Sequence[Sequence[int]] | None = None) -> None:
        """Sem argumento, usa a matriz 4x4 de zeros, como ``setInitialLpc``."""
        if data_bits is None:
            data_bits = [[0, 0, 0, 0] for _ in range(4)]
        self.initial_lpc = Lpc(data_bits)

    def set_error_interval(self, inicio: int, fim: int) -> None:
        """Define o intervalo ``[inicio, fim)`` de posições que podem ter erro.

        Suposição mantida do original: ``set_number_of_errors`` calcula
        C(``fim``, n), e não C(``fim - inicio``, n). Com ``inicio > 0`` a
        porcentagem de progresso não chega a 100 — os contadores continuam
        corretos. Chame este método **antes** de ``set_number_of_errors``.
        """
        self.elemento_inicial = inicio
        self.num_elements_lpc = fim

    def set_number_of_errors(self, n_errors: int) -> None:
        # O Java calculava n!/(n-k)! / k! com dois laços em ``long``; o
        # resultado é exatamente C(numElementsLpc, nE), o que ``math.comb``
        # fornece com inteiros de precisão arbitrária (inclusive 0 se nE > n).
        # Negativos: o Java falhava em ``new int[numErrors]``; aqui, ValueError.
        self.num_errors = n_errors
        self.num_combinations = math.comb(self.num_elements_lpc, n_errors)

    def set_iterations_se(self, number_of_iterations: int) -> None:
        self.iterations_se = number_of_iterations

    def set_loop_type(self, loop_type: LoopType | int) -> None:
        self.loop_type = loop_type

    def set_correction_model(self, model: CorrectionModel | int) -> None:
        self.correction_model = model

    def reset_simulation_data(self) -> None:
        self.counters = DecodingCounters()

    # ------------------------------------------------------------------ #
    # Execução
    # ------------------------------------------------------------------ #
    def error_generator(self) -> None:
        """Gera e decodifica todos os padrões de ``num_errors`` erros.

        O Java usava recursão "inclui/exclui" (``errorGenerator``), que produz
        as combinações em ordem lexicográfica — a mesma de
        ``itertools.combinations``, usada aqui (mais idiomática, sem risco de
        estouro de recursão e sem o vetor ``errorPattern`` mutável).
        """
        if self.initial_lpc is None:
            raise RuntimeError("Chame set_initial_lpc() antes de executar a simulação.")

        if self._executor is not None and self.num_errors >= _PARALLEL_MIN_ERRORS:
            self._error_generator_parallel()
            return

        for pattern in self._patterns():
            se_failed, de_failed = decode_pattern(
                self.initial_lpc, pattern, self.iterations_se, self.loop_type, self.correction_model
            )
            self.counters.number_of_decodings += 1
            self.print_simulation_percentage()
            if se_failed:
                self.counters.error_se_decoding += 1
                if de_failed:
                    self.counters.error_de_decoding += 1

    def _patterns(self) -> Iterator[tuple[int, ...]]:
        return combinations(range(self.elemento_inicial, self.num_elements_lpc), self.num_errors)

    def _error_generator_parallel(self) -> None:
        """Mesmo resultado, fatiando as combinações pelos 2 primeiros índices.

        Os contadores são somas, logo independem da ordem. A única diferença
        visível é o progresso, que avança em saltos (ao fim de cada fatia).
        """
        assert self._executor is not None and self.initial_lpc is not None
        prefixes = combinations(range(self.elemento_inicial, self.num_elements_lpc), _SHARD_PREFIX)
        tasks: Iterable[tuple[list[list[int]], tuple[int, ...], int, int, int, int, int]] = (
            (
                self.initial_lpc.D,
                prefix,
                self.num_elements_lpc,
                self.num_errors - _SHARD_PREFIX,
                self.iterations_se,
                int(self.loop_type),
                int(self.correction_model),
            )
            for prefix in prefixes
        )
        for partial in self._executor.map(_decode_shard, tasks, chunksize=4):
            self.counters += partial
            self.print_simulation_percentage()

    def print_simulation_percentage(self) -> None:
        percentage_d = (self.counters.number_of_decodings * 100) / self.num_combinations
        percentage_l = int(percentage_d)  # (long) em Java: trunca em direção a zero
        if self.percentage_lp != percentage_l:
            self.percentage_lp = percentage_l
            print(f"{percentage_l} ", end="", file=self._out, flush=True)

    def print_test_identification(self) -> None:
        model = _label(CorrectionModel, self.correction_model)
        loop = _label(LoopType, self.loop_type)
        loop_part = f" ({loop})" if loop else ""
        print(
            f"\nAlgSE{self.iterations_se}_{model}{loop_part} + AlgDE : #Errors={self.num_errors}",
            file=self._out,
        )

    def print_results(self) -> None:
        c = self.counters
        print(f"\n\tnumberOfDecodigns = {c.number_of_decodings}", file=self._out)
        print(f"\terrorSeDecoding = {c.error_se_decoding}", file=self._out)
        print(f"\terrorDeDecoding = {c.error_de_decoding}", file=self._out, flush=True)

    def run_test(self) -> DecodingCounters:
        """Bloco que se repetia dentro dos laços de ``main`` e ``main2``."""
        self.print_test_identification()
        self.reset_simulation_data()
        self.error_generator()
        self.print_results()
        return self.counters


def _label(enum_cls: type[LoopType] | type[CorrectionModel], value: int) -> str:
    """Rótulo do enum; valor desconhecido -> ``""`` (switch Java sem default)."""
    try:
        return enum_cls(value).label
    except ValueError:
        return ""


# ---------------------------------------------------------------------- #
# Roteiros de execução (antes: main e main2)
# ---------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class SweepConfig:
    """Parâmetros de uma varredura. Os laços seguem a ordem do Java:
    modelo -> laço -> nº de erros -> nº de iterações."""

    correction_models: tuple[CorrectionModel, ...]
    loop_types: tuple[LoopType, ...]
    max_errors: int
    max_iterations: int
    error_interval: tuple[int, int] = (0, NUM_ELEMENTS_LPC)


MAIN_CONFIG = SweepConfig(
    correction_models=(CorrectionModel.DCOC,),
    loop_types=(LoopType.INVERT_LOOP,),
    max_errors=7,
    max_iterations=7,
)
"""Equivalente a ``main``: DCOC + InvertLoop, 0..7 erros, 0..7 iterações."""

MAIN2_CONFIG = SweepConfig(
    correction_models=tuple(CorrectionModel),
    loop_types=tuple(LoopType),
    max_errors=5,
    max_iterations=3,
)
"""Equivalente a ``main2``: todos os modelos e laços, 0..5 erros, 0..3 iterações."""


@dataclass(frozen=True, slots=True)
class TestResult:
    """Uma linha de dados: identificação do teste + seus contadores finais."""

    correction_model: str
    loop_type: str
    num_errors: int
    iterations_se: int
    number_of_decodings: int
    error_se_decoding: int
    error_de_decoding: int


def run_sweep(
    config: SweepConfig,
    system: LpcSimulationSystem,
    on_result: Callable[[TestResult], None] | None = None,
) -> None:
    system.set_initial_lpc()
    system.set_error_interval(*config.error_interval)  # default (0, 48): todos os bits
    for model in config.correction_models:
        system.set_correction_model(model)
        for loop_type in config.loop_types:
            system.set_loop_type(loop_type)
            for number_of_errors in range(config.max_errors + 1):
                system.set_number_of_errors(number_of_errors)
                for number_of_iterations in range(config.max_iterations + 1):
                    system.set_iterations_se(number_of_iterations)
                    counters = system.run_test()
                    if on_result is not None:
                        on_result(
                            TestResult(
                                correction_model=_label(CorrectionModel, model),
                                loop_type=_label(LoopType, loop_type),
                                num_errors=number_of_errors,
                                iterations_se=number_of_iterations,
                                number_of_decodings=counters.number_of_decodings,
                                error_se_decoding=counters.error_se_decoding,
                                error_de_decoding=counters.error_de_decoding,
                            )
                        )


def make_executor(workers: int) -> ProcessPoolExecutor | None:
    """``workers <= 1`` -> ``None`` (sequencial, saída idêntica ao Java)."""
    return ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
