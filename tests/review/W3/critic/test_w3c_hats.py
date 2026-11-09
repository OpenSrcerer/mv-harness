"""W3C-4 (M3a drums, R8): Jeremy's hi-hat hits are not on the beat grid.

drum_hits for Jeremy (DrumSep path) holds 988 'hat' hits from the hihat sub-stem. Measured against the beat grid
(which the kicks and snares confirm: within 1/32 beat of a 16th position for 91 % of kicks and 90 % of snares with
vel >= 0.3, ride 80 %), only 37 % of the 496 hats with vel >= 0.3 are, where a uniform scatter gives 25 %; the phase
concentration on the 16th grid is 0.14 (kick 0.92, snare 0.92). On the other songs the hats lock to the grid
(Newton 85 %, synthetic 85 %). So on a distorted rock mix the 'hat' class is mostly not hi-hat strokes (guitar
or cymbal wash bleeding into the hihat sub-stem), and the hat row of the groove matrix, the drums.hat envelope and
hat-driven accents flicker at random for a choreography agent.
"""

from __future__ import annotations

from w3c_support import beat_phase


def _on_grid_share(f, drum, sub=None, vmin=0.3):
    beats = f.events("beats")
    n = ok = 0
    for h in f.events("drum_hits"):
        if h["drum"] != drum or h["vel"] < vmin or (sub and h.get("sub_stem") != sub):
            continue
        ph = beat_phase(beats, h["t"])
        if ph is None:
            continue
        n += 1
        x = ph[0] * 4
        if abs(x - round(x)) / 4 <= 1 / 32:
            ok += 1
    return ok / max(1, n), n


def test_w3c_jeremy_kick_and_snare_confirm_the_grid(real_folder):
    f = real_folder("jeremy")
    for drum in ("kick", "snare"):
        share, n = _on_grid_share(f, drum)
        assert n >= 100 and share >= 0.8, f"jeremy {drum}: {share:.2f} of {n} on the 16th grid"


def test_w3c_jeremy_hats_are_on_the_grid(real_folder):
    f = real_folder("jeremy")
    share, n = _on_grid_share(f, "hat")
    assert n >= 100
    assert share >= 0.6, (f"jeremy: only {share:.0%} of {n} hats (vel >= 0.3) are within 1/32 beat of a 16th position "
                          "(chance 25 %, kick/snare about 90 %): the hat class is mostly not hi-hat strokes")
