"""R-DSP review round 3 (M1 spectral, hits.kick) after fixer-m1-r2 replaced the click refractory by the low band's own
attack (dsp.select_kick_events).

* NEW (regression, blocker): kicks over a moving bass line. The <= 400 Hz "own attack" is the bass instrument's as much as
  the kick's: a bass-note onset (no kick) is emitted as a kick (viz-strength, kick_conf 1.0) and its 0.2 s refractory then
  drops the real kick after it. The builder's own groove() generator (sustained bass notes changing on off-beats, its
  default texture) falls to F1 0.75; the fixer lowered tests/unit/spectral::test_kick_events_with_sub_bass_line from
  recall >= 0.85 to >= 0.7 instead. kick_glide separates the two on these signals (kicks median 1.93, the bass-note
  extras <= 1.29), and select_kick_events' docstring promises a ``glide_song`` rule that the code does not implement.
* R2-M2 NOT fixed beyond the exact test case: 16th double kicks are found at 150-160 BPM with a tight, clicky kick, but
  not at 170 BPM (R 0.81), 180 BPM (3 / 96) or under a crash (160 BPM, 42 / 96: the roll rule needs a >= 15 dB click).

PLAN §7: kick events F1 >= 0.95 at +-10 ms, event time = the one-shot's sample onset."""

from __future__ import annotations

import numpy as np
import pytest
from rdsp_m1_support import SR, bass_riff_kicks, f1, grid_times, kicks_on_a_grid, run_spectral


def _items(ctx) -> list[dict]:
    return ctx.written_events("hits.kick")["items"]


def _extras(items, ref, tol=0.010):
    r = np.asarray(ref)
    return [(round(float(i["t"] - r[np.argmin(np.abs(r - i["t"]))]), 3), i["viz"], i["kick_conf"])
            for i in items if np.min(np.abs(r - i["t"])) > tol]


# ------------------------------------------------------------------------------------------------ NEW: bass-line regression
@pytest.mark.parametrize("kw", [{}, {"seed": 3}, {"syncopated": False}], ids=["default", "seed3", "four-on-the-floor"])
def test_kicks_over_the_builders_groove_bass_line(kw, tmp_path):
    """tests/synth/m1/signals.groove(): fixture kicks, snares, 8th hats, a pad and sustained bass notes that change on the
    off-beats (the generator's comment: 'sub energy that the kick detector must ignore'). Now: default F1 0.754 (P 0.78,
    R 0.73), seed 3 F1 0.739, straight four-on-the-floor F1 0.880 (P 0.786: 12 bass-note onsets emitted as kicks with
    kick_conf ~1.0). Without the bass the same grooves score 0.976 / 1.0."""
    from tests.synth.m1.signals import groove

    x, sr, truth = groove(**kw)
    ref = [k["t"] for k in truth["kick"]]
    items = _items(run_spectral(x, sr, tmp_path / "s"))
    f, p, r = f1([i["t"] for i in items], ref, 0.010)
    assert f >= 0.95, f"groove{kw}: F1 {f:.3f} (P {p:.3f}, R {r:.3f}), {len(items)} events for {len(ref)} kicks; extras (offset s, viz, kick_conf): {_extras(items, ref)[:6]}"


def test_kicks_over_a_sixteenth_bass_riff(tmp_path):
    """Four-on-the-floor fixture kicks over a staccato 16th-note bass riff with 16th hats (rock / EDM gallop): the G1
    note one 16th before each bar's downbeat is a kick-band attack with a low-band attack and a hat click, and is
    emitted as a kick (viz true) in every bar: 40 events for 32 kicks, F1 0.889 (same without hats)."""
    x, ref = bass_riff_kicks()
    items = _items(run_spectral(x, SR, tmp_path / "s"))
    f, p, r = f1([i["t"] for i in items], ref, 0.010)
    assert f >= 0.95, f"16th bass riff: F1 {f:.3f} (P {p:.3f}, R {r:.3f}), {len(items)} events for {len(ref)} kicks; extras: {_extras(items, ref)[:6]}"


# ------------------------------------------------------------------------------------------------ R2-M2 (not fixed beyond the test case)
@pytest.mark.parametrize("bpm,crash", [(170.0, False), (180.0, False), (160.0, True)], ids=["170bpm", "180bpm", "160bpm-under-crash"])
def test_sixteenth_double_kicks_beyond_the_tested_tempo(bpm, crash, tmp_path):
    """The R2-M2 texture (tight 70 ms-decay kick with a click, 16th notes, 6 bars) at other tempos and under a crash
    every 2 s. 150 and 160 BPM: 96 / 96. 170 BPM (88 ms apart): 78 / 96; 180 BPM (83 ms): 3 / 96; 160 BPM under a crash:
    42 / 96 (the step-only 'roll' candidates need a >= 15 dB >= 1 kHz click, which the crash masks). Metal double bass
    runs 16ths at 160-220 BPM, usually under cymbals."""
    ts = grid_times(bpm, 4, 6)
    x = kicks_on_a_grid(ts, "tight", crash_every_s=2.0 if crash else None, crash_gain=0.5)
    items = _items(run_spectral(x, SR, tmp_path / "s"))
    f, p, r = f1([i["t"] for i in items], ts, 0.010)
    assert f >= 0.95, f"16th kicks at {bpm:g} BPM{' under a crash' if crash else ''}: F1 {f:.3f} (P {p:.3f}, R {r:.3f}), {len(items)} events for {len(ts)} kicks"


# ------------------------------------------------------------------------------------------------ R2-M1 (not fixed over a held bass note)
@pytest.mark.parametrize("bpm", [140.0, 160.0])
def test_rock_eighth_kick_pairs_over_a_held_bass_note(bpm, tmp_path):
    """The rock beat (kicks on 1, 1&, 3, 3&; 8th hats) over a bass note held for two beats from each kick pair. 100-130
    BPM: 32 / 32. 140 BPM: 12 of the 16 '&' kicks are lost (R 0.625): a lost kick's kick-band attack is x 0.37 with v_free 0,
    so the candidate is dropped as envelope-less, and as a low-band step its excess over the held bass is 3.1 dB < 3.5.
    160 BPM: all 16 '&' kicks lost (R 0.5; low step 3 dB). Without the bass note both tempos give 1.0. The R2-M1 crash
    test passes only because it has no bass."""
    x, ref = bass_riff_kicks(bpm=bpm, kick_steps=(0, 2, 8, 10), bass_steps=(0, 8), staccato=7.6, hat_steps=range(0, 16, 2))
    items = _items(run_spectral(x, SR, tmp_path / "s"))
    est = np.asarray([i["t"] for i in items])
    f, p, r = f1(est, ref, 0.010)
    beat = 60.0 / bpm
    missed_steps = sorted({round(((t - 0.5) % (4 * beat)) / (beat / 4)) for t in ref if est.size == 0 or np.min(np.abs(est - t)) > 0.010})
    assert f >= 0.95, f"rock 8th kicks over a held bass at {bpm:g} BPM: F1 {f:.3f} (P {p:.3f}, R {r:.3f}); missed 16th steps {missed_steps}"
