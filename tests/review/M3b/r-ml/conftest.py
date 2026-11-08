# ruff: noqa: E501  (long docstrings)
"""Fixtures for the R-ML review tests of M3b (notes, vocals, instruments). Owner: reviewer r-ml-m3b.

Synthetic inputs only. Real models (basic-pitch, CED, CLAP, RMVPE) run inside a machine-wide heavy slot
(``mvh.testing.heavy``); every test here is short (a few seconds of model time). The ``real`` marker only labels
model use, as in tests/review/M4/r-ml: these tests run in the gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_configure(config):
    config.addinivalue_line("markers", "real: uses real models (heavy slot)")


@pytest.fixture(scope="session")
def clap():
    from mvh.runner import models
    from mvh.stages.instruments.clap import Clap

    try:
        files = dict(models.handle("clap_larger_music_speech_onnx").files)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"CLAP model unavailable: {e}")
    return Clap(files, threads=3)
