"""R-WORDS review tests of M5 (identity, lyrics, voices, lipsync). Markers as in the M5 unit tests
(tests/synth/m5/pytest_markers.py): ``models`` = synthetic inputs through real models in a heavy slot (default on,
MVH_SKIP_MODELS=1 skips); ``real`` = real songs (opt-in). Only the synthetic fixture's invented lyrics appear here."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tests.synth.m5 import pytest_markers as _m  # noqa: E402


def pytest_configure(config):
    _m.configure(config)


def pytest_collection_modifyitems(config, items):
    _m.modify(config, items)
