# ruff: noqa: E501  (long docstrings and tables)
"""drums: the detector on synthetic one-shots, the DrumSep path and the classifier path scored against the synthetic
song's ground truth (PLAN §7: F1 >= 0.9 kick/snare/hat, >= 0.7 tom/cymbal; event time = the one-shot's first
sample), then the stage end to end on the fixture."""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pytest
from tests.synth.m3a import SYNTH, fixture_upstreams, real_fixture, run_stage, truth

from mvh.contract import schemas
from mvh.io import audio as aio
from mvh.stages.drums import core

SR = 44100
TOL = 0.010   # PLAN §7 kick events: +-10 ms (applied to every drum here)


def _kick(sr=SR, vel=1.0):
    n = int(0.3 * sr)
    t = np.arange(n) / sr
    f = 50 + 100 * np.exp(-t / 0.03)
    return vel * np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.15)


def _place(n, shots):
    x = np.zeros(n)
    for s, y in shots:
        e = min(n, s + y.size)
        x[s:e] += y[: e - s]
    return x


# ------------------------------------------------------------------------------------------------ detector
def test_detect_is_sample_accurate_on_one_shots():
    starts = [4410, 30000, 52000, 77777]
    x = _place(SR * 2, [(s, _kick()) for s in starts])
    hits = core.detect(x, SR, drum="kick")
    assert len(hits) == len(starts)
    # a sine starting at phase 0 crosses 15 % of its peak (the pre-echo-proof threshold) after <= 10 samples (0.23 ms)
    assert all(0 <= h.sample - s <= 10 for h, s in zip(hits, starts)), [h.sample - s for h, s in zip(hits, starts)]


def test_detect_on_a_tail_and_velocity():
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(int(0.1 * SR))
    hat = noise * np.exp(-np.arange(noise.size) / SR / 0.02)
    starts = [1000 + i * 5513 for i in range(8)]          # 8th notes at 120 BPM
    vels = [1.0, 0.5, 0.8, 0.4, 1.0, 0.6, 0.9, 0.3]
    x = _place(SR * 2, [(s, v * hat) for s, v in zip(starts, vels)])
    hits = core.detect(x, SR, drum="hat")
    assert len(hits) == 8
    assert max(abs(h.sample - s) for h, s in zip(hits, starts)) <= 2
    core.velocities(hits, pct=100.0)
    est = np.array([h.vel for h in hits])
    assert np.corrcoef(est, vels)[0, 1] > 0.98


def test_detect_ignores_silence_and_low_frequency_ripple():
    assert core.detect(np.zeros(SR), SR) == []
    t = np.arange(SR * 2) / SR
    # a steady 45 Hz tone (sin^2 ripple every 11 ms) is not a train of onsets
    hits = core.detect(0.5 * np.sin(2 * np.pi * 45 * t) * np.minimum(1, t / 0.002), SR)
    assert len(hits) == 1 and hits[0].sample < 100


def test_envelopes_follow_the_flash_rule():
    h = core.Hit(t=1.234, sample=0, drum="snare", level_db=-10, peak=0.5, rise_db=20, vel=0.8)
    env = core.envelopes([h], 300)
    sn = env["snare"]
    assert sn[123] == pytest.approx(0.8) and sn[124] == pytest.approx(0.8)
    assert sn[122] == 0.0 and 0 < sn[140] < 0.8
    assert env["kick"].max() == 0.0 and env["perc"].max() == 0.0


def test_match_f1():
    assert core.match_f1([1.0, 2.0, 3.0], [1.005, 2.02, 3.0], 0.01)[:3] == pytest.approx((2 / 3, 2 / 3, 2 / 3))
    assert core.match_f1([], [], 0.01)[0] == 0.0 or core.match_f1([], [], 0.01)[1] == 1.0


# ------------------------------------------------------------------------------------------------ synthetic song
@lru_cache(maxsize=1)
def _truth_by_drum():
    out = {}
    for h in truth()["drum_hits"]:
        out.setdefault(h["drum"], []).append(h)
    return out


def _scores(hits):
    res = {}
    for drum in ("kick", "snare", "hat", "tom", "cymbal"):
        est = [h.t for h in hits if h.drum == drum]
        ref = [x["t"] for x in _truth_by_drum().get(drum, [])]
        res[drum] = core.match_f1(est, ref, TOL)[0]
    return res


@lru_cache(maxsize=1)
def _drumsep_synth():
    subs = {}
    for s in ("kick", "snare", "toms", "hihat", "ride", "crash"):
        d = aio.decode(SYNTH / "stems" / "drums" / f"{s}.flac")
        subs[s] = d.samples
    hits, _ = core.drumsep_hits(subs, d.sr)
    core.velocities(hits)
    return hits


def test_drumsep_path_f1_on_the_synthetic_song():
    f1 = _scores(_drumsep_synth())
    for d in ("kick", "snare", "hat"):
        assert f1[d] >= 0.9, (d, f1)
    for d in ("tom", "cymbal"):
        assert f1[d] >= 0.7, (d, f1)


def _burst(lo, hi, tau, dur=0.4, seed=0, sr=SR):
    from scipy import signal

    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    sos = signal.butter(4, [lo / (sr / 2), hi / (sr / 2)], btype="bandpass", output="sos")
    return signal.sosfilt(sos, rng.standard_normal(n)) * np.exp(-np.arange(n) / sr / tau)


def test_drumsep_drops_dull_hihat_bleed_under_a_louder_snare():
    """DrumSep leaks snare noise (1.5-6 kHz) into the hi-hat stem: those copies are dull and coincide with a louder
    snare, so they go; bright hats on the same snare strokes stay."""
    n = 5 * SR
    hats = [(int((0.25 + 0.5 * i) * SR), 0.3 * _burst(8000, 15000, 0.03, seed=i)) for i in range(9)]
    snare_t = [0.5, 1.5, 2.5, 3.5]
    bleed = [(int(t * SR), 0.1 * _burst(1500, 5000, 0.05, seed=20 + i)) for i, t in enumerate(snare_t)]
    hats_on_snare = [(int(1.0 * SR), 0.3 * _burst(8000, 15000, 0.03, seed=40)), (int(3.0 * SR), 0.3 * _burst(8000, 15000, 0.03, seed=41))]
    snare = _place(n, [(int(t * SR), 1.0 * _burst(150, 6000, 0.08, seed=30 + i)) for i, t in enumerate(snare_t + [1.0, 3.0])])
    hihat = _place(n, hats + bleed + hats_on_snare)
    hits, st = core.drumsep_hits({"hihat": hihat, "snare": snare}, SR)
    ht = sorted(round(h.t, 2) for h in hits if h.drum == "hat")
    assert ht == sorted([round(0.25 + 0.5 * i, 2) for i in range(9)] + [1.0, 3.0]), (ht, st)
    assert st["dull_bleed_dropped"] >= 1 and st["dull_bleed_dropped"] + st["bleed_dropped"]["hihat"] == 4, st


def test_drumsep_drops_open_hat_copies_in_the_ride_stem_but_keeps_a_ringing_cymbal():
    n = 4 * SR
    open_hat = 0.4 * _burst(7000, 15000, 0.035, seed=1)   # the synthetic song's open hat: ~8 dB down after 30 ms
    hihat = _place(n, [(int(1.0 * SR), open_hat), (int(2.0 * SR), 0.3 * _burst(8000, 15000, 0.02, seed=2))])
    ride = _place(n, [(int(1.0 * SR), 0.2 * open_hat), (int(2.0 * SR), 0.08 * _burst(2000, 9000, 1.0, dur=1.5, seed=3))])
    hits, st = core.drumsep_hits({"hihat": hihat, "ride": ride}, SR)
    cy = [round(h.t, 2) for h in hits if h.drum == "cymbal"]
    assert cy == [2.0], (cy, st)
    # the ride stem's quiet copy of the open hat goes (as a hat duplicate or as a quiet copy of a louder hat stroke)
    assert st["hat_duplicates_dropped"] + st.get("cymbal_leak_dropped", 0) == 1, st
    # a hat-stem hit at the instant of a ringing ride stroke is the stroke's copy (DrumSep routes a ride's attack into the hi-hat stem): the cymbal wins
    assert sorted(round(h.t, 2) for h in hits if h.drum == "hat") == [1.0]


def test_drumsep_drops_a_small_second_bump_on_the_kick_stem():
    """A separated kick stem can carry a second bump 50 ms after the stroke (bass leaking in): a < 6 dB rise is no
    new kick."""
    n = 4 * SR
    shots = []
    for i, t in enumerate((0.5, 1.5, 2.5)):
        shots.append((int(t * SR), _kick()))
        shots.append((int((t + 0.053) * SR), 0.35 * _kick()))
    hits, st = core.drumsep_hits({"kick": _place(n, shots)}, SR)
    kt = [round(h.t, 2) for h in hits if h.drum == "kick"]
    assert kt == [0.5, 1.5, 2.5], (kt, st)


def test_drumsep_onsets_are_the_one_shot_first_sample():
    hits = _drumsep_synth()
    ref = {d: np.array([x["t"] for x in v]) for d, v in _truth_by_drum().items()}
    errs = []
    for h in hits:
        r = ref.get(h.drum)
        if r is not None and r.size:
            e = np.min(np.abs(r - h.t))
            if e < TOL:
                errs.append(e)
    assert np.median(errs) <= 0.0005 and np.percentile(errs, 95) <= 0.008


def test_drumsep_velocity_tracks_programmed_velocity():
    """vel is relative to the loudest hits of the same drum: compare after per-drum scaling (rank correlation)."""
    hits = _drumsep_synth()
    for drum in ("kick", "snare"):
        ref = _truth_by_drum()[drum]
        rt = np.array([x["t"] for x in ref])
        pairs = []
        for h in hits:
            if h.drum == drum:
                j = int(np.argmin(np.abs(rt - h.t)))
                if abs(rt[j] - h.t) < TOL:
                    pairs.append((h.vel, ref[j]["vel"]))
        a = np.array(pairs)
        assert np.corrcoef(a[:, 0], a[:, 1])[0, 1] > 0.95, drum


def test_classifier_path_on_the_synthetic_drum_stem():
    """The fallback path (no DrumSep sub-stems), on the generator's clean drum stem. Kick, snare and tom meet the PLAN
    §7 gates; hat and cymbal do not (hats under a snare tail and rides under strokes are not separable from one mixed
    stem: measured hat 0.79, cymbal 0.44) and the stage marks them low confidence. Floors guard against regressions.
    The review test tests/review/M3a/r-ml/test_drums_classifier_path.py holds the full PLAN gates."""
    d = aio.decode(SYNTH / "stems" / "drums.flac")
    hits, _ = core.classify(d.samples, d.sr)
    f1 = _scores(hits)
    for drum in core.CLASSIFIER_RELIABLE:
        assert f1[drum] >= (0.9 if drum != "tom" else 0.7), (drum, f1)
    assert f1["hat"] >= 0.75 and f1["cymbal"] >= 0.4, f1


def _noise_hit(sr, lo, hi, tau, dur, seed):
    return _burst(lo, hi, tau, dur=dur, seed=seed, sr=sr)


def test_quiet_hats_on_a_noise_bed_are_found_in_the_air_band():
    """A hat sitting on a broadband bed rises ~1 dB in the full band but clearly above 8 kHz (separated hi-hat stems
    carry such beds)."""
    rng = np.random.default_rng(3)
    n = 4 * SR
    bed = 0.02 * rng.standard_normal(n)
    hat = _burst(8000, 16000, 0.02, dur=0.1, seed=4)
    starts = [int((0.5 + 0.25 * i) * SR) for i in range(12)]
    x = bed + _place(n, [(s, 0.05 * hat / np.max(np.abs(hat))) for s in starts])
    found = core.detect_air(x, SR, drum="hat")
    est = [h.t for h in found]
    _, _, recall, _ = core.match_f1(est, [s / SR for s in starts], 0.01)
    assert recall >= 0.9, (recall, len(est))
    # the full-band detector (default thresholds) cannot see them on this bed
    assert core.match_f1([h.t for h in core.detect(x, SR)], [s / SR for s in starts], 0.01)[2] < recall


def test_drumsep_relabels_a_crash_routed_into_the_hihat_stem_and_drops_a_preecho():
    n = 4 * SR
    hat = 0.4 * _burst(8000, 16000, 0.015, dur=0.3, seed=1)
    crash = 0.4 * _burst(2500, 12000, 0.2, dur=0.6, seed=2)
    kick = _kick()
    hihat = _place(n, [(int(s * SR), hat) for s in (0.5, 1.0, 1.5, 2.5, 3.0)] + [(int(2.0 * SR), crash)])   # a hat stem: mostly hats
    kicks = _place(n, [(int(2.0 * SR), 0.1 * kick)])
    hits, st = core.drumsep_hits({"hihat": hihat, "kick": kicks}, SR)
    assert [round(h.t, 2) for h in hits if h.drum == "hat"] == [0.5, 1.0, 1.5, 2.5, 3.0], st
    assert [round(h.t, 2) for h in hits if h.drum == "cymbal"] == [2.0], st
    assert st["relabelled_cymbal"] == 1


def test_classifier_labels_a_tonal_tom_not_a_snare():
    from scipy import signal

    n = 3 * SR
    t = np.arange(int(0.4 * SR)) / SR
    tom = np.sin(2 * np.pi * np.cumsum(180 + 60 * np.exp(-t / 0.05)) / SR) * np.exp(-t / 0.12)
    click = 0.05 * signal.sosfilt(signal.butter(4, [2000 / (SR / 2), 6000 / (SR / 2)], btype="bandpass", output="sos"),
                                  np.random.default_rng(0).standard_normal(int(0.4 * SR))) * np.exp(-t / 0.01)
    starts = [int(0.5 * SR), int(1.2 * SR), int(2.0 * SR)]
    x = _place(n, [(s, 0.5 * (tom + click)) for s in starts])
    hits, _ = core.classify(x, SR)
    assert [h.drum for h in hits] == ["tom"] * 3, [(h.t, h.drum) for h in hits]


# ------------------------------------------------------------------------------------------------ stage
@pytest.fixture(scope="module")
def stage_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("drums")
    ups, ing = fixture_upstreams(SYNTH)
    sa, _ = run_stage("stem_activity", tmp, ups, ing)
    ups["stem_activity"] = str(sa)
    out, done = run_stage("drums", tmp, ups, ing)
    return out, done


def test_stage_outputs(stage_run):
    out, done = stage_run
    with open(out / "events/drum_hits.json", encoding="utf-8") as fh:
        ev = json.load(fh)
    assert schemas.validate(ev, "mvh/events/drum_hits") == []
    items = ev["items"]
    assert all(it["source"] == "drumsep" and 0 <= it["vel"] <= 1 and 0 <= it["conf"] <= 1 for it in items)
    assert [it["t"] for it in items] == sorted(it["t"] for it in items)
    n = -(-int(truth()["n_samples"]) * 100 // int(truth()["sr"]))
    for d in core.DRUMS:
        assert done["curves"]["core"][f"drums.{d}"]["n"] == n
    hits = [core.Hit(t=it["t"], sample=0, drum=it["drum"], level_db=0, peak=0, rise_db=0) for it in items]
    f1 = _scores(hits)
    assert min(f1["kick"], f1["snare"], f1["hat"]) >= 0.9 and min(f1["tom"], f1["cymbal"]) >= 0.7, f1
    assert done["result"]["summary"]["path"] == "drumsep"


def test_stage_envelope_peaks_at_hits(stage_run):
    out, _ = stage_run
    with open(out / "events/drum_hits.json", encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    env = np.fromfile(out / "_mvh/curves/core/drums.kick.f32", dtype="<f4")
    from mvh.contract.conventions import flash_samples

    for it in [x for x in items if x["drum"] == "kick"][:20]:
        for i in flash_samples(it["t"]):
            assert env[i] >= it["vel"] - 1e-5


def test_stage_classifier_path_without_substems(tmp_path):
    import shutil

    ups, ing = fixture_upstreams(SYNTH)
    hq = tmp_path / "hq"
    (hq / "stems").mkdir(parents=True)
    shutil.copy(SYNTH / "stems" / "drums.flac", hq / "stems" / "drums.flac")
    shutil.copytree(SYNTH / "meta", hq / "meta")
    ups["separate_hq"] = str(hq)
    sa, _ = run_stage("stem_activity", tmp_path, ups, ing)
    ups["stem_activity"] = str(sa)
    out, done = run_stage("drums", tmp_path, ups, ing)
    assert done["status"] == "degraded" and "drums:classifier" in done["result"]["fallbacks"]
    with open(out / "events/drum_hits.json", encoding="utf-8") as fh:
        ev = json.load(fh)
    assert schemas.validate(ev, "mvh/events/drum_hits") == []
    assert {it["source"] for it in ev["items"]} == {"classifier"}
    # hat / cymbal are below the PLAN gates on this path: their vel (all the consumers read) is scaled by the confidence cap
    low = [it for it in ev["items"] if it["drum"] in ("hat", "cymbal")]
    assert low and all("vel_raw" in it and abs(it["vel"] - 0.45 * it["vel_raw"]) < 2e-4 for it in low)
    assert not any("vel_raw" in it for it in ev["items"] if it["drum"] in ("kick", "snare", "tom"))
    assert "drums:low_confidence(hat,cymbal)" in done["result"]["fallbacks"]


# ------------------------------------------------------------------------------------------------ real songs (explicit)
REAL_RATE = {  # hits per second per drum on the W0 DrumSep stems: snapshot ranges (plausibility, not truth)
    "jeremy": {"kick": (1.5, 3.0), "snare": (0.8, 1.6)},
    "megafauna": {"kick": (2.0, 4.0), "snare": (1.5, 3.5)},
    "newton-vs-nye": {"kick": (1.0, 4.0), "snare": (0.5, 3.0)},
    "versatile": {"kick": (0.5, 4.0)},
}


@pytest.mark.real
@pytest.mark.parametrize("slug", sorted(REAL_RATE))
def test_real_song_hit_rates(slug, tmp_path):
    fx = real_fixture(slug)
    if not (fx / "stems" / "drums").is_dir():
        pytest.skip(f"no fixture {fx}")
    ups, ing = fixture_upstreams(fx)
    sa, _ = run_stage("stem_activity", tmp_path, ups, ing)
    ups["stem_activity"] = str(sa)
    out, done = run_stage("drums", tmp_path, ups, ing)
    with open(out / "events/drum_hits.json", encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    dur = done["result"]["summary"]["n_hits"] and max(it["t"] for it in items)
    for drum, (lo, hi) in REAL_RATE[slug].items():
        rate = sum(1 for it in items if it["drum"] == drum) / dur
        assert lo <= rate <= hi, (drum, rate)


def test_stage_recovers_toms_the_toms_stem_lost_from_the_classifier(tmp_path):
    """DrumSep's toms stem differs from run to run and can lose strokes: the classifier on the full drum stem adds the
    toms it finds that the sub-stems do not carry (low confidence, ``classifier_only``)."""
    import shutil

    ups, ing = fixture_upstreams(SYNTH)
    hq = tmp_path / "hq"
    (hq / "stems" / "drums").mkdir(parents=True)
    shutil.copy(SYNTH / "stems" / "drums.flac", hq / "stems" / "drums.flac")
    for s in ("kick", "snare", "hihat", "ride", "crash"):   # no toms sub-stem
        shutil.copy(SYNTH / "stems" / "drums" / f"{s}.flac", hq / "stems" / "drums" / f"{s}.flac")
    shutil.copytree(SYNTH / "meta", hq / "meta")
    ups["separate_hq"] = str(hq)
    sa, _ = run_stage("stem_activity", tmp_path, ups, ing)
    ups["stem_activity"] = str(sa)
    out, done = run_stage("drums", tmp_path, ups, ing)
    with open(out / "events/drum_hits.json", encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    toms = [it for it in items if it["drum"] == "tom"]
    assert len(toms) >= 6 and all(it["source"] == "drumsep" and "classifier_only" in it["evidence"] for it in toms)
    assert max(it["conf"] for it in toms) <= 0.5
    ref = [h["t"] for h in truth()["drum_hits"] if h["drum"] == "tom"]
    assert core.match_f1([it["t"] for it in toms], ref, TOL)[0] >= 0.7


def test_ring_tells_a_cymbal_from_a_kick_click():
    ride = 0.3 * _burst(3000, 12000, 0.4, dur=0.6, seed=1)
    click = 0.3 * _burst(3000, 12000, 0.004, dur=0.05, seed=2)
    kick = _kick()
    n = 2 * SR
    x_ride = _place(n, [(SR // 2, ride)])
    x_click = _place(n, [(SR // 2, click), (SR // 2, 2.0 * kick)])
    hf, decay = core._ring(x_ride, SR, SR // 2)
    assert hf >= 14.0 and decay <= 13.0
    hf2, decay2 = core._ring(x_click, SR, SR // 2)
    assert not (hf2 >= 14.0 and decay2 <= 13.0), (hf2, decay2)


def test_cymbal_far_under_the_kit_needs_ring_and_classifier_confirmation():
    """A ride hit 15 dB under the kit's own level (past the tight gate) stays only when it rings AND the classifier on the
    full drum stem also finds it; unconfirmed it is leakage."""
    n = 6 * SR
    kick = _kick()
    strong = [(int((1.0 + i) * SR), 1.0 * kick) for i in range(4)]
    ride_hits = [(int((1.0 + i) * SR), (0.22 if i < 2 else 0.04) * _burst(3000, 12000, 0.4, dur=0.6, seed=10 + i)) for i in range(4)]
    subs = {"kick": _place(n, strong), "ride": _place(n, ride_hits)}
    unconf, st0 = core.drumsep_hits(subs, SR)
    conf, _ = core.drumsep_hits(subs, SR, cymbal_confirm=[1.0 + i for i in range(4)])
    assert [round(h.t, 2) for h in unconf if h.drum == "cymbal"] == [1.0, 2.0] and st0["cymbal_leak_dropped"] == 2
    assert [round(h.t, 2) for h in conf if h.drum == "cymbal"] == [1.0, 2.0, 3.0, 4.0]
