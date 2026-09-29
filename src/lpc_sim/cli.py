"""Linha de comando.

No Eclipse, trocar de cenário exigia editar ``main`` ou renomear ``main2``.
Aqui os dois cenários viram *presets* e qualquer parâmetro pode ser
sobrescrito por argumento, sem mexer no código.

Exemplos::

    python -m lpc_sim                          # igual ao main() do Java
    python -m lpc_sim --preset main2           # igual ao main2() do Java
    python -m lpc_sim --max-errors 3 --max-iterations 2
    python -m lpc_sim --workers 0              # paralelo, usa todos os núcleos
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import dataclasses
import os
import random
import sys
from collections.abc import Callable, Sequence
from enum import IntEnum

from .enums import CorrectionModel, LoopType
from .exceptions import LpcError
from .lpc_with_error import NUM_ELEMENTS_LPC
from .simulation_system import (
    MAIN2_CONFIG,
    MAIN_CONFIG,
    LpcSimulationSystem,
    SweepConfig,
    TestResult,
    make_executor,
    run_sweep,
)
from .training_data import DEFAULT_FILE_NAME, LAYOUTS, count_rows, write_training_data

PRESETS: dict[str, SweepConfig] = {"main": MAIN_CONFIG, "main2": MAIN2_CONFIG}

MAX_TRAINING_ROWS = 5_000_000
"""Acima disso (~10 min e ~1 GB), ``--dados-treinamento`` exige ``--forcar``."""


def _non_negative(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("deve ser >= 0")
    return value


def _enum_arg(enum_cls: type[LoopType] | type[CorrectionModel]) -> Callable[[str], IntEnum]:
    def parse(text: str) -> IntEnum:
        try:
            return enum_cls.from_label(text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    parse.__name__ = enum_cls.__name__  # usado por argparse nas mensagens de erro
    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lpc_sim",
        description="Simulação exaustiva de decodificação do código LPC 4x4 (AlgSE + AlgDE).",
    )
    parser.add_argument("--preset", choices=PRESETS, default="main", help="cenário base (padrão: main)")
    parser.add_argument(
        "--correction-model",
        nargs="+",
        type=_enum_arg(CorrectionModel),
        metavar="MODELO",
        help="DCO, DCOC, DRC, DRCC ou 0..3 (aceita vários)",
    )
    parser.add_argument(
        "--loop-type",
        nargs="+",
        type=_enum_arg(LoopType),
        metavar="LACO",
        help="BasicLoop, InvertLoop, PriorityLoop, FairPriorityLoop ou 0..3 (aceita vários)",
    )
    parser.add_argument("--max-errors", type=_non_negative, help="nº máximo de erros (inclusive)")
    parser.add_argument("--max-iterations", type=_non_negative, help="nº máximo de iterações SE (inclusive)")
    parser.add_argument(
        "--error-interval",
        nargs=2,
        type=_non_negative,
        metavar=("INICIO", "FIM"),
        help=f"posições [INICIO, FIM) sujeitas a erro (padrão: 0 {NUM_ELEMENTS_LPC})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="processos paralelos; 1 = sequencial (saída idêntica ao Java); 0 = todos os núcleos",
    )
    parser.add_argument(
        "--csv",
        metavar="ARQUIVO",
        help="salva os contadores de cada teste em CSV (modelo, laço, nº de erros, nº de "
        "iterações, decodificações, falhas SE, falhas DE)",
    )
    training = parser.add_argument_group(
        "dados de treinamento",
        "Em vez da simulação, gera uma linha por decodificação (palavra recebida de 48 bits + rótulo 1/-1) "
        "e acrescenta ao arquivo. Usa os mesmos modelos, laços, nº de erros e iterações da varredura.",
    )
    training.add_argument(
        "--dados-treinamento",
        nargs="?",
        const=DEFAULT_FILE_NAME,
        metavar="ARQUIVO",
        help=f'arquivo de saída (padrão: "{DEFAULT_FILE_NAME}"); as linhas são acrescentadas',
    )
    training.add_argument(
        "--layout",
        choices=LAYOUTS,
        default="matriz",
        help="ordem dos 48 bits: matriz = cada linha D+Cr+Pr, depois Cc e Pc; blocos = D, Cr, Pr, Cc, Pc",
    )
    training.add_argument(
        "--dados-aleatorios",
        action="store_true",
        help="usa um D aleatório em cada padrão, em vez da matriz de zeros",
    )
    training.add_argument("--semente", type=int, help="semente do gerador aleatório (reprodutibilidade)")
    training.add_argument(
        "--forcar",
        action="store_true",
        help=f"permite gerar mais de {MAX_TRAINING_ROWS:,} linhas".replace(",", "."),
    )
    return parser


def config_from_args(args: argparse.Namespace) -> SweepConfig:
    config = PRESETS[args.preset]
    overrides: dict[str, object] = {}
    if args.correction_model:
        overrides["correction_models"] = tuple(args.correction_model)
    if args.loop_type:
        overrides["loop_types"] = tuple(args.loop_type)
    if args.max_errors is not None:
        overrides["max_errors"] = args.max_errors
    if args.max_iterations is not None:
        overrides["max_iterations"] = args.max_iterations
    if args.error_interval is not None:
        start, end = args.error_interval
        if not start <= end <= NUM_ELEMENTS_LPC:
            raise SystemExit(f"--error-interval inválido: exige 0 <= INICIO <= FIM <= {NUM_ELEMENTS_LPC}")
        overrides["error_interval"] = (start, end)
    return dataclasses.replace(config, **overrides)  # type: ignore[arg-type]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = config_from_args(args)
    if args.dados_treinamento:
        return _training_main(args, config)
    workers = args.workers if args.workers > 0 else (os.cpu_count() or 1)

    executor = make_executor(workers)
    try:
        with contextlib.ExitStack() as stack:
            on_result: Callable[[TestResult], None] | None = None
            if args.csv:
                csv_file = stack.enter_context(open(args.csv, "w", newline="", encoding="utf-8"))
                writer = csv.writer(csv_file)
                writer.writerow([field.name for field in dataclasses.fields(TestResult)])

                def on_result(result: TestResult) -> None:
                    writer.writerow(dataclasses.astuple(result))

            run_sweep(config, LpcSimulationSystem(executor=executor), on_result=on_result)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.", file=sys.stderr)
        return 130
    except BrokenPipeError:  # ex.: saída redirecionada para ``head``
        sys.stderr.close()
        return 0
    except LpcError as exc:
        print(f"\nErro: {exc}", file=sys.stderr)
        return 1
    finally:
        if executor is not None:
            executor.shutdown(cancel_futures=True)
    return 0


def _training_main(args: argparse.Namespace, config: SweepConfig) -> int:
    """``--dados-treinamento``: sequencial (``--workers`` não se aplica)."""
    expected = count_rows(config)
    if expected > MAX_TRAINING_ROWS and not args.forcar:
        print(
            f"Erro: a varredura geraria {expected:,} linhas (limite {MAX_TRAINING_ROWS:,}). Reduza "
            "--max-errors/--max-iterations/--correction-model/--loop-type ou use --forcar.".replace(",", "."),
            file=sys.stderr,
        )
        return 1
    rng = random.Random(args.semente) if args.dados_aleatorios else None
    print(f"Gerando {expected:,} linhas em '{args.dados_treinamento}'...".replace(",", "."), flush=True)
    try:
        total, failures = write_training_data(
            args.dados_treinamento, config, layout=args.layout, rng=rng, progress=sys.stdout
        )
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário (as linhas já gravadas permanecem no arquivo).", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(f"Total: {total} linhas ({total - failures} com rótulo 1, {failures} com rótulo -1)")
    return 0
