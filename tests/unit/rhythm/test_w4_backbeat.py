"""W4A-S18 / W3C-3: a half-time backbeat (snare on beat 3 of 4/4) makes the feel half_time; a 2-and-4 backbeat does not."""
from __future__ import annotations

import numpy as np

from mvh.stages.rhythm.fusion import backbeat_feel


def _grid(snare_beats, n_bars=40, ibi=0.5, noise=0.2, seed=5):
    rng = np.random.default_rng(seed)
    beats = 0.5 + ibi * np.arange(4 * n_bars)
    pos = np.tile([1, 2, 3, 4], n_bars)
    flux = rng.random(int((beats[-1] + 1) * 100)) * noise          # rap / guitar onsets everywhere
    for t, q in zip(beats, pos):
        if q in snare_beats:
            flux[int(round(t * 100))] += 1.0
    return beats, pos, np.full(len(beats), 4), np.ones(len(beats), bool), flux


def test_half_time_backbeat():
    b, pos, met, ip, fl = _grid({3})
    half, rep = backbeat_feel(b, pos, met, ip, fl)
    assert half.mean() > 0.9 and rep["ratio"] > 1.5


def test_normal_backbeat_and_four_on_the_floor():
    for snares in ({2, 4}, {1, 2, 3, 4}):
        b, pos, met, ip, fl = _grid(snares)
        half, rep = backbeat_feel(b, pos, met, ip, fl)
        assert not half.any(), (snares, rep)


def test_waltz_and_short_input_are_never_half_time():
    b, pos, met, ip, fl = _grid({3})
    half, _ = backbeat_feel(b, pos, np.full(len(b), 3), ip, fl)
    assert not half.any()
    half, rep = backbeat_feel(b[:8], pos[:8], met[:8], ip[:8], fl)
    assert not half.any() and rep["ratio"] is None


def test_no_percussion_no_backbeat():
    """A voice alone (random onsets, beat 3 not above the off-beats): never half time (synth_acap had 18 % before)."""
    b, pos, met, ip, fl = _grid(set(), noise=1.0, seed=9)
    rng = np.random.default_rng(1)
    for t, q in zip(b, pos):                      # a sung syllable now and then, sometimes on beat 3
        if q == 3 and rng.random() < 0.5:
            fl[int(round(t * 100))] += 0.6
    half, rep = backbeat_feel(b, pos, met, ip, fl)
    assert not half.any(), rep


def test_hats_only_on_beat_3_need_a_snare_body():
    """W4 verifier N4: a beat-3 accent in the high band only (hats / a synth, no snare body in 150-4000 Hz) is not a
    half-time backbeat; with the body it is."""
    b, pos, met, ip, fl = _grid({3})
    rng = np.random.default_rng(3)
    flat_mid = rng.random(fl.size) * 0.2
    half, rep = backbeat_feel(b, pos, met, ip, fl, flux_mid=flat_mid)
    assert not half.any() and rep.get("dropped_runs"), rep
    body = flat_mid.copy()
    for t, q in zip(b, pos):
        if q == 3:
            body[int(round(t * 100))] += 1.0
    half, rep = backbeat_feel(b, pos, met, ip, fl, flux_mid=body)
    assert half.mean() > 0.9, rep


def test_meter_late_bias_breaks_flat_ties_late():
    """W4V-GAIN-BEATS: with flat evidence (a drumless break, 40 beats) between two stretches of strong downbeats one
    beat apart in phase, the irregular bar(s) go just before the second stretch, whatever the 1e-4 noise."""
    from mvh.stages.rhythm.fusion import decode_meter

    for seed in range(6):
        rng = np.random.default_rng(seed)
        s = rng.random(160) * 1e-4
        s[0:40:4] += 2.0                    # downbeats every 4 beats ...
        s[83:160:4] += 2.0                  # ... after the break shifted by -1 beat
        mp = decode_meter(s, late_bias=0.25)
        irregular = np.flatnonzero(mp.meter == 3)
        assert len(irregular) and irregular.min() >= 70 and irregular.max() <= 83, (seed, irregular)
