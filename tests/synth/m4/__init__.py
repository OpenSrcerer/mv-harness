"""Synthetic generators for the harmony and mood tests (module M4): chord progressions with exact chord/key truth, a
modulating piece, and mood stimuli (calm pad, energetic beat, digital silence). Deterministic, float64, mono at 44.1 kHz."""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from tests.synth import primitives

SR = 44100
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = (0, 4, 7)
MINOR = (0, 3, 7)
_SCALE = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10)}


def triad_midi(root_pc: int, quality: str, octave_base: int = 52) -> list[int]:
    """Closed-position triad whose lowest note is the root, inside [octave_base, octave_base + 12)."""
    r = octave_base + (root_pc - octave_base) % 12
    iv = MAJOR if quality == "maj" else MINOR
    return [r + i for i in iv]


def beat_grid(duration: float, bpm: float = 120.0, beats_per_bar: int = 4) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Beat and bar event items (as the rhythm stage writes them) for a steady grid starting at t = 0."""
    spb = 60.0 / bpm
    n = int(duration / spb)
    beats = [{"t": round(i * spb, 6), "beat_index": i, "in_pulse": True} for i in range(n)]
    bars = [{"bar": i // beats_per_bar + 1, "t": round(i * spb, 6), "d": round(beats_per_bar * spb, 6), "beats_in_bar": beats_per_bar,
             "n_beats": beats_per_bar, "first_beat": i, "pickup": False, "in_pulse": True, "conf": 1.0}
            for i in range(0, n, beats_per_bar)]
    return beats, bars


def progression(chords: Sequence[tuple[int, str]], *, bars_per_chord: int = 1, repeats: int = 4, bpm: float = 120.0,
                program: str = "piano", bass: bool = True, lead_in_s: float = 0.0, sr: int = SR) -> tuple[np.ndarray, int, dict[str, Any]]:
    """Render ``chords`` ([(root_pc, 'maj'|'min')]) ``repeats`` times, one chord per ``bars_per_chord`` bars.

    Truth: chords [{t, d, root_pc, quality, label}] (time-exact), the beat grid and the duration."""
    spb = 60.0 / bpm
    dur_chord = 4 * spb * bars_per_chord
    notes, bnotes, truth_chords = [], [], []
    t = lead_in_s
    for _ in range(repeats):
        for root, q in chords:
            for m in triad_midi(root, q):
                notes.append((t, dur_chord - 0.05, m, 0.7))
            if bass:
                bm = 36 + (root - 36) % 12
                bnotes.append((t, dur_chord - 0.05, bm, 0.9))
            truth_chords.append({"t": round(t, 6), "d": round(dur_chord, 6), "root_pc": root, "quality": q, "label": f"{NAMES[root]}:{q}"})
            t += dur_chord
    total = t + 0.5
    x = np.zeros(int(total * sr))
    a, _, _ = primitives.midi_render(notes, program=program, bpm=bpm, tail_s=0.4, sr=sr)
    x[: min(len(a), len(x))] += a[: len(x)]
    if bass:
        b, _, _ = primitives.midi_render(bnotes, program="bass", bpm=bpm, tail_s=0.2, sr=sr)
        x[: min(len(b), len(x))] += b[: len(x)]
    x = 0.8 * x / max(float(np.abs(x).max()), 1e-9)
    beats, bars = beat_grid(total, bpm)
    return x, sr, {"chords": truth_chords, "beats": beats, "bars": bars, "duration": total, "bpm": bpm}


def cadence(tonic_pc: int, mode: str) -> list[tuple[int, str]]:
    """I-IV-V-I (major) or i-iv-V-i (minor), the V major in both."""
    if mode == "major":
        return [(tonic_pc, "maj"), ((tonic_pc + 5) % 12, "maj"), ((tonic_pc + 7) % 12, "maj"), (tonic_pc, "maj")]
    return [(tonic_pc, "min"), ((tonic_pc + 5) % 12, "min"), ((tonic_pc + 7) % 12, "maj"), (tonic_pc, "min")]


def modulating(first: tuple[int, str], second: tuple[int, str], seg_s: float = 48.0, bpm: float = 120.0, sr: int = SR):
    """Two cadence loops in different keys back to back (seg_s each). Truth key regions."""
    reps = int(round(seg_s / (16 * 60.0 / bpm * 0.5)))   # one cadence = 4 bars = 8 s at 120 BPM
    reps = max(reps, 1)
    xa, _, ta = progression(cadence(*first), repeats=reps, bpm=bpm, sr=sr)
    xb, _, tb = progression(cadence(*second), repeats=reps, bpm=bpm, sr=sr)
    x = np.concatenate([xa, xb])
    beats, bars = beat_grid(len(x) / sr, bpm)
    return x, sr, {"regions": [{"t": 0.0, "d": len(xa) / sr, "tonic_pc": first[0], "mode": first[1]},
                               {"t": len(xa) / sr, "d": len(xb) / sr, "tonic_pc": second[0], "mode": second[1]}],
                   "beats": beats, "bars": bars, "duration": len(x) / sr, "chords": ta["chords"] + [dict(c, t=c["t"] + len(xa) / sr) for c in tb["chords"]]}


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


# ------------------------------------------------------------------------------------------------ mood stimuli
def calm_pad(seconds: float = 30.0, sr: int = SR) -> np.ndarray:
    """Quiet, slow, soft sustained pad chords (low arousal)."""
    notes = []
    t = 0.0
    chords = [(57, 60, 64), (53, 57, 60), (55, 59, 62), (52, 55, 59)]
    i = 0
    while t < seconds:
        for m in chords[i % 4]:
            notes.append((t, 7.5, m, 0.35))
        t += 8.0
        i += 1
    x, _, _ = primitives.midi_render(notes, program="pad", bpm=60, tail_s=1.0, sr=sr)
    x = x[: int(seconds * sr)]
    return (0.12 * x / max(float(np.abs(x).max()), 1e-9)).astype(np.float64)


def energetic_beat(seconds: float = 30.0, bpm: float = 170.0, sr: int = SR, seed: int = 7) -> np.ndarray:
    """Loud, dense, fast: four-on-the-floor kick, noise hats on 16ths, saw stabs and a driving bass (high arousal)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    x = np.zeros(n)
    spb = 60.0 / bpm
    nk = int(0.12 * sr)
    tk = np.arange(nk) / sr
    kick = np.sin(2 * np.pi * (45 + 110 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 18)
    nh = int(0.03 * sr)
    t = 0.0
    k = 0
    while t < seconds - 0.2:
        a = int(t * sr)
        if k % 4 == 0 or True:
            x[a:a + nk] += 0.9 * kick[: min(nk, n - a)]
        for sub in range(4):
            b = int((t + sub * spb / 4) * sr)
            m = min(nh, n - b)
            if m > 0:
                x[b:b + m] += 0.25 * rng.standard_normal(m) * np.exp(-np.arange(m) / (0.008 * sr))
        t += spb
        k += 1
    notes = []
    for i in range(int(seconds / spb)):
        for m in ((57, 60, 64) if (i // 4) % 2 == 0 else (55, 59, 62)):
            notes.append((i * spb, spb * 0.45, m + 12, 0.9))
    stab, _, _ = primitives.midi_render(notes, program="saw", bpm=bpm, tail_s=0.2, sr=sr)
    x[: min(n, len(stab))] += 0.5 * stab[:n]
    bn = [(i * spb / 2, spb * 0.4, 33 if (i // 8) % 2 == 0 else 31, 1.0) for i in range(int(seconds / spb * 2))]
    bs, _, _ = primitives.midi_render(bn, program="bass", bpm=bpm, tail_s=0.1, sr=sr)
    x[: min(n, len(bs))] += 0.6 * bs[:n]
    return (0.9 * x / max(float(np.abs(x).max()), 1e-9)).astype(np.float64)
