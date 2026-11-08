# ruff: noqa: E501
"""Shared marker setup for the M5 unit-test folders (each folder's conftest.py calls these).

* ``models``: synthetic inputs through real models (faster-whisper, MMS_FA, ECAPA, Rhubarb) inside a heavy slot;
  run by default (the PLAN §7 thresholds are asserted there); skip with ``MVH_SKIP_MODELS=1``.
* ``real``: the four real songs (tests/contract/real-*); opt-in with ``-m real`` or ``MVH_REAL_TESTS=1``.
"""

from __future__ import annotations

import os

import pytest


def configure(config) -> None:
    config.addinivalue_line("markers", "models: synthetic inputs through real models in a heavy slot (MVH_SKIP_MODELS=1 skips)")
    config.addinivalue_line("markers", "real: the real songs (opt-in: -m real or MVH_REAL_TESTS=1)")


def modify(config, items) -> None:
    want_real = os.environ.get("MVH_REAL_TESTS") == "1" or "real" in (config.getoption("-m") or "")
    skip_models = os.environ.get("MVH_SKIP_MODELS") == "1"
    for it in items:
        if "real" in it.keywords and not want_real:
            it.add_marker(pytest.mark.skip(reason="real-song test: run with -m real or MVH_REAL_TESTS=1"))
        elif "models" in it.keywords and skip_models:
            it.add_marker(pytest.mark.skip(reason="MVH_SKIP_MODELS=1"))
