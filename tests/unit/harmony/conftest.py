# ruff: noqa: E501  (long literals and docstrings)
"""Fixtures for the harmony tests. Tests marked ``real`` run real models (S-KEY ONNX, lv-chordia) inside a heavy slot."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
SYNTH = ROOT / "tests" / "contract" / "synth"


def pytest_configure(config):
    config.addinivalue_line("markers", "real: uses real models or real songs (heavy)")
    config.addinivalue_line("markers", "slow: takes more than ~10 s")


@pytest.fixture(scope="session")
def skey():
    from mvh.runner import models
    from mvh.stages.harmony import keys as K

    try:
        h = models.handle("skey_onnx")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"S-KEY model unavailable: {e}")
    return K.SKey(h.files["skey/skey.onnx"], h.files["skey/config.json"], threads=3)


@pytest.fixture(scope="session")
def synth_song():
    """(y22, truth chords, beats, bars, duration) of the contract synthetic song."""
    if not (SYNTH / "meta" / "source.json").exists():
        pytest.skip("tests/contract/synth is not built")
    from mvh.io import audio as aio

    src = json.loads((SYNTH / "meta" / "source.json").read_text(encoding="utf-8"))
    d = aio.decode(SYNTH / "_truth" / "synth-song.flac", sr=22050, mono=True)

    def ev(n):
        return json.loads((SYNTH / "events" / f"{n}.json").read_text(encoding="utf-8"))["items"]

    return {"y": np.asarray(d.samples, np.float32).reshape(-1), "chords": ev("chords"), "beats": ev("beats"), "bars": ev("bars"),
            "duration": src["n_samples"] / src["sample_rate"], "n_curve": math.ceil(src["n_samples"] * 100 / src["sample_rate"])}
