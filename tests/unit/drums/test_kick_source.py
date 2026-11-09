"""UD2 (D79): the DrumSep kick-stem quality gate (CR-M1-4), the recovery of kicks DrumSep put in the snare / toms stem,
and the per-song kick-source choice written to meta/drums.json. Synthetic one-shots only (fast)."""
from __future__ import annotations

import json

import numpy as np
import pytest
from tests.synth.m3a import SYNTH, fixture_upstreams, run_stage

from mvh.contract import schemas
from mvh.stages.drums import core
from mvh.stages.drums import kick as kq

SR = 44100


def _kick(vel=1.0, sr=SR):
    n = int(0.3 * sr)
    t = np.arange(n) / sr
    f = 50 + 100 * np.exp(-t / 0.03)
    return vel * np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.15)


def _tick(gain, seed, sr=SR):
    """A hat click leaking into another stem: 4-12 kHz noise, 15 ms decay, nothing below 1 kHz."""
    from scipy import signal

    rng = np.random.default_rng(seed)
    n = int(0.06 * sr)
    y = signal.sosfilt(signal.butter(4, [4000 / (sr / 2), 12000 / (sr / 2)], btype="bandpass", output="sos"), rng.standard_normal(n))
    return gain * y * np.exp(-np.arange(n) / sr / 0.015)


def _floor_tom(sr=SR):
    n = int(0.8 * sr)
    t = np.arange(n) / sr
    return 0.8 * np.sin(2 * np.pi * 95 * t) * np.exp(-t / 0.5)


def _place(n, shots):
    x = np.zeros(n)
    for s, y in shots:
        e = min(n, s + y.size)
        x[s:e] += y[: e - s]
    return x


def _hit(t, drum, sub, vel=1.0):
    return core.Hit(t=t, sample=int(round(t * SR)), drum=drum, level_db=-10.0, peak=vel, rise_db=30.0, sub_stem=sub)


def _bleedy_song(dur=8.0):
    """Kicks on every beat at 120 BPM in the kick stem, plus 32nd-note hat ticks that leak into the kick stem 30 dB down
    (MEGAFAUNA's kick stem); the hat stem carries the ticks at full level."""
    n = int(dur * SR)
    kick_t = [0.5 + 0.5 * k for k in range(int((dur - 1.0) / 0.5))]
    tick_t = [0.5 + 0.0625 * k + 0.031 for k in range(int((dur - 1.0) / 0.0625))]
    # the onset detector masks a weak tick on a kick's tail (detect: mask_ms), so no candidate row exists there
    tick_t = [t for t in tick_t if not any(0 <= t - k <= 0.1 for k in kick_t)]
    kick = _place(n, [(int(t * SR), _kick()) for t in kick_t] + [(int(t * SR), _tick(0.03, i)) for i, t in enumerate(tick_t)])
    hat = _place(n, [(int(t * SR), _tick(1.0, i)) for i, t in enumerate(tick_t)])
    hits = ([_hit(t, "kick", "kick") for t in kick_t] + [_hit(t, "kick", "kick", 0.05) for t in tick_t]
            + [_hit(t, "hat", "hihat") for t in tick_t])
    return {"kick": kick, "hihat": hat}, sorted(hits, key=lambda h: h.t), kick_t, tick_t


def test_gate_drops_hat_bleed_rows_and_keeps_every_kick():
    subs, hits, kick_t, tick_t = _bleedy_song()
    out, st = kq.gate_kicks(hits, subs, SR)
    kicks = sorted(h.t for h in out if h.drum == "kick")
    assert kicks == pytest.approx(kick_t), (len(kicks), len(kick_t), st)
    assert st["candidates"] == len(kick_t) + len(tick_t)
    assert sum(st["dropped"].values()) == len(tick_t), st
    assert all("low_band_rise" in h.evidence for h in out if h.drum == "kick")


def test_gate_keeps_soft_kicks_that_rise_in_the_low_band():
    """A ghost kick 14 dB under the accents is still a kick (its low band rises, no hat on it)."""
    n = int(4 * SR)
    loud = [0.5, 1.5, 2.5, 3.5]
    soft = [1.0, 2.0, 3.0]
    x = _place(n, [(int(t * SR), _kick()) for t in loud] + [(int(t * SR), _kick(0.2)) for t in soft])
    hits = [_hit(t, "kick", "kick") for t in sorted(loud + soft)]
    out, st = kq.gate_kicks(hits, {"kick": x}, SR)
    assert sorted(h.t for h in out if h.drum == "kick") == sorted(loud + soft), st


def test_a_kick_in_the_snare_stem_is_recovered_and_a_floor_tom_is_not():
    n = int(6 * SR)
    kick_t = [0.5, 1.5, 2.5, 3.5, 4.5]
    snare_kick_t = [1.0, 3.0]        # DrumSep put these kicks into the snare stem
    tom_t = [2.0, 4.0]               # ringing floor toms (95 Hz): bass-heavy, but not kicks
    subs = {"kick": _place(n, [(int(t * SR), _kick()) for t in kick_t]),
            "snare": _place(n, [(int(t * SR), _kick(0.8)) for t in snare_kick_t]),
            "toms": _place(n, [(int(t * SR), _floor_tom()) for t in tom_t])}
    hits = ([_hit(t, "kick", "kick") for t in kick_t] + [_hit(t, "snare", "snare") for t in snare_kick_t]
            + [_hit(t, "tom", "toms") for t in tom_t])
    out, st = kq.gate_kicks(hits, subs, SR, mix_kicks=kick_t + snare_kick_t + tom_t)
    assert sorted(h.t for h in out if h.drum == "kick") == sorted(kick_t + snare_kick_t), st
    assert st["recovered"]["snare"] == 2 and st["recovered"]["toms"] == 0
    assert sorted(h.t for h in out if h.drum == "tom") == tom_t
    rec = [h for h in out if "recovered_from_snare_low_band" in h.evidence]
    assert len(rec) == 2 and all(h.sub_stem == "snare" for h in rec)


def test_a_snare_stroke_is_never_recovered_as_a_kick():
    from scipy import signal

    n = int(4 * SR)
    rng = np.random.default_rng(3)
    sn = signal.sosfilt(signal.butter(2, [150 / (SR / 2), 8000 / (SR / 2)], btype="bandpass", output="sos"),
                        rng.standard_normal(int(0.2 * SR))) * np.exp(-np.arange(int(0.2 * SR)) / SR / 0.05)
    snare_t = [1.0, 2.0, 3.0]
    subs = {"kick": _place(n, [(int(t * SR), _kick()) for t in (0.5, 1.5, 2.5)]),
            "snare": _place(n, [(int(t * SR), 0.9 * sn) for t in snare_t])}
    hits = [_hit(t, "kick", "kick") for t in (0.5, 1.5, 2.5)] + [_hit(t, "snare", "snare") for t in snare_t]
    out, st = kq.gate_kicks(hits, subs, SR, mix_kicks=snare_t)   # even with the mix "seeing" a kick there
    assert sorted(h.t for h in out if h.drum == "snare") == snare_t
    assert sum(st["recovered"].values()) == 0, st


def test_agreement_is_the_share_within_tolerance():
    assert kq.agreement([1.0, 2.0, 3.0], [1.02, 2.5], 0.03) == pytest.approx(1 / 3)
    assert kq.agreement([], [1.0], 0.03) is None
    assert kq.agreement([1.0], [], 0.03) == 0.0


def _kicks(times, vel):
    return [core.Hit(t=t, sample=0, drum="kick", level_db=-10.0, peak=1.0, rise_db=20.0, vel=vel) for t in times]


def test_choose_source_prefers_a_clean_stem_and_rejects_a_bleedy_one():
    beat = [0.5 + 0.5 * k for k in range(40)]
    mix = [{"t": t + 0.004, "kick_conf": 0.9} for t in beat]
    gate = {"candidates": 40, "recovered": {}, "dropped": {}, "low_rise_share": 1.0}
    c = kq.choose_source("drumsep", _kicks(beat, 0.8), gate, mix)
    assert c["kick_source"] == "drums" and not c["agreement"]["low"] and c["agreement"]["min"] == 1.0
    # MEGAFAUNA's raw kick stem: 32nd-grid rows at vel 0.14
    grid = [0.5 + 0.071 * k for k in range(200)]
    c = kq.choose_source("drumsep", _kicks(grid, 0.14), {"candidates": 200, "recovered": {}, "dropped": {}}, mix)
    assert c["kick_source"] == "mix", c
    assert any("vel" in f for f in c["drums"]["checks_failed"]) and any("gaps" in f for f in c["drums"]["checks_failed"])
    assert "lower quality" in c["reason"]


def test_choose_source_without_stems_or_without_kicks():
    mix = [{"t": 1.0, "kick_conf": 0.9}]
    assert kq.choose_source("none", [], None, mix)["kick_source"] == "mix"
    # W4A-ACAP: a separated drum stem without a kick and a single mix 'kick' (a plosive): no agent kicks, no flag
    c = kq.choose_source("drumsep", [], {"candidates": 0}, mix, duration_s=60.0)
    assert c["kick_source"] == "drums" and "no agent-facing kicks" in c["reason"] and not c["agreement"]["low"]
    c = kq.choose_source("drumsep", [], {"candidates": 0}, [])
    assert c["kick_source"] == "drums" and c["agreement"]["min"] is None and not c["agreement"]["low"]


def test_kickless_stem_next_to_a_kick_track_falls_back_and_flags():
    """W4A-ACAP: the stem holds no kick while the mix has a real kick track (separation lost it): mix + QA flag."""
    mix = [{"t": 0.5 + 0.5 * k, "kick_conf": 0.9} for k in range(60)]
    c = kq.choose_source("classifier", [], None, mix, duration_s=40.0)
    assert c["kick_source"] == "mix" and c["agreement"]["low"] and c["agreement"]["min"] == 0.0


def test_a_cappella_plosives_give_no_agent_kicks_but_a_flag_when_frequent():
    """A handful of mix 'kicks' on a vocal-only song (synth_acap had 13 before the formant gate): no agent kicks; >= 3
    raise the disagreement flag so the QA sees them."""
    mix = [{"t": 2.0 + 3.0 * k, "kick_conf": 0.8} for k in range(5)]
    c = kq.choose_source("classifier", [], None, mix, duration_s=94.0)
    assert c["kick_source"] == "drums" and c["agreement"]["low"]


def test_low_agreement_with_a_clean_stem_keeps_the_stem_and_flags():
    beat = [0.5 + 0.5 * k for k in range(40)]
    mix = [{"t": t + 0.25, "kick_conf": 0.9} for t in beat[:10]]   # a sidechained drop: the mix low band misses the kicks
    c = kq.choose_source("drumsep", _kicks(beat, 0.8), {"candidates": 40, "recovered": {}, "dropped": {}}, mix)
    assert c["kick_source"] == "drums" and c["agreement"]["low"] and "agrees only" in c["reason"]


# ------------------------------------------------------------------------------------------------ stage
def _spectral_upstream(tmp_path):
    """A spectral cache dir holding the contract fixture's events/hits.kick.json (plus the runner's done record)."""
    import shutil

    d = tmp_path / "spectral-up"
    (d / "events").mkdir(parents=True)
    (d / "_mvh").mkdir()
    shutil.copyfile(SYNTH / "events" / "hits.kick.json", d / "events" / "hits.kick.json")
    with open(d / "_mvh" / "done.json", "w", encoding="utf-8") as fh:
        json.dump({"outputs": {"events/hits.kick.json": {"kind": "events", "events": "hits.kick"}}}, fh)
    return str(d)


def test_stage_writes_meta_drums_and_picks_the_stem_on_the_synthetic_song(tmp_path):
    ups, ing = fixture_upstreams(SYNTH)
    sa, _ = run_stage("stem_activity", tmp_path, ups, ing)
    ups["stem_activity"] = str(sa)
    ups["spectral"] = _spectral_upstream(tmp_path)
    out, done = run_stage("drums", tmp_path, ups, ing)
    with open(out / "meta/drums.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert schemas.validate(meta, "mvh/files/drums") == []
    assert meta["kick_source"] == "drums", meta["reason"]
    assert meta["agreement"]["min"] >= 0.9 and not meta["agreement"]["low"]
    assert done["result"]["summary"]["kick_source"] == "drums"
    assert meta["drums"]["kept_share"] >= 0.95


def test_stage_kick_source_param_overrides_the_choice(tmp_path):
    ups, ing = fixture_upstreams(SYNTH)
    sa, _ = run_stage("stem_activity", tmp_path, ups, ing)
    ups["stem_activity"] = str(sa)
    ups["spectral"] = _spectral_upstream(tmp_path)
    out, done = run_stage("drums", tmp_path, ups, ing, params={"kick_source": "mix"})
    with open(out / "meta/drums.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["kick_source"] == "mix" and meta["override"] == "mix" and "automatic choice: drums" in meta["reason"]
    assert "drums:kick_source_mix" in done["result"]["fallbacks"]
