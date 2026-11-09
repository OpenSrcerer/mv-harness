"""W4A-S19 (hihat bleed gate) and W4A-KICKCURVE (one agent-facing kick curve under the mix fallback). Synthetic hits."""
from __future__ import annotations

import numpy as np

from mvh.stages.drums import core, mix_kick_hits
from mvh.stages.drums.hats import HatGateParams, gate_hats


def _hat(t, rise):
    return core.Hit(t=t, sample=0, drum="hat", level_db=-30.0, peak=0.1, rise_db=rise, vel=0.5)


def test_bleed_heavy_hihat_stem_keeps_confirmed_or_strong_strokes():
    grid = [0.25 * k for k in range(40)]                   # real strokes on the 16th grid (120 BPM)
    rng = np.random.default_rng(3)
    wash = sorted(float(t) for t in rng.uniform(0.0, 10.0, 400) if min(abs(t - g) for g in grid) > 0.04)[:160]  # guitar wash
    hits = [_hat(t, 4.0) for t in wash] + [_hat(t, 4.0) for t in grid[:20]] + [_hat(t, 14.0) for t in grid[20:]]
    hits.append(core.Hit(t=1.0, sample=0, drum="kick", level_db=-20.0, peak=0.5, rise_db=20.0, vel=0.9))
    mix_high = grid[:20]                                   # the mix confirms the first 20 strokes
    out, st = gate_hats(hits, mix_high, HatGateParams())
    assert st["applied"] and st["confirmed_share"] < 0.4
    kept = sorted(h.t for h in out if h.drum == "hat")
    assert len(kept) == 40 and all(any(abs(k - g) < 1e-9 for g in grid) for k in kept)
    assert sum(1 for h in out if h.drum == "kick") == 1


def test_clean_hihat_stem_is_left_alone():
    grid = [0.25 * k for k in range(40)]
    hits = [_hat(t, 3.0) for t in grid]                    # quiet closed hats (low rise), all confirmed by the mix
    out, st = gate_hats(hits, grid[::2], HatGateParams())  # half confirmed: share 0.5 >= 0.4
    assert not st["applied"] and len(out) == len(hits)
    out, st = gate_hats(hits, None, HatGateParams())
    assert not st["applied"] and len(out) == len(hits)


def test_mix_fallback_kick_curve_flashes_on_every_agent_kick():
    items = [{"t": 0.5 + 0.5 * k, "strength": s} for k, s in enumerate([2.0, 0.4, 1.0, 0.3, 1.8] * 8)]
    env = core.envelopes(mix_kick_hits(items), 2200)["kick"].astype(float)
    peaks = [i / 100 for i in range(1, len(env) - 1) if env[i] > 0.1 and env[i] >= env[i - 1] and env[i] > env[i + 1]]
    for it in items:
        assert min(abs(p - it["t"]) for p in peaks) <= 0.03, it
    assert len(peaks) == len(items)
