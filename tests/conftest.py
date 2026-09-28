from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def golden() -> Path:
    return GOLDEN_DIR
