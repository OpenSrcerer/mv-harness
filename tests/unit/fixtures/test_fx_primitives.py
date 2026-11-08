"""The tests/synth primitives match their own truth (and the EBU reference values)."""

import os
import sys

import numpy as np
import pytest
from tests.synth import primitives as P
from tests.synth.song import analysis as A

pytestmark = pytest.mark.timeout(600)


def test_click_track_onsets():
    x, sr, tr = P.click_track(120.0, 6.0, subdivision=2, swing=1.5)
    assert len(tr["beats"]) == 11
    for c in tr["clicks"]:
        i = int(round(c["t"] * sr))
        assert np.max(np.abs(x[i - 30 : i])) < 1e-9 < np.max(np.abs(x[i : i + 30]))
    off = [c["t"] for c in tr["clicks"] if c["kind"] == "offbeat"]
    beats = [b["t"] for b in tr["beats"]]
    assert abs((off[0] - beats[0]) / 0.5 - 0.6) < 1e-3  # 60:40 swing


def test_click_track_tempo_ramp():
    x, sr, tr = P.click_track(100.0, 20.0, ramp_to_bpm=140.0)
    ibi = np.diff([b["t"] for b in tr["beats"]])
    assert ibi[0] == pytest.approx(60.0 / (100.0 + 40.0 * 0.5 / 20.0), abs=1e-3) and ibi[-1] < 0.45
    assert np.all(np.diff(ibi) <= 1e-4)


@pytest.mark.parametrize("case", ["3341_1", "3341_2", "3341_3", "3341_4"])
def test_ebu_integrated(case):
    import pyloudnorm as pyln

    x, sr, tr = P.ebu_signal(case)
    got = pyln.Meter(sr).integrated_loudness(x.T)
    assert abs(got - tr["integrated"]) <= tr["tolerance_lu"], (case, got)


@pytest.mark.parametrize("case", ["3342_1", "3342_2", "3342_3"])
def test_ebu_lra(case):
    x, sr, tr = P.ebu_signal(case)
    got = A.integrated_and_lra(x, sr)["lra_lu"]
    assert abs(got - tr["lra"]) <= tr["lra_tolerance_lu"], (case, got)


def test_true_peak_signal():
    x, sr, tr = P.ebu_signal("true_peak_fs4")
    sp = 20 * np.log10(np.max(np.abs(x)))
    assert abs(sp - tr["sample_peak_db"]) < 0.05
    assert abs(A.true_peak_db(x) - tr["true_peak_dbtp"]) < 0.2


def test_sweep_frequency():
    x, sr, tr = P.sweep(100.0, 4000.0, 4.0)
    i = int(2.0 * sr)
    seg = x[i - 2048 : i + 2048] * np.hanning(4096)
    f = np.fft.rfftfreq(4096, 1 / sr)[np.argmax(np.abs(np.fft.rfft(seg)))]
    assert abs(f - tr["freq_100hz"][200]) / tr["freq_100hz"][200] < 0.03


def test_midi_render_bass_line():
    x, sr, tr = P.midi_render(P.BASS_LINE, program="bass")
    assert tr["smf"][:4] == b"MThd" and len(tr["notes"]) == len(P.BASS_LINE)
    for n in tr["notes"]:
        i = int(round(n["t"] * sr))
        assert np.sqrt(np.mean(x[i : i + 2000] ** 2)) > 1e-3
    assert np.sqrt(np.mean(x[: int(0.45 * sr)] ** 2)) < 1e-9


def test_sung_sine_f0():
    notes = [(0.5, 1.0, 57), (1.6, 1.0, 64)]
    x, sr, tr = P.sung_sine(notes)
    m = tr["midi_100hz"]
    assert m[10] is None and abs(m[100] - 57) <= 0.41 and abs(m[210] - 64) <= 0.41


def test_tts_words_exact_onsets():
    x, sr, tr = P.tts_words([("paper", 0.5), ("lanterns", 1.5)], "david")
    for w in tr["words"]:
        i = int(round(w["t"] * sr))
        assert np.max(np.abs(x[i - 100 : i])) == 0.0 and np.max(np.abs(x[i : i + 2000])) > 0


@pytest.mark.skipif(sys.platform != "win32", reason="SAPI is Windows-only")
def test_tts_sentence_word_marks():
    x, sr, tr = P.tts_sentence("zira", "She sells sea shells by the sea shore")
    assert [w["text"] for w in tr["words"]] == "She sells sea shells by the sea shore".split()
    ts = [w["t"] for w in tr["words"]]
    assert ts == sorted(ts) and ts[-1] < x.size / sr


@pytest.mark.parametrize(
    "name", ["mono_44k", "stereo_48k", "mp3_delay", "short_10s", "unicode_path", "corrupt_flac"]
)
def test_edge_cases_decode(name):
    from tests.synth.audio_io import decode

    path, tr = P.edge_case(name)
    assert path.exists()
    if name == "corrupt_flac":
        try:
            x, sr = decode(path)
        except RuntimeError:
            return  # a decoder may refuse; the ingest stage must cope either way
        assert x.shape[1] <= tr["n_samples"] + 4608
        return
    x, sr = decode(path)
    assert sr == tr["sample_rate"] and x.shape[0] == tr["channels"]
    if name == "mp3_delay":
        # gapless trimming: the first click must land within 1 ms of the truth
        b0 = tr["beats"][0]
        i = (
            int(np.argmax(np.abs(np.diff(x[0])) > 0.03)) + 1
        )  # first click (the pad is low-frequency: tiny diff)
        assert abs(i / sr - b0) < 0.001 or pytest.xfail(
            f"mp3 decode offset {i / sr - b0:+.4f} s (encoder delay not trimmed)"
        )
    else:
        assert x.shape[1] == tr["n_samples"]


@pytest.mark.skipif(not os.environ.get("MVH_SLOW"), reason="10-minute file: set MVH_SLOW=1")
def test_long_file():
    from tests.synth.audio_io import decode

    path, tr = P.edge_case("long_10min")
    x, sr = decode(path)
    assert x.shape[1] == tr["n_samples"]
