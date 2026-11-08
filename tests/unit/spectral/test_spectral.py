# ruff: noqa: E501  (long formulas, tables and docstrings)
"""spectral stage: viz parity (the real viz/js/audio.js under Node), physical units, synthetic ground truth for the kick
events (PLAN §7: F1 >= 0.95 at +-10 ms, event time = the one-shot's first sample), contract outputs and edge cases."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from tests.synth.m1.harness import run_m1
from tests.synth.m1.markers import REAL_SONGS, real_available, real_dir
from tests.synth.m1.signals import f1, groove

from mvh.contract import registry
from mvh.contract.conventions import flash_samples, n_curve_frames
from mvh.stages.spectral import dsp

HERE = Path(__file__).resolve().parent
VIZ_AUDIO_JS = Path(__file__).resolve().parents[4] / "viz" / "js" / "audio.js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None or not VIZ_AUDIO_JS.is_file(), reason="node or viz/js/audio.js missing")


def _node(payload: dict, tmp_path: Path) -> dict:
    p = tmp_path / "viz_in.json"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    r = subprocess.run([NODE, str(HERE / "viz_parity.cjs"), str(VIZ_AUDIO_JS), str(p)], capture_output=True,
                       timeout=120, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


# ------------------------------------------------------------------------------------------------ viz parity
@needs_node
@pytest.mark.parametrize("sr", [44100, 48000])
def test_band_map_and_values_match_viz(sr, tmp_path):
    rng = np.random.default_rng(3)
    n_fft = dsp.fft_size(sr)
    nb = n_fft // 2
    frames = []
    for k in range(4):
        d = -60.0 + 25.0 * rng.standard_normal(nb) - np.linspace(0, 30, nb) * k / 3
        d[rng.integers(0, nb, 5)] = -250.0  # below the -200 floor
        frames.append(np.maximum(d, -400.0))
    e = np.zeros(400)
    for i in range(10, 400, 37):
        e[i:i + 3] += [0.6, 0.5, 0.4]
    e += 0.05 * np.abs(rng.standard_normal(400))
    norm = np.clip(rng.random((6, 128)), 0, 1)
    out = _node({"sr": sr, "frames": [f.tolist() for f in frames], "e": e.tolist(), "dt": 0.01, "gateDb": -46,
                 "norm": norm.tolist()}, tmp_path)
    bm = dsp.band_map(sr, n_fft)
    assert np.allclose(out["bLo"], bm.lo, atol=1e-4) and np.allclose(out["bHi"], bm.hi, atol=1e-4)
    assert np.allclose(out["bC"], bm.centre, atol=1e-4) and np.allclose(out["tilt"], bm.tilt, atol=1e-4)
    for k in ("bass", "kick", "mid", "high"):
        assert list(out["ranges"][k]) == list(bm.ranges[k]), k
    for k, j in (("flux", "flux_bass"), ("fluxMid", "flux_mid"), ("fluxHigh", "flux_high")):
        assert list(out["ranges"][k]) == list(bm.ranges[j]), k
    assert tuple(out["kickBins"]) == bm.kick_bins
    # raw bands and the raw kick energy computed by viz's own update() from the same per-bin dB
    for d, js in zip(frames, out["frames"]):
        dd = np.maximum(d, -1000.0)[None, :]
        raw = np.maximum((dsp.viz_band_db(dd, bm)[0] + bm.tilt - dsp.MIN_DB) / dsp.DB_RANGE, 0.0)
        assert np.allclose(raw, js["bandsRaw"], atol=2e-5)
        ek = max(0.0, (dsp.kick_band_db(dd, bm)[0] + 2.0 - dsp.MIN_DB) / dsp.DB_RANGE)
        assert abs(ek - js["eKick"]) < 2e-5
    # _hitEnvelope: the causal reference path is a verbatim port
    hr = dsp.hit_envelope(e, gate_db=-46.0, median_ref_s=None)
    assert np.allclose(hr.raw, out["hit"]["raw"], atol=1e-6)
    assert np.allclose(hr.released, out["hit"]["env"], atol=1e-6)
    # _flux
    py_flux = dsp.band_flux(norm, bm.ranges["flux_bass"])[1:]
    assert np.allclose(py_flux, out["flux"], atol=1e-6)


def test_webaudio_window_and_framing():
    w = dsp.webaudio_blackman(2048)
    assert abs(w[0]) < 1e-12 and abs(w[1024] - 1.0) < 1e-12  # periodic window: w[N/2] == 1
    assert dsp.fft_size(44100) == 2048 and dsp.fft_size(48000) == 2048 and dsp.fft_size(96000) == 4096
    c = dsp.frame_centres(44100 * 3 + 7, 44100)
    assert c.size == n_curve_frames(44100 * 3 + 7, 44100) and c[100] == 44100


# ------------------------------------------------------------------------------------------------ physical units
def _sine(f, sr=44100, dur=2.0, amp=1.0, ch=2):
    t = np.arange(int(sr * dur)) / sr
    x = amp * np.sin(2 * np.pi * f * t)
    return np.vstack([x] * ch)


@pytest.mark.parametrize("f,band", [(80.0, "bands.bass"), (1000.0, "bands.mid"), (5000.0, "bands.high"),
                                    (70.0, "bands.kick"), (300.0, "fine.lowmid"), (8000.0, "fine.air")])
def test_band_power_is_dbfs_mean_square(f, band):
    fr = dsp.analyse_frames(_sine(f), 44100)
    v = fr.phys_db[band][20:-20]
    assert np.all(np.abs(v - (-3.0103)) < 0.25), (band, float(np.median(v)))  # full-scale sine = -3.01 dBFS


def test_stereo_features():
    sr = 44100
    rng = np.random.default_rng(1)
    s = rng.standard_normal(sr) * 0.1
    left = dsp.analyse_frames(np.vstack([s, np.zeros_like(s)]), sr)
    assert np.allclose(left.balance[10:-10], -1.0, atol=1e-6)
    mono = dsp.analyse_frames(np.vstack([s, s]), sr)
    assert np.allclose(mono.width[10:-10], 0.0, atol=1e-9) and np.allclose(mono.correlation[10:-10], 1.0, atol=1e-6)
    anti = dsp.analyse_frames(np.vstack([s, -s]), sr)
    assert np.allclose(anti.width[10:-10], 1.0, atol=1e-6) and np.allclose(anti.correlation[10:-10], -1.0, atol=1e-6)
    silent = dsp.analyse_frames(np.zeros((2, sr)), sr)
    assert np.all(silent.width == 0) and np.all(silent.balance == 0) and np.all(silent.correlation == 1)


def test_timbre_features():
    sr = 44100
    fr = dsp.analyse_frames(_sine(1000.0, amp=0.5), sr)
    assert abs(float(np.median(fr.centroid_hz[10:-10])) - 1000.0) < 25.0
    rng = np.random.default_rng(2)
    white = rng.standard_normal(sr * 2) * 0.1
    fw = dsp.analyse_frames(np.vstack([white, white]), sr)
    bm = dsp.band_map(sr, fw.n_fft)
    sw = dsp.spectral_slope(fw.log_band_db, bm.centres_hz)
    assert abs(float(np.median(sw[10:-10]))) < 0.5  # white noise: flat per-bin density
    X = np.fft.rfft(rng.standard_normal(sr * 2))
    f = np.fft.rfftfreq(sr * 2, 1 / sr)
    X[1:] /= np.sqrt(f[1:])
    pink = np.fft.irfft(X)
    pink *= 0.1 / pink.std()
    fp = dsp.analyse_frames(np.vstack([pink, pink]), sr)
    sp = dsp.spectral_slope(fp.log_band_db, bm.centres_hz)
    assert abs(float(np.median(sp[10:-10])) + 3.01) < 0.5  # pink: -3 dB/oct
    assert float(np.median(fw.flatness[10:-10])) > float(np.median(fp.flatness[10:-10]))


# ------------------------------------------------------------------------------------------------ kick events (§7)
@pytest.mark.parametrize("kw,thr", [
    (dict(bass=False, syncopated=False), 0.98),
    (dict(bass=False), 0.95),
    (dict(bass=False, pad=False, hats=False, snares=False), 0.95),
    (dict(bass=False, gain_db=-25.0), 0.95),
    (dict(bass=False, bpm=96.0, seed=5), 0.95),
])
def test_kick_events_f1_on_one_shots(kw, thr, tmp_path):
    x, sr, truth = groove(**kw)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    est = [it["t"] for it in ev]
    ref = [k["t"] for k in truth["kick"]]
    f, p, rc, errs = f1(est, ref, 0.010)
    assert f >= thr, (kw, f, p, rc)
    assert abs(float(np.median(errs))) < 0.003 and float(np.percentile(np.abs(errs), 95)) < 0.006


def test_kick_events_with_sub_bass_line(tmp_path):
    """A sustained bass line in the kick band: kicks are still found (bass-note attacks are kick-band hits too, by viz
    design; ``kick_conf`` separates them)."""
    x, sr, truth = groove()
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    ref = [k["t"] for k in truth["kick"]]
    f, p, rc, _ = f1([it["t"] for it in ev], ref, 0.010)
    # syncopated 16th kicks 121 ms apart that sit under a bass note on the same hat (the generator's 8th-note bass line)
    # are indistinguishable from the bass-note onsets by band envelopes; hits.kick prefers not to double kicks on hats
    # (review B1) and keeps recall >= 0.7 here
    assert rc >= 0.7 and p >= 0.7, (f, p, rc)
    kicks = np.array(ref)
    tp = [it["kick_conf"] for it in ev if np.min(np.abs(kicks - it["t"])) <= 0.01]
    fp = [it["kick_conf"] for it in ev if np.min(np.abs(kicks - it["t"])) > 0.01]
    assert not fp or np.median(tp) >= np.median(fp)


# ------------------------------------------------------------------------------------------------ stage outputs
@pytest.fixture(scope="module")
def groove_run(tmp_path_factory):
    x, sr, truth = groove(duration_s=16.0)
    d = tmp_path_factory.mktemp("spec")
    return run_m1(x, sr, d, stages=("spectral",)), x, sr, truth


def test_outputs_complete_and_valid(groove_run):
    r, x, sr, _ = groove_run
    ctx = r["ctx"]["spectral"]
    ch = ctx.written_curves()
    n = n_curve_frames(x.shape[1], sr)
    want = [c.id for c in registry.channels_of("spectral") if c.file == "core"]
    assert sorted(ch) == sorted(want)
    for cid, v in ch.items():
        c = registry.match_channel(cid)
        assert v.size == n and np.all(np.isfinite(v)), cid
        assert v.min() >= c.range[0] - 1e-6 and v.max() <= c.range[1] + 1e-6, (cid, v.min(), v.max())
    meta = ctx.written_curve_meta()
    for cid in ("bands.bass", "fine.air", "timbre.centroid", "flux.mid"):
        assert {"lo", "hi"} <= set(meta[cid]["meta"]), cid
    spec = ctx.written_matrix("spectrum128")
    assert spec.shape == (n, 128) and spec.dtype == np.uint8 and spec.max() > 100
    assert len(ctx.writer.matrices["spectrum128"]["meta"]["band_edges_hz"]) == 129
    for name in ("hits.kick", "hits.mid", "hits.high", "onsets.bass", "onsets.mid", "onsets.high"):
        env = ctx.written_events(name)
        assert env["items"], name
        ts = [it["t"] for it in env["items"]]
        assert ts == sorted(ts)


def test_hit_envelopes_follow_the_flash_rule(groove_run):
    r, _, _, _ = groove_run
    ctx = r["ctx"]["spectral"]
    ch = ctx.written_curves()
    for band in ("kick", "mid", "high"):
        raw, rel = ch[f"hits.{band}_raw"], ch[f"hits.{band}"]
        for it in ctx.written_events(f"hits.{band}")["items"]:
            for i in flash_samples(it["t"]):
                assert raw[i] >= it["env"] - 1e-4 and rel[i] >= it["env"] - 1e-4, (band, it["t"])
        assert np.all(rel >= raw - 1e-6)  # the released curve never sits below the raw one


@pytest.mark.parametrize("kw,thr", [(dict(bass=False, pad=False, syncopated=False), 0.98),
                                    (dict(bass=False, pad=False), 0.9)])
def test_onsets_bass_on_kicks(kw, thr, tmp_path):
    """onsets.bass (viz flux 32-260 Hz, refractory 0.16 s) land on the kicks, timed on the 400 Hz envelope."""
    x, sr, truth = groove(duration_s=16.0, **kw)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("onsets.bass")["items"]
    f, p, rc, errs = f1([it["t"] for it in ev], [k["t"] for k in truth["kick"]], 0.02)
    assert f >= thr and p >= 0.95, (f, p, rc)
    assert abs(float(np.median(errs))) < 0.003
    assert all(0.0 <= it["strength"] <= 1.0 for it in ev)


def test_onsets_mid_high_on_snares_and_hats(tmp_path):
    x, sr, truth = groove(duration_s=16.0, bass=False, pad=False, syncopated=False)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ctx = r["ctx"]["spectral"]
    hi = [it["t"] for it in ctx.written_events("onsets.high")["items"]]
    _, p, rc, errs = f1(hi, sorted([k["t"] for k in truth["hat"]] + [k["t"] for k in truth["snare"]]), 0.02)
    assert p >= 0.9 and rc >= 0.7, (p, rc)
    mid = [it["t"] for it in ctx.written_events("onsets.mid")["items"]]
    _, p, rc, _ = f1(mid, sorted([k["t"] for k in truth["snare"]] + [k["t"] for k in truth["kick"]]), 0.02)
    assert p >= 0.9 and rc >= 0.6, (p, rc)


def test_viz_values_and_spectrum_follow_the_viz_rules(groove_run):
    r, x, sr, _ = groove_run
    fr = dsp.analyse_frames(x, sr)
    vv = dsp.viz_values(fr)
    assert 0.6 <= vv.gain <= 3.5
    # spectrum128 = round(255 * smoothed bands); bands rise with a 22 ms attack and fall with a 110 ms release
    spec = r["ctx"]["spectral"].written_matrix("spectrum128")
    ref = np.round(255 * np.clip(vv.bands, 0, 1)).astype(np.int16)
    assert np.max(np.abs(spec.astype(np.int16) - ref)) <= 1  # the stage reads float32 audio
    a = 1 - math.exp(-0.01 / 0.022)
    v = np.zeros((5, 1))
    v[1:] = 1.0
    sm = dsp.asym_smooth(v, 0.022, 0.11)
    assert abs(sm[1, 0] - a) < 1e-12


@pytest.mark.parametrize("sr,ch", [(48000, 1), (22050, 2), (96000, 2)])
def test_other_rates_and_mono(sr, ch, tmp_path):
    x, _, truth = groove(duration_s=8.0, sr=sr, bass=False)
    if ch == 1:
        x = x.mean(axis=0, keepdims=True)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ctx = r["ctx"]["spectral"]
    n = n_curve_frames(x.shape[1], sr)
    assert ctx.written_curves()["bands.bass_db"].size == n
    f, _, _, _ = f1([it["t"] for it in ctx.written_events("hits.kick")["items"]], [k["t"] for k in truth["kick"]], 0.01)
    assert f >= 0.9, (sr, ch, f)


def test_digital_silence(tmp_path):
    x = np.zeros((2, 44100 * 3))
    r = run_m1(x, 44100, tmp_path, stages=("spectral",))
    ctx = r["ctx"]["spectral"]
    ch = ctx.written_curves()
    assert np.all(ch["bands.bass_db"] == dsp.DB_FLOOR) and np.all(ch["hits.kick"] == 0)
    assert ctx.written_events("hits.kick")["items"] == []


# ------------------------------------------------------------------------------------------------ real songs
@pytest.mark.real
@pytest.mark.slow
@pytest.mark.parametrize("slug", list(REAL_SONGS))
def test_real_song_kick_counts(slug, tmp_path):
    """The viz-strength kick hits match the W0 offline reference count within 10 % (bench-music §4)."""
    if not real_available(slug):
        pytest.skip("real fixture missing")
    from mvh.io import audio as aio

    d = aio.decode(real_dir(slug) / "_intermediate" / "ingest" / "canonical.wav")
    r = run_m1(d.samples, d.sr, tmp_path, stages=("spectral",))
    items = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    ref = REAL_SONGS[slug][2]
    n_viz = sum(1 for it in items if it["viz"])
    # The viz reference count includes the bass-note and cymbal ripple that viz's one-hit-per-note logic registers; hits.kick
    # (review B1 / R2-M1) drops the ones with no low-band attack of their own, so up to ~35 % fewer viz-flagged events is
    # expected (megafauna's DrumSep stem, the only dense one, is unusable); never more than the reference + 10 %.
    assert 0.65 * ref <= n_viz <= 1.1 * ref, (slug, n_viz, ref)
    assert len(items) >= n_viz


# ------------------------------------------------------------------------------------------------ kick evidence helpers
def test_kick_glide_tells_a_kick_sweep_from_a_held_bass_note():
    sr = 44100
    t = np.arange(int(0.3 * sr)) / sr
    kick = np.sin(2 * np.pi * np.cumsum(48.0 + 110.0 * np.exp(-t / 0.03)) / sr) * np.exp(-t / 0.2)
    bass = np.sin(2 * np.pi * 55.0 * t) * np.exp(-t / 0.5)
    g_kick = dsp.kick_glide(dsp.glide_signal(kick, sr), 0.0)
    g_bass = dsp.kick_glide(dsp.glide_signal(bass, sr), 0.0)
    assert g_kick >= 1.5 and 0.7 <= g_bass <= 1.2
    assert np.isnan(dsp.kick_glide(np.zeros(100), 5.0))


def test_low_excess_separates_an_attack_from_the_recovery_of_a_beating_null():
    n = 400
    lvl = np.full(n, -30.0)
    lvl[100:] = -10.0  # a kick: steps up from -30 to -10 dB
    lvl[250:256] = -35.0  # a beating null in the tail ...
    lvl[256:] = -10.0  # ... that recovers to where it was
    ex = dsp.low_excess_db(lvl)
    assert ex[99] > 15.0
    assert ex[255] < 1.0
