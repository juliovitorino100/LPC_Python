"""Permite ``python -m lpc_sim`` (substitui o ``public static void main`` do Java)."""

import sys

from .cli import main

if __name__ == "__main__":  # necessário para ProcessPoolExecutor no Windows/macOS (spawn)
    sys.exit(main())
