"""Seam S05 (M2, with M1): in Jeremy the band enters at 19.47 s (bar 9). dynamics opens its first loud part there and
the only impact (+5.9 LU, bass +13 dB) is there, but structure starts verse#1 one bar later (21.80 s, bar 10) and
keeps bar 9 in the intro. A choreographer cuts at the band entry: the section grid should agree with a major impact
that sits on a downbeat."""

from __future__ import annotations


def test_real_jeremy_major_impact_starts_a_section(real_song):
    s = real_song("jeremy")
    imps = sorted(s.events("impacts"), key=lambda i: -float(i.get("strength", 0)))
    assert imps
    top = imps[0]
    beats = [b["t"] for b in s.events("beats")]
    beat = sorted(b2 - b1 for b1, b2 in zip(beats, beats[1:]))[len(beats) // 2]
    starts = [x["t"] for x in s.events("sections")]
    gap = min(abs(t - top["t"]) for t in starts)
    assert gap <= beat, f"strongest impact {top['t']:.2f} s is {gap:.2f} s from the nearest section start"
