"""W4A-S17 (noisy-kit groove consolidation) on synthetic groove rows."""
from __future__ import annotations

import numpy as np

from mvh.stages.choreo import consolidate_grooves

P = {"groove_noise_singletons": 0.2, "groove_min_bars": 3, "groove_absorb_similarity": 0.6, "groove_absorb_min_vel": 0.3,
     "groove_hat_weight": 0.25}


def _row(bar, kick, snare, gid, rng=None, noise=0):
    pat = {r: [0.0] * 16 for r in ("kick", "snare", "hat", "perc")}
    for k in kick:
        pat["kick"][k] = 0.9
    for k in snare:
        pat["snare"][k] = 0.9
    if rng is not None:
        for _ in range(noise):                          # transcription noise: an extra strong hit on a random step
            pat["kick" if rng.random() < 0.5 else "snare"][int(rng.integers(16))] = 0.6
    for k in range(0, 16, 2):
        pat["hat"][k] = 0.5
    return {"bar": bar, "t": 2.0 * bar, "d": 2.0, "pattern": pat, "groove_id": gid}


def test_noisy_kit_bars_collapse_into_their_section_grooves():
    rng = np.random.default_rng(11)
    rows = [_row(b, (0, 8), (4, 12), f"G{b:02d}", rng, 1) for b in range(1, 17)]          # section A, one id per bar
    rows += [_row(b, (0, 4, 8, 12), (4, 12), f"G{b:02d}", rng, 1) for b in range(17, 33)]  # section B
    secs = [{"id": "S01", "t": 2.0, "d": 32.0, "repeat_group": "A"}, {"id": "S02", "t": 34.0, "d": 32.0, "repeat_group": "B"}]
    rep = consolidate_grooves(rows, secs, P)
    assert rep["applied"]
    ids = {g["groove_id"] for g in rows}
    assert len(ids) / len(rows) <= 0.35, (len(ids), rep)
    a = {g["groove_id"] for g in rows[:16]}
    b = {g["groove_id"] for g in rows[16:]}
    assert not a & b                                       # the two grooves stay apart


def test_clean_kit_is_left_alone():
    rows = [_row(b, (0, 8), (4, 12), "G01") for b in range(1, 13)] + [_row(13, (0, 8), (4, 12, 13, 14, 15), "G02")]
    secs = [{"id": "S01", "t": 2.0, "d": 26.0, "repeat_group": "A"}]
    rep = consolidate_grooves(rows, secs, P)
    assert not rep["applied"] and rows[-1]["groove_id"] == "G02"   # a real fill stays its own groove
