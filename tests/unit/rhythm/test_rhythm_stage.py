"""The rhythm stage end to end on synthetic click tracks (PLAN §7: beats F1 >= 0.98 at +-70 ms, tempo error <= 0.5
BPM). Fast tests use the DSP tracker path (``use_models=False``: PLP + onset activation into the same fusion);
``slow`` tests run beat_this + madmom on the click tracks and on the synthetic song."""
import numpy as np
import pytest
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import audio_fixture, doc, events, validate_all
from tests.synth.primitives import click_track

from mvh.stages.rhythm.fusion import f_measure

DSP = {"use_models": False}


def _run(tmp_path, x, sr, params=None, overrides=None, name="rhythm"):
    fx = audio_fixture(tmp_path / "fx", x, sr)
    res, ctx, _ = run_stage("rhythm", fx, tmp_path / name, params=params, overrides=overrides)
    return res, tmp_path / name


def _score(out, tr):
    beats = events(out, "beats")
    ref = np.array([b["t"] for b in tr["beats"]])
    est = np.array([b["t"] for b in beats if b["in_pulse"]])
    tempo = doc(out, "meta/tempo.json")
    return f_measure(est, ref, 0.07), tempo, beats


@pytest.mark.parametrize("bpm", [90.0, 120.0, 140.0])
def test_clicks_dsp_f1_and_tempo(tmp_path, bpm):
    x, sr, tr = click_track(bpm, 30.0)
    res, out = _run(tmp_path, x, sr, DSP)
    f, tempo, beats = _score(out, tr)
    assert f >= 0.98, f
    assert abs(tempo["bpm"] - bpm) <= 0.5, tempo["bpm"]
    assert tempo["meter"]["beats_per_bar"] in (3, 4)
    assert validate_all(out) == []
    # D11: the grid covers the song, every beat is indexed 0..n-1, curves have the right length
    assert [b["beat_index"] for b in beats] == list(range(len(beats)))
    regions = events(out, "pulse_regions")
    assert regions[0]["t"] == 0.0 and abs(regions[-1]["t"] + regions[-1]["d"] - 30.0) < 1e-3


def test_clicks_dsp_swing_and_ramp(tmp_path):
    x, sr, tr = click_track(110.0, 30.0, subdivision=2, swing=1.5)
    _, out = _run(tmp_path, x, sr, DSP, name="swing")
    f, tempo, _ = _score(out, tr)
    assert f >= 0.98 and abs(tempo["bpm"] - 110.0) <= 0.5
    x, sr, tr = click_track(100.0, 40.0, ramp_to_bpm=120.0)
    _, out = _run(tmp_path, x, sr, DSP, name="ramp")
    f, tempo, _ = _score(out, tr)
    assert f >= 0.98, f
    segs = events(out, "tempo_segments")
    assert tempo["is_variable"] or len(segs) > 1 or not all(s["stable"] for s in segs)


def test_no_pulse_gap_gets_virtual_beats(tmp_path):
    x1, sr, tr1 = click_track(120.0, 12.0)
    gap = np.zeros(int(4.0 * sr))
    x2, _, tr2 = click_track(120.0, 12.0)
    x = np.concatenate([x1, gap, x2])
    _, out = _run(tmp_path, x, sr, DSP)
    beats = events(out, "beats")
    virt = [b for b in beats if not b["in_pulse"] and 12.5 < b["t"] < 15.5]
    assert len(virt) >= 5
    ibi = np.diff([b["t"] for b in beats if 11.0 < b["t"] < 17.0])
    assert np.allclose(ibi, 0.5, atol=0.03)
    pr = events(out, "pulse_regions")
    assert any((not r["in_pulse"]) and r["t"] < 13.0 and r["t"] + r["d"] > 15.5 for r in pr)


def test_overrides_bpm_offset_phase(tmp_path):
    x, sr, tr = click_track(120.0, 20.0)
    fx = audio_fixture(tmp_path / "fx", x, sr)
    _, ctx, _ = run_stage("rhythm", fx, tmp_path / "base", params=DSP)
    base = events(tmp_path / "base", "beats")
    _, ctx, _ = run_stage("rhythm", fx, tmp_path / "dbl", params=DSP, overrides={"rhythm.bpm": 240.0})
    dbl = doc(tmp_path / "dbl", "meta/tempo.json")
    assert abs(dbl["bpm"] - 240.0) < 2.0 and dbl["arbitration"]["forced"] == 240.0
    _, ctx, _ = run_stage("rhythm", fx, tmp_path / "off", params=DSP, overrides={"rhythm.beat_offset_s": 0.05})
    off = events(tmp_path / "off", "beats")
    common = min(len(base), len(off)) - 2
    d = np.median([off[i]["t"] - base[i]["t"] for i in range(1, common)])
    assert abs(d - 0.05) < 0.005
    _, ctx, _ = run_stage("rhythm", fx, tmp_path / "ph", params=DSP, overrides={"rhythm.downbeat_phase": 1})
    ph = events(tmp_path / "ph", "beats")
    db0 = [b["beat_index"] for b in base if b["beat_in_bar"] == 1 and b["in_pulse"]]
    db1 = [b["beat_index"] for b in ph if b["beat_in_bar"] == 1 and b["in_pulse"]]
    assert db0 != db1


# ----------------------------------------------------------------------------------------------- slow: models
@pytest.mark.slow
@pytest.mark.timeout(5400)
def test_synth_song_with_models(tmp_path):
    from tests.synth.m2.score import rhythm_scores
    from tests.synth.m2.testing import synth_ready

    from mvh.testing import heavy

    fx = synth_ready()
    with heavy("pytest-m2-rhythm"):
        res, ctx, secs = run_stage("rhythm", fx, tmp_path / "rhythm", threads=6)
    s = rhythm_scores(tmp_path / "rhythm")
    assert s["f_beats"] >= 0.98, s
    assert s["f_downbeats"] >= 0.95, s
    assert s["tempo_err"] <= 0.5, s
    assert s["median_abs_err_ms"] <= 5.0, s
    assert s["pickup_beats"] == 1 and s["pickup_beat_in_bar"] == 4 and abs(s["pickup_t"] - 0.5) < 0.03, s
    assert s["bar16_beats_in_bar"] == 3 and s["bar16_n"] == 3, s
    assert s["pulse_agreement"] >= 0.9, s
    assert any(not r["in_pulse"] and r["t"] <= 33.0 and r["t"] + r["d"] >= 34.4 for r in events(tmp_path / "rhythm", "pulse_regions"))
    assert validate_all(tmp_path / "rhythm") == []


@pytest.mark.slow
@pytest.mark.timeout(5400)
def test_clicks_with_models(tmp_path):
    from mvh.testing import heavy

    x, sr, tr = click_track(128.0, 30.0)
    fx = audio_fixture(tmp_path / "fx", x, sr)
    with heavy("pytest-m2-rhythm"):
        res, ctx, secs = run_stage("rhythm", fx, tmp_path / "rhythm", threads=6)
    f, tempo, _ = _score(tmp_path / "rhythm", tr)
    assert f >= 0.98 and abs(tempo["bpm"] - 128.0) <= 0.5
