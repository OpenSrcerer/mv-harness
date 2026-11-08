# ruff: noqa: E501
"""R-DSP M2 finding F2 (major): the rhythm stage crashes on any input shorter than about 6 s, and choreo crashes on
inputs shorter than 2 s.

* rhythm: ``fusion.metrical_evidence`` sizes its analysis window as max(6 s, 4 beats) and indexes the padded drum
  envelope up to that window even when the song is shorter (IndexError); ``tempogram_peaks`` subtracts a 1 s moving
  average with ``np.convolve(..., mode='same')`` that returns the *kernel* length for inputs < 1 s (ValueError).
  The 3 s 48 kHz tone the runtime tests use (tests/conftest.py ``tone48``) and a 4-5 s click track both crash, so
  once the stub is replaced every downstream stage (harmony, dynamics, structure, choreo, cues, ...) fails too.
* choreo: the movement-density smoothing ``np.convolve(dens, hanning(201), mode='same')`` returns 201 samples for a
  song shorter than 2.01 s and the broadcast with the intensity curve fails (ValueError).

The fast DSP tracker path (use_models=False) reaches the same fusion code as the model path."""
import numpy as np
import pytest
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import audio_fixture, doc, events
from tests.synth.primitives import click_track


@pytest.mark.parametrize("dur", [3.0, 4.0, 5.0])
def test_rhythm_survives_short_click_tracks(tmp_path, dur):
    x, sr, tr = click_track(120.0, dur)
    fx = audio_fixture(tmp_path / "fx", x, sr)
    res, _, _ = run_stage("rhythm", fx, tmp_path / "rhythm", params={"use_models": False})
    assert res.status in ("ok", "degraded")
    beats = events(tmp_path / "rhythm", "beats")
    assert len(beats) >= 2
    assert abs(doc(tmp_path / "rhythm", "meta/tempo.json")["bpm"] - 120.0) <= 2.0


def test_rhythm_survives_the_runtime_tone_fixture(tmp_path):
    from mvh import testing
    from mvh.io import audio as aio

    p = testing.tone(tmp_path / "tone" / "t.flac", seconds=3.0, sr=48000)   # = tests/conftest.py tone48
    d = aio.decode(p)
    fx = audio_fixture(tmp_path / "fx", d.samples, d.sr)
    res, _, _ = run_stage("rhythm", fx, tmp_path / "rhythm", params={"use_models": False})
    assert res.status in ("ok", "degraded")
    regions = events(tmp_path / "rhythm", "pulse_regions")
    assert regions and regions[0]["t"] == 0.0


def test_choreo_survives_a_sub_two_second_song(tmp_path):
    x, sr, _ = click_track(120.0, 1.0)
    fx = audio_fixture(tmp_path / "fx", np.asarray(x), sr)
    run_stage("rhythm", fx, tmp_path / "rhythm", params={"use_models": False})
    run_stage("structure", fx, tmp_path / "structure", overlays={"rhythm": tmp_path / "rhythm"})
    res, _, _ = run_stage("choreo", fx, tmp_path / "choreo",
                          overlays={"rhythm": tmp_path / "rhythm", "structure": tmp_path / "structure"})
    assert res.status in ("ok", "degraded")
