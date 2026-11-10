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
from tests.synth.m1.markers import real_available, real_dir
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


@pytest.mark.parametrize("kw", [{}, {"seed": 3}, {"syncopated": False}, {"seed": 5}, {"bpm": 140.0}, {"dense": True}],
                         ids=["default", "seed3", "four-on-the-floor", "seed5", "140bpm", "dense"])
def test_kick_events_with_sub_bass_line(kw, tmp_path):
    """A bass line in the kick band (sustained notes changing on the off-beats, 100-200 ms before or after many kicks):
    bass-note onsets are no kicks and must not suppress the kick after them (PLAN §7 F1 >= 0.95), and kick_conf ranks
    the kicks above anything else emitted."""
    x, sr, truth = groove(**kw)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    ref = [k["t"] for k in truth["kick"]]
    f, p, rc, _ = f1([it["t"] for it in ev], ref, 0.010)
    assert f >= 0.95, (kw, f, p, rc)
    kicks = np.array(ref)
    tp = [it["kick_conf"] for it in ev if np.min(np.abs(kicks - it["t"])) <= 0.01]
    fp = [it["kick_conf"] for it in ev if np.min(np.abs(kicks - it["t"])) > 0.01]
    assert not fp or np.median(tp) >= np.median(fp)


def _riff(bpm: float, kick_steps, bass_steps, staccato: float, hat_steps, bars: int = 8):
    """Fixture kicks (tests.synth.dsp.kick, faded) over a bass riff (A1 A1 A2 A1 C2 A1 A2 G1 on 16ths) with closed hats."""
    from tests.synth import dsp as sd
    from tests.synth.m1.signals import _faded

    sr = 44100
    beat = 60.0 / bpm
    s16 = beat / 4
    x = np.zeros((2, int((0.5 + bars * 4 * beat + 1.0) * sr)))
    ref = []
    notes = [33, 33, 45, 33, 36, 33, 45, 31]
    for b in range(bars):
        t0 = 0.5 + b * 4 * beat
        for s in kick_steps:
            i = int(round((t0 + s * s16) * sr))
            sd.place(x, sd.pan(_faded(sd.kick(0.95, sr), sr) * 0.9, 0.0), i)
            ref.append(i / sr)
        for s in bass_steps:
            sd.place(x, sd.pan(sd.bass_note(notes[s % 8], s16 * staccato, 0.8, sr) * 0.5, 0.0), int(round((t0 + s * s16) * sr)))
        for s in hat_steps:
            sd.place(x, sd.pan(_faded(sd.hihat(0.6, False, sr, seed=4), sr) * 0.3, 0.3), int(round((t0 + s * s16) * sr)))
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    return x * 10 ** (-1 / 20) / np.max(np.abs(x)), sr, ref


def _roll(bpm: float, crash: bool):
    """Metal double bass: a tight 70 ms-decay kick with a click on 16ths (6 bars), optionally under a crash every 2 s."""
    from scipy import signal as ss
    from tests.synth import dsp as sd

    sr = 44100
    step = 60.0 / bpm / 4
    ref = [0.5 + i * step for i in range(96)]
    n = int(0.3 * sr)
    tt = np.arange(n) / sr
    body = np.sin(2 * np.pi * np.cumsum(55.0 + 100.0 * np.exp(-tt / 0.02)) / sr) * np.exp(-tt / 0.07)
    click = ss.sosfilt(ss.butter(4, 1500, "highpass", fs=sr, output="sos"), np.random.default_rng(3).standard_normal(n))
    k = body + click * np.exp(-tt / 0.003) * 0.35
    k = 0.9 * k / np.max(np.abs(k))
    x = np.zeros((2, int((ref[-1] + 1.5) * sr)))
    for t in ref:
        sd.place(x, sd.pan(k, 0.0), int(round(t * sr)))
    if crash:
        t = 0.3
        while t < x.shape[1] / sr - 1.0:
            sd.place(x, sd.pan(sd.crash(1.0, 2.5, sr) * 0.5, 0.0), int(t * sr))
            t += 2.0
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    return x * 10 ** (-1 / 20) / np.max(np.abs(x)), sr, ref


@pytest.mark.parametrize("case", ["riff16", "riff16-150bpm", "rock-140bpm", "rock-160bpm", "rock-180bpm",
                                  "roll-180bpm", "roll-220bpm", "roll-170bpm-crash"])
def test_kick_events_over_bass_riffs_and_in_rolls(case, tmp_path):
    """Review R3-B1 / R2-M1 / R2-M2 textures: four-on-the-floor over a staccato 16th bass riff (the note one 16th before
    the downbeat is no kick); rock 8th-kick pairs over a bass note held for two beats (the '&' kick rises only ~3 dB over
    the bass); 16th double kicks up to 220 BPM and under a crash that masks the click. PLAN §7: F1 >= 0.95 at +-10 ms."""
    if case.startswith("riff16"):
        x, sr, ref = _riff(150.0 if "150" in case else 128.0, (0, 4, 8, 12), range(16), 0.8, range(16))
    elif case.startswith("rock"):
        x, sr, ref = _riff(float(case.split("-")[1][:3]), (0, 2, 8, 10), (0, 8), 7.6, range(0, 16, 2))
    else:
        x, sr, ref = _roll(float(case.split("-")[1][:3]), case.endswith("crash"))
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    f, p, rc, _ = f1([it["t"] for it in ev], ref, 0.010)
    assert f >= 0.95, (case, f, p, rc, len(ev), len(ref))


def _kick_case(case: str):
    from tests.synth.m1 import kicks as K

    db = 10 ** (-1 / 20)
    if case.startswith("held-"):
        return K.kicks_over_held_bass(case.split("-")[1])
    if case.startswith("duck-"):
        kind, bass = case.split("-")[1], float(case.split("-")[2])
        return K.kicks_over_ducked_sub(kind, bass=bass)
    if case == "quiet-intro":
        return K.kicks_over_held_bass("fixture", bass=0.0, bars=12, gains=[db ** 16] * 4 + [1.0] * 8)
    if case == "quiet-intro-bass":
        return K.kicks_over_held_bass("fixture", bass=0.5, bars=12, gains=[db ** 16] * 4 + [1.0] * 8)
    if case == "fade-out":
        return K.kicks_over_held_bass("fixture", bass=0.0, bars=12, gains=[1.0] * 8 + [db ** (4 * k) for k in range(1, 5)])
    if case == "fixture-roll-180bpm-crash":
        return K.fixture_roll(180.0)
    raise KeyError(case)


@pytest.mark.parametrize("case", ["held-acoustic", "held-tr909", "held-fixture", "duck-fixture-0.8", "duck-fixture-1.0",
                                  "duck-tr909-0.8", "quiet-intro", "quiet-intro-bass", "fade-out",
                                  "fixture-roll-180bpm-crash"])
def test_kick_designs_and_mix_situations(case, tmp_path):
    """Review R4-M1/M2/M3 and m21, on signals independent of the review's (tests/synth/m1/kicks.py: other kick designs,
    tempos and gains): an acoustic kick (no sweep, beater click) and a 909 over a bass note held for the bar; kicks over a
    sub bass sidechain-ducked 92 % at each kick (the low band hardly rises); a 4-bar intro 16 dB down and a fade-out of
    4 dB per bar (the faint-thump filter is relative to the local mix level); the contract song's long kick on 16ths at
    180 BPM under a crash (roll route). PLAN §7: F1 >= 0.95 at +-10 ms.
    UD2 (W4, docs/contract/decisions/UD2.md): the acoustic kick over a held bass was found only by the clicky-body route,
    which is off (it invents kicks on kick-free material); for it the target is precision >= 0.95 (no invented kick) with
    a recall guard of 0.5 (measured 0.725)."""
    x, sr, ref = _kick_case(case)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    f, p, rc, _ = f1([it["t"] for it in ev], ref, 0.010)
    if case == "held-acoustic":
        assert p >= 0.95 and rc >= 0.5, (case, f, p, rc, len(ev), len(ref))
    else:
        assert f >= 0.95, (case, f, p, rc, len(ev), len(ref))


@pytest.mark.xfail(strict=True, reason="known limit: a clickless 808 starting at 82 Hz over a held bass is often anchored "
                                       "~10 ms early (90-200 Hz band pre-ringing) or missed (pitch drop 1.15-1.2)")
def test_clickless_808_over_a_held_bass_note(tmp_path):
    """A second 808 design (82 -> 48 Hz, tau 18 ms, no click) over the held bass: F1 0.80 (the review's 808, 80 -> 50 Hz
    at 120 BPM, passes). Without the bass: 1.0."""
    from tests.synth.m1 import kicks as K

    x, sr, ref = K.kicks_over_held_bass("tr808")
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    f, p, rc, _ = f1([it["t"] for it in ev], ref, 0.010)
    assert f >= 0.95, (f, p, rc)


def test_kick_on_the_first_sample(tmp_path):
    """Review m20: a file that starts on a kick keeps that kick (the analysis pads silence in front)."""
    from tests.synth.m1 import kicks as K

    x, sr, ref = K.kick_at_start()
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ts = [it["t"] for it in r["ctx"]["spectral"].written_events("hits.kick")["items"]]
    f, p, rc, _ = f1(ts, ref, 0.010)
    assert f == 1.0 and ts[0] < 0.01, ts


def test_kick_routes_and_conf_are_reported(groove_run):
    """Every kick carries a route from dsp.KICK_ROUTES (summarised in the stage's meta) and a 0..1 kick_conf."""
    r, _, _, _ = groove_run
    items = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    assert items and all(0.0 <= it["kick_conf"] <= 1.0 for it in items)
    ev = dsp.KickEvidence(attack=8.0, glide=1.5, f_early=90.0, click=20.0, low_ex=6.0, body_ex=8.0, body_add=7.0,
                          body_db=-10.0, decay=9.0, gate=1.0)
    assert dsp.kick_route(ev, dsp.KICK_DEFAULTS) in dsp.KICK_ROUTES and 0.0 <= ev.conf() <= 1.0
    ev.gate = 0.0
    assert dsp.kick_route(ev, dsp.KICK_DEFAULTS) == ""


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


@pytest.mark.parametrize("analysis_lufs,hi_rc", [(None, 0.7), (-10.0, 0.6)], ids=["native_level", "analysis_level"])
def test_onsets_mid_high_on_snares_and_hats(tmp_path, analysis_lufs, hi_rc):
    """The groove is a -16 LUFS mix. At its own level (analysis_lufs None) the high-band flux onsets recall >= 0.7 of
    the hats + snares; at the default analysis level (F-gain-5: events picked on the mix at -10 LUFS, a commercial
    master's level) the viz dB map compresses the flux of a louder signal and recall is 0.64, so the bar there is 0.6."""
    x, sr, truth = groove(duration_s=16.0, bass=False, pad=False, syncopated=False)
    r = run_m1(x, sr, tmp_path, stages=("spectral",), params={"spectral": {"analysis_lufs": analysis_lufs}})
    ctx = r["ctx"]["spectral"]
    hi = [it["t"] for it in ctx.written_events("onsets.high")["items"]]
    _, p, rc, errs = f1(hi, sorted([k["t"] for k in truth["hat"]] + [k["t"] for k in truth["snare"]]), 0.02)
    assert p >= 0.9 and rc >= hi_rc, (p, rc)
    mid = [it["t"] for it in ctx.written_events("onsets.mid")["items"]]
    _, p, rc, _ = f1(mid, sorted([k["t"] for k in truth["snare"]] + [k["t"] for k in truth["kick"]]), 0.02)
    assert p >= 0.9 and rc >= 0.6, (p, rc)


def test_events_do_not_follow_the_master_level(tmp_path):
    """F-gain-5 (W4V2-GAIN-SPECTRAL): a -12 dB copy of the mix gives the same hit and onset events (F >= 0.97 at 10 ms);
    the dB curves move by the gain."""
    x, sr, _ = groove(duration_s=16.0, bass=True, pad=True, syncopated=True)
    a = run_m1(x, sr, tmp_path / "a", stages=("spectral",))["ctx"]["spectral"]
    q = np.asarray(x, np.float32) * np.float32(10 ** (-12 / 20))
    b = run_m1(q, sr, tmp_path / "b", stages=("spectral",))["ctx"]["spectral"]
    for lane in ("hits.kick", "hits.mid", "hits.high", "onsets.bass", "onsets.mid", "onsets.high"):
        ta = [it["t"] for it in a.written_events(lane)["items"]]
        tb = [it["t"] for it in b.written_events(lane)["items"]]
        if len(ta) < 3:
            continue
        f = f1(tb, ta, 0.01)[0]
        assert f >= 0.97, (lane, len(ta), len(tb), f)


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
@pytest.mark.parametrize("slug", ["jeremy", "newton-vs-nye", "versatile"])
def test_real_song_kick_events_follow_the_kick_stem(slug, tmp_path):
    """hits.kick against the unambiguous onsets of the DrumSep kick sub-stem (rise >= 20 dB to within 6 dB of the stem's
    top level, review helper): recall >= 0.93 at +-30 ms. (The helper's onsets sit ~20 ms before the true onset: a
    zero-phase filter.) MEGAFAUNA is left out: its DrumSep kick stem is mostly 32nd-note hat bleed."""
    import sys

    if not real_available(slug):
        pytest.skip("real fixture missing")
    stem = real_dir(slug) / "stems" / "drums" / "kick.flac"
    if not stem.is_file():
        pytest.skip("no DrumSep kick stem")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "review" / "M1" / "r-dsp"))
    from rdsp_m1_support import kick_stem_attacks

    from mvh.io import audio as aio

    d = aio.decode(real_dir(slug) / "_intermediate" / "ingest" / "canonical.wav")
    r = run_m1(d.samples, d.sr, tmp_path, stages=("spectral",))
    items = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    ref = [t + 0.02 for t in kick_stem_attacks(stem)]
    f, p, rc, _ = f1([it["t"] for it in items], ref, 0.030)
    assert rc >= 0.93, (slug, f, p, rc, len(items), len(ref))


# ------------------------------------------------------------------------------------------------ kick evidence helpers
def test_glide_meter_tells_a_kick_sweep_from_a_bass_note_even_over_a_held_note():
    sr = 44100
    t = np.arange(int(0.6 * sr)) / sr
    on = t >= 0.3
    tk = np.maximum(t - 0.3, 0.0)
    kick = np.where(on, np.sin(2 * np.pi * np.cumsum(np.where(on, 48.0 + 110.0 * np.exp(-tk / 0.03), 0.0)) / sr) * np.exp(-tk / 0.2), 0.0)
    bass = np.where(on, np.sin(2 * np.pi * 55.0 * t), 0.0)
    held = 0.6 * np.sin(2 * np.pi * 55.0 * t + 0.4) + 0.3 * np.sin(2 * np.pi * 110.0 * t)
    g_kick = dsp.GlideMeter(kick, sr).glide(0.3)[0]
    g_bass = dsp.GlideMeter(bass, sr).glide(0.3)[0]
    g_over = dsp.GlideMeter(kick + held, sr).glide(0.3)[0]
    assert g_kick >= 1.5 and 0.8 <= g_bass <= 1.2 and g_over >= 1.4, (g_kick, g_bass, g_over)
    assert np.isnan(dsp.GlideMeter(np.zeros(sr), sr).glide(0.5)[0])


def test_max_step_ignores_the_recovery_of_a_beating_null():
    lvl = np.full(400, -30.0)
    lvl[100:] = -10.0  # a kick: steps up from -30 to -10 dB
    lvl[250:256] = -35.0  # a beating null in the tail ...
    lvl[256:] = -10.0  # ... that recovers to where it was
    s = dsp.max_step(lvl, 4, 8)
    assert s[99] > 15.0
    assert np.max(s[250:260]) < 1.0


def _kick_free(kind: str, bpm: float = 110.0, bars: int = 10, sr: int = 44100):
    """Kick-free textures (no kick in the truth), built here from tests.synth.dsp primitives with other parameters than
    the review's rdsp_r5_signals.kick_free (tempo 110, roots E1 G1 D1 C2, other gains and registers)."""
    from tests.synth import dsp as sd
    from tests.synth.m1.signals import _faded

    beat = 60.0 / bpm
    x = np.zeros((2, int((0.5 + bars * 4 * beat + 1.5) * sr)))
    roots = [28, 31, 26, 36]
    hat = _faded(sd.hihat(0.5, False, sr, seed=7), sr) * 0.35
    for b in range(bars):
        t0 = 0.5 + b * 4 * beat
        r = roots[b % 4]
        if kind == "pluck_hats":
            n = int(beat / 2 * sr)
            tt = np.arange(n) / sr
            f0 = float(sd.midi_hz(r + 12))
            fc = 140.0 + 1700.0 * np.exp(-tt / 0.04)
            pl = sd.additive(f0, n, [1.0 / k for k in range(1, 50)], sr,
                             partial_env=lambda k: 1.0 / np.sqrt(1 + (k * f0 / fc) ** 8))
            pl = 0.45 * pl * np.minimum(1, tt / 0.003) * np.exp(-tt / 0.3) * np.minimum(1, (n - np.arange(n)) / (0.01 * sr))
            for q in range(8):
                i = int(round((t0 + q * beat / 2) * sr))
                sd.place(x, sd.pan(pl, -0.1), i)
                sd.place(x, sd.pan(hat, 0.25), i)
        elif kind == "piano_low":
            for q in range(4):
                i = int(round((t0 + q * beat) * sr))
                # left hand from the octave above E2..C3 (110-130 Hz roots; a staccato chord whose FUNDAMENTAL sits in the
                # 30-100 Hz kick band, e.g. E2 at 82 Hz, reads as an acoustic kick to a mix-only detector: a documented
                # limit of the fallback, docs/contract/decisions/UD2.md)
                for m in (r + 24, r + 31, r + 36, r + 40):
                    sd.place(x, sd.pan(sd.piano_note(m, beat * 0.85, 0.8, sr), 0.0), i)
        elif kind == "snare_bass":
            for q in (1, 3):
                i = int(round((t0 + q * beat) * sr))
                sd.place(x, sd.pan(_faded(sd.snare(0.85, sr, seed=5), sr) * 0.75, 0.05), i)
                sd.place(x, sd.pan(sd.bass_note(roots[(b * 2 + q) % 4], 2 * beat * 0.9, 0.75, sr) * 0.65, 0.0), i)
        else:
            raise KeyError(kind)
    x += 10 ** (-72 / 20) * np.random.default_rng(3).standard_normal(x.shape)
    return x * (10 ** (-1 / 20) / np.max(np.abs(x))), sr


@pytest.mark.parametrize("kind", ["pluck_hats", "piano_low", "snare_bass"])
def test_no_invented_kicks_on_kick_free_material(kind, tmp_path):
    """UD2 precision target for the hits.kick fallback, on kick-free textures independent of the review's generators
    (other tempo, roots and gains): a pluck bass with a closed hat on every 8th, low piano chords on every beat, a snare
    that starts each held bass note. The clicky-body route made 39 / 21 / 7 kicks of these; now <= 1."""
    x, sr = _kick_free(kind)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    ev = r["ctx"]["spectral"].written_events("hits.kick")["items"]
    assert len(ev) <= 1, (kind, [round(it["t"], 2) for it in ev[:6]])
