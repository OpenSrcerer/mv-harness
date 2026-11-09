"""R-ML review M3a round 2, finding N1: the F1 fix's cymbal gate deletes every ride / crash of a softer passage.

``drums.core.drumsep_hits`` (fix round) drops a ride / crash hit more than ``cym_gate_db`` = 12 dB under the 2nd
loudest stroke of its own sub-stem, song-wide. A song whose drummer plays a verse 13 dB softer than the chorus (an
ordinary dynamic range for a rock song) therefore loses every cymbal of that verse, on CLEAN sub-stems (no separator
involved), while kick, snare and hat of the same passage survive down to 20+ dB (their gate is the 30 dB
``rel_gate_db``). Measured on the generator's sub-stems with the whole kit 13 dB down in 16.9-20.95 s: cymbal
recall in the window 0/9 (8/9 at 0-10 dB down), song cymbal F1 0.974 -> 0.687; kick/snare/hat recall 1.0.
Synthetic input only (fast).
"""
from __future__ import annotations

from m3a_rml_util import oracle_substems, truth

LO, HI = 16.9, 20.95


def _softer(subs, sr, db):
    g = 10 ** (-db / 20)
    out = {}
    for k, v in subs.items():
        w = v.copy()
        w[int(LO * sr):int(HI * sr)] *= g
        out[k] = w
    return out


def test_a_kit_played_13_db_softer_keeps_its_cymbals():
    from mvh.stages.drums import core

    subs, sr = oracle_substems()
    hits, st = core.drumsep_hits(_softer(subs, sr, 13.0), sr)
    rec = {}
    for d in ("kick", "snare", "hat", "cymbal"):
        ref = [h["t"] for h in truth()["drum_hits"] if h["drum"] == d and LO <= h["t"] < HI]
        est = [h.t for h in hits if h.drum == d and LO - 0.05 <= h.t < HI]
        rec[d] = round(core.match_f1(est, ref, 0.010)[2], 3)
    assert rec["cymbal"] >= 0.7, (f"recall in the softer passage (kit -13 dB): {rec}; cymbal_leak_dropped="
                                  f"{st.get('cymbal_leak_dropped')} (cym_gate_db=12 dB under the stem's 2nd loudest stroke)")
