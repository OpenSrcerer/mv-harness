# ruff: noqa: E501  (long formulas, tables and docstrings)
"""loudness stage: EBU Tech 3341 / 3342 conformance (PLAN §7: +-0.1 LU; LRA +-1 LU per Tech 3342), true peak, the
ffmpeg ebur128 cross-check (+-0.5 LU), the centred curve convention, the RMS/peak/crest curves and the contract output."""

from __future__ import annotations

import math

import numpy as np
import pytest
from tests.synth.m1.harness import run_m1
from tests.synth.m1.markers import REAL_SONGS, real_available, real_dir
from tests.synth.m1.signals import groove
from tests.synth.primitives import ebu_signal

from mvh.contract.conventions import n_curve_frames
from mvh.stages.loudness import r128


def _measure(x, sr):
    xk = r128.k_weight(x, sr)
    z = r128.weighted_power(xk)
    return z, r128.loudness_curves(z, sr, x.shape[1])


@pytest.mark.parametrize("sr", [48000, 44100])
@pytest.mark.parametrize("case", ["3341_1", "3341_2", "3341_3", "3341_4"])
def test_ebu_3341_integrated(case, sr):
    x, sr, truth = ebu_signal(case, sr=sr)
    got = r128.integrated(x, sr)
    assert abs(got - truth["integrated"]) <= 0.1, (case, got)
    if "momentary" in truth:
        _, c = _measure(x, sr)
        n = c["momentary"].size
        core = slice(int(0.25 * n), int(0.75 * n))
        assert np.all(np.abs(c["momentary"][core] - truth["momentary"]) <= 0.1)
        assert np.all(np.abs(c["short_term"][core] - truth["short_term"]) <= 0.1)


@pytest.mark.parametrize("case", ["3342_1", "3342_2", "3342_3"])
def test_ebu_3342_lra(case):
    x, sr, truth = ebu_signal(case, sr=48000)
    z, _ = _measure(x, sr)
    got = r128.loudness_range(z, sr)["lra_lu"]
    assert abs(got - truth["lra"]) <= 1.0, (case, got)  # EBU Tech 3342 tolerance
    assert abs(got - truth["lra"]) <= 0.2, (case, got)  # what this implementation achieves


def test_true_peak_intersample():
    x, sr, truth = ebu_signal("true_peak_fs4", sr=44100)
    tp = r128.db(r128.true_peak(x, sr))
    sp = r128.db(float(np.max(np.abs(x))))
    assert abs(tp - truth["true_peak_dbtp"]) <= 0.2, tp
    assert abs(sp - truth["sample_peak_db"]) <= 0.05, sp


def test_centred_curves():
    """A 1 kHz tone (-23 dBFS per channel) starting at 5 s: the centred 0.4 s window at t = 5.0 holds half the energy
    (-3.01 LU), and a spec (trailing) meter shows that value 0.2 s later (curve_offsets_s)."""
    sr = 48000
    x = np.zeros((2, sr * 10))
    t = np.arange(sr * 5) / sr
    tone = 10 ** (-23 / 20) * np.sin(2 * np.pi * 1000 * t)
    x[:, sr * 5 :] = tone
    _, c = _measure(x, sr)
    assert abs(c["momentary"][500] - (-23.0 - 3.0103)) < 0.1
    assert abs(c["momentary"][520] - (-23.0)) < 0.1  # window [5.0, 5.4) is all tone
    assert c["momentary"][470] == r128.LUFS_FLOOR
    assert abs(c["short_term"][500] - (-23.0 - 3.0103)) < 0.1


def test_level_curves():
    sr = 44100
    t = np.arange(sr * 2) / sr
    x = np.vstack([np.sin(2 * np.pi * 440 * t)] * 2)
    x[:, sr:] = 0.0
    lv = r128.level_curves(x, sr, 2048)
    assert abs(lv["rms_db"][50] - (-3.0103)) < 0.05
    assert abs(lv["peak_db"][50]) < 0.01
    assert abs(lv["crest_db"][50] - 3.0103) < 0.05
    assert lv["rms_db"][150] == r128.DB_FLOOR and lv["crest_db"][150] == 0.0
    # the peak window is centred: a single spike at 1.5 s shows in the frames whose 46 ms window contains it
    y = np.zeros((2, sr * 2))
    y[0, int(1.5 * sr)] = 0.5
    pk = r128.level_curves(y, sr, 2048)["peak_db"]
    hit = np.flatnonzero(pk > -120)
    assert hit.min() == 148 and hit.max() == 152


def test_clipping_count():
    x = np.zeros((2, 1000))
    x[0, 10:15] = 1.0
    x[1, 20] = -1.0
    assert r128.clipped_samples(x) == 6


def test_parse_ebur128_summary():
    txt = ("[Parsed_ebur128_0 @ 000] Summary:\n\n  Integrated loudness:\n    I:         -20.4 LUFS\n"
           "    Threshold: -30.5 LUFS\n\n  Loudness range:\n    LRA:         7.2 LU\n    Threshold: -40.5 LUFS\n"
           "    LRA low:   -25.0 LUFS\n    LRA high:  -17.8 LUFS\n\n  True peak:\n    Peak:        -1.0 dBFS\n")
    assert r128.parse_ebur128(txt) == {"integrated_lufs": -20.4, "lra_lu": 7.2, "true_peak_dbtp": -1.0}


# ------------------------------------------------------------------------------------------------ the stage
@pytest.fixture(scope="module")
def groove_loud(tmp_path_factory):
    x, sr, _ = groove(duration_s=20.0)
    d = tmp_path_factory.mktemp("loud")
    r = run_m1(x, sr, d, stages=("spectral", "loudness"))
    return r, x, sr


def test_stage_outputs_and_ffmpeg_crosscheck(groove_loud):
    r, x, sr = groove_loud
    ctx = r["ctx"]["loudness"]
    doc = ctx.written_json("meta/loudness.json")
    for k in ("integrated_lufs", "lra_lu", "lra_low_lufs", "lra_high_lufs", "true_peak_dbtp", "sample_peak_db", "plr_db"):
        assert isinstance(doc[k], float), k
    assert abs(doc["integrated_lufs"] - r128.integrated(x, sr)) < 1e-3
    assert "ebur128" in doc, r["loudness"].warnings
    assert abs(doc["ebur128"]["diff_lu"]) <= 0.5  # PLAN §7: +-0.5 LU vs ffmpeg
    assert abs(doc["ebur128"]["true_peak_dbtp"] - doc["true_peak_dbtp"]) <= 0.3
    assert doc["true_peak_dbtp"] >= doc["sample_peak_db"]
    assert math.isclose(doc["plr_db"], doc["true_peak_dbtp"] - doc["integrated_lufs"], abs_tol=2e-3)
    assert doc["curve_offsets_s"] == {"momentary": 0.2, "short_term": 1.5}
    assert {"loudest", "quietest", "short_term_percentiles"} <= set(doc)
    ch = ctx.written_curves()
    n = n_curve_frames(x.shape[1], sr)
    assert sorted(ch) == sorted(["loud.momentary", "loud.momentary_lufs", "loud.short_term", "loud.short_term_lufs",
                                 "loud.rms", "loud.rms_db", "loud.peak_db", "loud.crest_db"])
    for cid, v in ch.items():
        assert v.size == n and np.all(np.isfinite(v)), cid
    assert ch["loud.momentary_lufs"].min() >= r128.LUFS_FLOOR and ch["loud.rms_db"].min() >= r128.DB_FLOOR
    assert 0.0 <= ch["loud.short_term"].min() and ch["loud.short_term"].max() <= 1.0
    meta = ctx.written_curve_meta()
    assert {"lo", "hi"} <= set(meta["loud.short_term"]["meta"])


@pytest.mark.parametrize("sr,ch", [(48000, 1), (44100, 6)])
def test_mono_and_surround(sr, ch, tmp_path):
    x, _, truth = ebu_signal("3341_1", sr=sr)
    if ch == 1:
        y = x[:1]  # BS.1770: a mono signal is one channel (no +3 dB dual-mono assumption)
        want = truth["integrated"] - 3.0103
    else:
        y = np.zeros((6, x.shape[1]))
        y[0], y[1] = x[0], x[1]
        y[3] = x[0]  # LFE: excluded
        want = truth["integrated"]
    r = run_m1(y, sr, tmp_path, stages=("spectral", "loudness"))
    doc = r["ctx"]["loudness"].written_json("meta/loudness.json")
    assert abs(doc["integrated_lufs"] - want) <= 0.1, doc["integrated_lufs"]


def test_limited_master_flag(tmp_path):
    x, sr, _ = groove(duration_s=20.0)
    y = np.tanh(6.0 * x) * 0.98  # brick-wall-ish limiting: small LRA, low PLR
    r = run_m1(y, sr, tmp_path, stages=("spectral", "loudness"))
    doc = r["ctx"]["loudness"].written_json("meta/loudness.json")
    assert doc["limited_master"] and "loudness:limited_master" in doc["qa"]


# ------------------------------------------------------------------------------------------------ real songs
@pytest.mark.real
@pytest.mark.slow
@pytest.mark.parametrize("slug", list(REAL_SONGS))
def test_real_song_loudness(slug, tmp_path):
    if not real_available(slug):
        pytest.skip("real fixture missing")
    from mvh.io import audio as aio

    p = real_dir(slug) / "_intermediate" / "ingest" / "canonical.wav"
    d = aio.decode(p)
    r = run_m1(d.samples, d.sr, tmp_path, audio_path=p, stages=("spectral", "loudness"))
    doc = r["ctx"]["loudness"].written_json("meta/loudness.json")
    w0_i, w0_lra, _ = REAL_SONGS[slug]
    assert abs(doc["ebur128"]["diff_lu"]) <= 0.5
    assert abs(doc["integrated_lufs"] - w0_i) <= 0.1
    assert abs(doc["lra_lu"] - w0_lra) <= 0.5
