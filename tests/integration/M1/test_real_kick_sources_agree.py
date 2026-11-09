"""Seam S06 (M1, with M3a): two kick timelines reach the agents. On MEGAFAUNA spectral hits.kick has 335 events and
the drums stage (DrumSep kick stem) 647; only 42 % of hits.kick have a drums kick within 30 ms, and 23 % the other
way (Newton: 94 % / 97 %). choreo and cues read both. A fused kick (spectral + DrumSep, a W2 change request that
needs drums in spectral's deps) or an explicit precedence rule for consumers is needed."""

from __future__ import annotations

import bisect


def _near(ts, t):
    i = bisect.bisect_left(ts, t)
    return min(abs(ts[j] - t) for j in (i - 1, i) if 0 <= j < len(ts))


def test_real_megafauna_kick_timelines_agree(real_song):
    s = real_song("megafauna")
    dk = sorted(h["t"] for h in s.events("drum_hits") if h["drum"] == "kick")
    hk = sorted(h["t"] for h in s.events("hits.kick"))
    a = sum(1 for t in hk if _near(dk, t) <= 0.03) / len(hk)
    b = sum(1 for t in dk if _near(hk, t) <= 0.03) / len(dk)
    assert a >= 0.7 and b >= 0.7, f"hits.kick matched {a:.2f}, drum kicks matched {b:.2f}"
