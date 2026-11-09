"""R-ML review M3a round 3, finding R3-1: a ride played in 8th notes at an ordinary tempo loses most of its strokes,
on CLEAN sub-stems.

``drums.core.drumsep_hits`` detects ride / crash candidates with the broadband rise floor ``cymbal_rise_db`` = 8 dB
(``detect(..., rise_db=max(prm.rise_db, cymbal_rise_db))``). A ride rings: each new stroke rises over the ring of the
previous one, and the closer the strokes the smaller the rise. The synthetic song only has quarter-note rides 0.5 s
apart (rise 12.7-15 dB), so the module's F1 gates never exercise a ride pattern. Built here from ONE stroke of the
generator's clean ride stem tiled at a uniform spacing (no separator involved): 8ths at 120 bpm (0.25 s) rise 8.2 dB
and survive by 0.2 dB; 8ths at 140 bpm (0.214 s) rise ~6.5 dB and 8ths at 150 bpm (0.2 s) ~5.5 dB, and recall
collapses (measured 3/32 with the quarter-note strokes doubled at +0.214 s). Kick / snare / hat use a 2 dB floor.
With ``cymbal_rise_db=4`` recall is 1.0 (precision 1.0) at 100-150 bpm. End to end (the synthetic MIX with its ride
part doubled at +0.214 s, real ROCm separation, round 3): ride recall 0.219 (7/32), song cymbal F1 0.385 (gate 0.7).
Synthetic input only (fast).
"""
from __future__ import annotations

import numpy as np
import pytest
from m3a_rml_util import oracle_substems, truth

LO, HI = 17.0, 24.5   # the ride passage of the synthetic song


def _tiled_ride(subs, sr, spacing):
    rides = sorted(h["t"] for h in truth()["drum_hits"] if h.get("inst") == "ride")
    a = int((rides[1] - 0.002) * sr)          # 17.5 s: a ride stroke with no crash on it
    one = subs["ride"][a:a + int(0.5 * sr)].copy()
    one *= np.minimum(1.0, np.linspace(40.0, 0.0, one.size))   # fade out the last 2.5 % (no click at the cut)
    x = np.zeros_like(subs["ride"])
    times = []
    t = LO
    while t < HI:
        s = int(round(t * sr)) - int(0.002 * sr)
        x[s:s + one.size] += one[: x.size - s]
        times.append(t)
        t += spacing
    return x, times


@pytest.mark.parametrize("bpm", [140, 150])
def test_an_eighth_note_ride_keeps_its_strokes(bpm):
    from mvh.stages.drums import core

    subs, sr = oracle_substems()
    spacing = 60.0 / bpm / 2
    ride, ref = _tiled_ride(subs, sr, spacing)
    hits, st = core.drumsep_hits(dict(subs, ride=ride), sr)
    est = [h.t for h in hits if h.drum == "cymbal" and LO - 0.05 <= h.t < HI + 0.05]
    f1, p, rc, tp = core.match_f1(est, ref, 0.012)
    cand_rises = sorted(round(h.rise_db, 1) for h in core.detect(ride, sr, drum="cymbal"))[:4]
    assert rc >= 0.7, (f"8th-note ride at {bpm} bpm ({spacing * 1000:.0f} ms apart) on a clean ride stem: recall {rc:.3f} "
                       f"({tp}/{len(ref)}), precision {p:.3f}; lowest stroke rises {cand_rises} dB vs the 8 dB cymbal floor; "
                       f"candidates {st['candidates'].get('ride')}")
