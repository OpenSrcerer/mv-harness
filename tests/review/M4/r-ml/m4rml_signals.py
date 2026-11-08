"""Synthetic signals for the R-ML M4 review tests (no real audio, no lyrics)."""
from __future__ import annotations

import numpy as np

SR22 = 22050


def _note(midi: float, dur: float, sr: int, amp: float = 0.2) -> np.ndarray:
    t = np.arange(int(dur * sr)) / sr
    f = 440.0 * 2 ** ((midi - 69) / 12)
    env = np.minimum(1.0, t / 0.01) * np.exp(-t * 1.5)
    return amp * env * sum((0.6 ** h) * np.sin(2 * np.pi * f * (h + 1) * t) for h in range(6))


def cadence(tonic_pc: int, mode: str, reps: int = 4, dur: float = 2.0, sr: int = SR22) -> np.ndarray:
    """I-IV-V-I (major) or i-iv-V-i (minor) with a bass root, additive piano-like tones, peak 0.5."""
    base = 48 + tonic_pc
    third = 4 if mode == "major" else 3
    seq = [(0, third), (5, third), (7, 4), (0, third)]
    parts = []
    for _ in range(reps):
        for r, th in seq:
            y = sum(_note(base + r + i, dur, sr) for i in (0, th, 7)) + _note(base + r - 12, dur, sr, 0.3)
            parts.append(y)
    y = np.concatenate(parts)
    return (y / np.abs(y).max() * 0.5).astype(np.float32)


def beat_grid(duration: float, period: float = 0.5, beats_per_bar: int = 4) -> tuple[list[dict], list[dict]]:
    """A steady beat grid (events/beats.json and events/bars.json shaped items)."""
    beats, bars = [], []
    n = int(duration / period)
    for i in range(n):
        t = round(i * period, 6)
        beats.append({"t": t, "beat_index": i, "in_pulse": True, "bar": i // beats_per_bar + 1,
                      "beat_in_bar": i % beats_per_bar + 1})
        if i % beats_per_bar == 0:
            bars.append({"t": t, "bar": i // beats_per_bar + 1, "in_pulse": True,
                         "d": period * beats_per_bar, "beats_in_bar": beats_per_bar})
    return beats, bars
