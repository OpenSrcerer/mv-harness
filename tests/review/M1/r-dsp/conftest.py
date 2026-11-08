"""Fixtures for the R-DSP review tests of M1 (spectral, loudness, dynamics). Synthetic inputs only (the
contract fixture song in tests/contract/synth and one-shots from tests/synth/dsp); no models."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rdsp_m1_support import SYNTH, have_viz  # noqa: E402


@pytest.fixture(scope="session")
def synth_ok() -> None:
    if not (SYNTH / "_intermediate" / "ingest" / "canonical.wav").is_file():
        pytest.skip("tests/contract/synth is not built")


@pytest.fixture(scope="session")
def viz_ok() -> None:
    if not have_viz():
        pytest.skip("needs node and viz/js/audio.js")
