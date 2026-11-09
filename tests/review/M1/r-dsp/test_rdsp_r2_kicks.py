"""R-DSP review round 2 (M1 spectral, hits.kick) after the fix of B1 / M1.

The fix drops a click-less kick-band hit within kick_refractory_s (0.30 s) of a kept event, weights the >= 1 kHz click
step fully in the kick onset score and grades kick_conf by click evidence. Click evidence is the discriminator, so:

* B1 is NOT fixed when hats play: a hat in the tail of a kick supplies the click, and the bass/kick beating (or the kick
  decay itself) is accepted as a second kick. On the contract fixture song kicks are still timed onto a hat ~100 ms
  earlier (F1 0.88 < PLAN §7 0.95).
* NEW (regression): the refractory drops real kicks whose click is masked (crash/ride wash, guitars): 8th-note kicks
  under a crash lose 17 % recall; on Jeremy a quarter of the unambiguous kicks of the DrumSep kick stem disappear and
  the builder's own W0 count test (tests/unit/spectral::test_real_song_kick_counts) now fails on 3 of 4 songs.
* NEW (pre-existing): 16th-note double kicks at 160 BPM (94 ms apart) give 3 events for 96 kicks.

PLAN §7: kick events F1 >= 0.95 at +-10 ms, event time = the one-shot's sample onset."""

from __future__ import annotations

import numpy as np
import pytest
from rdsp_m1_support import (
    SR,
    f1,
    grid_times,
    kick_stem_attacks,
    kicks_bass_hats,
    kicks_on_a_grid,
    run_spectral,
    synth_song,
)


def _kick_items(ctx) -> list[dict]:
    return ctx.written_events("hits.kick")["items"]


def _extras(items, ref, tol=0.010):
    r = np.asarray(ref)
    return [(round(float(i["t"] - r[np.argmin(np.abs(r - i["t"]))]), 3), i["viz"], round(i["env"], 2), i["kick_conf"])
            for i in items if np.min(np.abs(r - i["t"])) > tol]


# ------------------------------------------------------------------------------------------------ B1 (not fixed)
@pytest.mark.parametrize("hats,bass_gain", [("16ths", 0.6), ("offbeat", 0.6), ("16ths", 0.0)],
                         ids=["bass+16th-hats", "bass+offbeat-hats", "16th-hats-no-bass"])
def test_kick_events_with_hats_are_not_doubled(hats, bass_gain, tmp_path):
    """B1 texture (four-on-the-floor fixture kicks, one sustained bass note per bar) plus closed hats, the most common
    house/pop drum texture. Without hats the fix gives F1 1.0; with hats a hat 120 ms (16ths) or 250 ms (off-beat) after a
    kick supplies the click evidence, so the bass beating / kick decay at the hat is kept as a kick (kick_conf 0.8-1.0):
    16ths F1 0.72 (P 0.56), off-beat F1 0.85 (P 0.75), hats without bass F1 0.85."""
    x, ref = kicks_bass_hats(hats=hats, bass_gain=bass_gain)
    items = _kick_items(run_spectral(x, SR, tmp_path / "s"))
    f, p, r = f1([i["t"] for i in items], ref, 0.010)
    assert f >= 0.95, f"{hats} hats, bass {bass_gain}: F1 {f:.3f} (P {p:.3f}, R {r:.3f}), {len(items)} events for {len(ref)} kicks; extra (offset s, viz, env, kick_conf): {_extras(items, ref)[:6]}"


def test_kick_events_on_the_contract_fixture_song_meet_plan(synth_ok, tmp_path):
    """The scored synthetic song (85 kick one-shots): F1 0.880 (P 0.856, R 0.906) at +-10 ms. Kicks preceded by a hat
    100 ms earlier are timed onto the hat (events at -0.101 / -0.099 s; the full-weight click step in the kick onset
    score wins inside the [peak - 75 ms, peak + 5 ms] window) and the refractory then drops the kick itself."""
    x, sr, truth, _ = synth_song()
    ref = [h["t"] for h in truth["drum_hits"] if h["inst"] == "kick"]
    items = _kick_items(run_spectral(x, sr, tmp_path / "s"))
    est = np.asarray([i["t"] for i in items])
    f, p, r = f1(est, ref, 0.010)
    missed = [(round(t, 2), round(float(est[np.argmin(np.abs(est - t))] - t), 3)) for t in ref if np.min(np.abs(est - t)) > 0.010]
    assert f >= 0.95, f"fixture song kick F1 {f:.3f} (P {p:.3f}, R {r:.3f}); missed kicks (t, nearest event offset): {missed}"


# ------------------------------------------------------------------------------------------------ NEW: refractory regression
@pytest.mark.parametrize("bpm", [130.0, 150.0])
def test_eighth_note_kicks_under_a_crash_are_kept(bpm, tmp_path):
    """8th-note fixture kicks (231 / 200 ms apart, inside the 0.30 s refractory) under a crash struck every 2 s (rock
    chorus wash). The crash masks the >= 1 kHz click, has_click() is false and the refractory drops real kicks:
    130 BPM R 0.83 (F1 0.91), 150 BPM R 0.89 (F1 0.94). With kick_refractory_s=0 both are 1.0; viz registers 60/64."""
    ts = grid_times(bpm, 2, 8)
    x = kicks_on_a_grid(ts, "fixture", crash_every_s=2.0, crash_gain=0.5)
    items = _kick_items(run_spectral(x, SR, tmp_path / "s"))
    est = np.asarray([i["t"] for i in items])
    f, p, r = f1(est, ts, 0.010)
    missed = [round(t, 2) for t in ts if est.size == 0 or np.min(np.abs(est - t)) > 0.010]
    assert f >= 0.95, f"{bpm:g} BPM 8th kicks under a crash: F1 {f:.3f} (P {p:.3f}, R {r:.3f}); missed {missed}"


@pytest.mark.real
@pytest.mark.slow
def test_jeremy_unambiguous_kicks_are_kept(tmp_path):
    """Jeremy (real-jeremy): onsets of the DrumSep kick sub-stem that rise >= 20 dB and peak within 6 dB of the stem's
    top level (528 unambiguous kicks). hits.kick recalls 0.733 of them at +-30 ms; with kick_refractory_s=0 it recalls
    0.977 (precision 0.79 -> 0.82 only). The 181 dropped events have a median kick-stem rise of 33 dB at the stem's top
    level, 267 ms after the previous kept event (8th-note kicks under guitars and cymbals). Opt-in: MVH_REAL_TESTS=1."""
    from tests.synth.m1.markers import real_available, real_dir

    if not real_available("jeremy"):
        pytest.skip("real-jeremy fixture missing")
    d = real_dir("jeremy")
    stem = d / "stems" / "drums" / "kick.flac"
    if not stem.is_file():
        pytest.skip("no DrumSep kick stem")
    from mvh.io import audio as aio

    ref = kick_stem_attacks(stem)
    a = aio.decode(d / "_intermediate" / "ingest" / "canonical.wav")
    items = _kick_items(run_spectral(np.asarray(a.samples, np.float64), int(a.sr), tmp_path / "s"))
    f, p, r = f1([i["t"] for i in items], ref, 0.030)
    assert r >= 0.95, f"Jeremy: recall {r:.3f} of {len(ref)} unambiguous kick-stem kicks (precision {p:.3f}, {len(items)} events)"


# ------------------------------------------------------------------------------------------------ NEW: fast double kicks
def test_sixteenth_double_kicks_at_160_bpm(tmp_path):
    """Metal double-bass: 16th-note kicks at 160 BPM (94 ms apart, a 70 ms-decay kick with a click), 6 bars. The viz
    kick band (46 ms analyser) barely dips between kicks, so the attacks fall under HIT_FLOOR, the +-8 s median reference
    is set by the few large attacks at the section edges and every roll kick has x ~ 0.2 < event_x_min: 3 events for 96
    kicks. At 140 BPM (107 ms) all 96 are found. The 400 Hz refinement envelopes resolve every kick."""
    ts = grid_times(160.0, 4, 6)
    x = kicks_on_a_grid(ts, "tight")
    items = _kick_items(run_spectral(x, SR, tmp_path / "s"))
    f, p, r = f1([i["t"] for i in items], ts, 0.010)
    assert f >= 0.95, f"16th kicks at 160 BPM: F1 {f:.3f} (P {p:.3f}, R {r:.3f}), {len(items)} events for {len(ts)} kicks"
