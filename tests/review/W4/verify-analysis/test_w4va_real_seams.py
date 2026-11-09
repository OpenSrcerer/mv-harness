"""W4 verifier (analysis group, round 1): precision of the new S18 half-time backbeat vote on the fixer's real folders.

rhythm 1.1.1 labels beats half_time from the mix's percussive 1.5-8 kHz flux (beat 3 vs beats 2 + 4). On Newton it is
right (75 of 90 strong drum-stem snares in the half-time span land on beat 3) and on Versatile's local runs too (24 of
28). On MEGAFAUNA it adds a NEW half_time segment (89.3-99.5 s, a 'break' / 'inst' passage) where the drum stem has 3
strong snares in 10 s, all on beats 2 / 4 (none on 3), so the label has no backbeat behind it; and Versatile's last
run (211.8-227.5 s, the outro) has no kick or snare at all (13 hats). Minor (MEGAFAUNA 4.7 % of the song, Versatile
15.7 s; the global feel stays normal).
Folders: ``out/_wip/w4fix-analysis/<slug>`` (``$W4VA_BASE``). Numbers only.
"""

from __future__ import annotations

import numpy as np
import pytest
from w4va_support import base


@pytest.mark.parametrize("slug", ["newton-vs-nye", "versatile", "megafauna"])
def test_w4va_half_time_spans_have_a_beat3_backbeat(slug):
    f = base(slug)
    beats = f.events("beats")
    bt = np.array([b["t"] for b in beats])
    spans = [(s["t"], s["t"] + s["d"]) for s in f.events("tempo_segments") if s.get("feel") == "half_time"]
    if not spans:
        pytest.skip(f"{slug}: no half_time segment")
    bad = []
    for lo, hi in spans:
        pos = []
        for h in f.events("drum_hits"):
            if h["drum"] != "snare" or h["vel"] < 0.3 or not lo <= h["t"] < hi:
                continue
            j = int(np.argmin(np.abs(bt - h["t"])))
            if abs(bt[j] - h["t"]) <= 0.06:
                pos.append(beats[j]["beat_in_bar"])
        on3, on24 = pos.count(3), pos.count(2) + pos.count(4)
        if on3 < max(2, on24):
            bad.append((round(lo, 1), round(hi, 1), {"on_3": on3, "on_2_4": on24}))
    assert not bad, f"{slug}: half_time segments without a beat-3 snare backbeat (strong drum-stem snares): {bad}"
