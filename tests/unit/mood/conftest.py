# ruff: noqa: E501  (long literals and docstrings)
"""Fixtures for the mood tests. Tests marked ``real`` run the Essentia ONNX heads inside a heavy slot."""
from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real: uses real models or real songs (heavy)")
    config.addinivalue_line("markers", "slow: takes more than ~10 s")


@pytest.fixture(scope="session")
def heads():
    from mvh.runner import models
    from mvh.stages.mood import core as M

    try:
        mus = models.handle("essentia_msd_musicnn")
        eff = models.handle("essentia_discogs_effnet")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Essentia models unavailable: {e}")
    return M.Heads(mus.files, eff.files, threads=3)
