"""Simulador de decodificação do código de produto LPC 4x4 (conversão do projeto Java)."""

from .decoder_lpc import decoding_de, decoding_se
from .enums import CorrectionModel, LoopType
from .exceptions import InvalidErrorPositionError, LpcError
from .lpc import Lpc
from .lpc_with_error import NUM_ELEMENTS_LPC, LpcWithError, LpcWithErrror
from .simulation_system import (
    MAIN2_CONFIG,
    MAIN_CONFIG,
    DecodingCounters,
    LpcSimulationSystem,
    SweepConfig,
    TestResult,
    decode_pattern,
    run_sweep,
)

__all__ = [
    "MAIN2_CONFIG",
    "MAIN_CONFIG",
    "NUM_ELEMENTS_LPC",
    "CorrectionModel",
    "DecodingCounters",
    "InvalidErrorPositionError",
    "Lpc",
    "LpcError",
    "LpcSimulationSystem",
    "LpcWithErrror",
    "LpcWithError",
    "LoopType",
    "SweepConfig",
    "TestResult",
    "decode_pattern",
    "decoding_de",
    "decoding_se",
    "run_sweep",
]

__version__ = "1.0.0"
