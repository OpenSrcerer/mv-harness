"""Shared helpers for the W3 critic tests (beat-grid lookups)."""

from __future__ import annotations

import bisect


def nearest_beat(beats: list[dict], t: float, tol: float = 0.05):
    """The beats.json item within tol of t, or None."""
    bt = [b["t"] for b in beats]
    i = bisect.bisect_left(bt, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(bt) and abs(bt[j] - t) <= tol and (best is None or abs(bt[j] - t) < abs(bt[best] - t)):
            best = j
    return None if best is None else beats[best]


def beat_phase(beats: list[dict], t: float):
    """(fraction of the beat in [0, 1), beat index) for t between two in-pulse beats, else None."""
    bt = [b["t"] for b in beats]
    k = bisect.bisect_right(bt, t) - 1
    if k < 0 or k + 1 >= len(bt) or not (beats[k]["in_pulse"] and beats[k + 1]["in_pulse"]):
        return None
    return (t - bt[k]) / (bt[k + 1] - bt[k]), k
