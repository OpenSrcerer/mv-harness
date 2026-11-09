"""W3C-3 (M2 rhythm, R1): the feel label does not see a half-time backbeat.

R1 asks for "a feel label" next to the BPM; a choreographer reads it to pick the dance pulse. rhythm derives
`feel` / `tempo_segments[].feel` only from where the trackers' local tempo sits relative to the grid, never from the
backbeat. In Newton vs Nye (grid 138 BPM, 4/4) 76 % of the strong on-beat snares (vel >= 0.3; 86 of 113) land on
beat 3 and 19 % on beats 2 + 4: a half-time groove (the dance backbeat is at 69 BPM). meta/tempo.json says
feel 'normal' (feel_shares normal 0.94) and every tempo segment after 10 s is 'normal'. Versatile shows the same
pattern (50 % of strong snares on beat 3, feel 'normal'). Jeremy (95 % on 2 + 4) and the synthetic song (97 %) are
correctly 'normal'.
Accepts either fix: feel 'half_time' where the backbeat is on 3, or a grid at half the tempo (snare on 2 and 4).
"""

from __future__ import annotations

from collections import Counter

from w3c_support import nearest_beat


def _snare_beats(f):
    beats = f.events("beats")
    c = Counter()
    for h in f.events("drum_hits"):
        if h["drum"] != "snare" or h["vel"] < 0.3:
            continue
        b = nearest_beat(beats, h["t"])
        if b and b["in_pulse"] and b["beats_in_bar"] == 4:
            c[b["beat_in_bar"]] += 1
    return c


def test_w3c_half_time_backbeat_is_labelled(real_folder):
    f = real_folder("newton-vs-nye")
    c = _snare_beats(f)
    n = sum(c.values())
    assert n >= 40
    share3 = c[3] / n
    tempo = f.json("meta/tempo.json")
    if share3 >= 0.6 and (c[2] + c[4]) / n <= 0.3:
        half_share = (tempo.get("feel_shares") or {}).get("half_time", 0.0)
        assert tempo["feel"] == "half_time" or half_share >= 0.5 or tempo["bpm"] < 100, (
            f"newton-vs-nye: {share3:.0%} of {n} strong on-beat snares land on beat 3 (half-time backbeat at "
            f"{tempo['bpm']:.1f} BPM) but feel={tempo['feel']!r}, feel_shares={tempo.get('feel_shares')}")


def test_w3c_normal_backbeat_stays_normal(real_folder):
    f = real_folder("jeremy")
    c = _snare_beats(f)
    n = sum(c.values())
    assert n >= 40 and (c[2] + c[4]) / n >= 0.8
    assert f.json("meta/tempo.json")["feel"] == "normal"
