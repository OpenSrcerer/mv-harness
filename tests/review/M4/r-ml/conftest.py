"""Fixtures for the R-ML review tests of M4 (harmony, mood). Synthetic inputs only; the real models
(S-KEY ONNX, the Essentia ONNX heads, lv-chordia) run inside a heavy slot (mvh.testing.heavy)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_configure(config):
    config.addinivalue_line("markers", "real: uses real models (heavy slot)")


@pytest.fixture(scope="session")
def skey():
    from mvh.runner import models
    from mvh.stages.harmony import keys as K

    try:
        h = models.handle("skey_onnx")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"S-KEY model unavailable: {e}")
    return K.SKey(h.files["skey/skey.onnx"], h.files["skey/config.json"], threads=3)
