"""Kick-design and mix-situation signals for the spectral kick tests (fixer-m1-r4, review R4-M1/M2/M3, m20, m21).

Independent of the review's generators (other kick parameters, tempos and gains), so the unit tests check that the
kick rules generalise rather than re-run the review's exact signals. Truth = each one-shot's first sample."""

from __future__ import annotations

import numpy as np
from scipy import signal as ss
from tests.synth import dsp as sd
from tests.synth.m1.signals import _faded

SR = 44100


def kick_shot(kind: str, sr: int = SR) -> np.ndarray:
    """One kick one-shot (peak 0.9). kinds: fixture (the contract song's kick), acoustic (62 Hz body, small sweep, shell
    tone, beater click), tr808 (bridged-T sine 82 -> 48 Hz, long decay, no click), tr909 (fast 210 -> 52 Hz sweep +
    click)."""
    rng = np.random.default_rng(11)
    if kind == "fixture":
        z = _faded(sd.kick(0.95, sr), sr)
        return 0.9 * z / np.max(np.abs(z))
    if kind == "acoustic":
        n = int(0.5 * sr)
        t = np.arange(n) / sr
        z = np.sin(2 * np.pi * np.cumsum(62 + 14 * np.exp(-t / 0.025)) / sr) * np.exp(-t / 0.11)
        z += 0.3 * np.sin(2 * np.pi * 120 * t) * np.exp(-t / 0.045)
        z += 0.45 * ss.sosfilt(ss.butter(2, [1800, 6500], "bandpass", fs=sr, output="sos"), rng.standard_normal(n)) * np.exp(-t / 0.004)
    elif kind == "tr808":
        n = int(0.9 * sr)
        t = np.arange(n) / sr
        z = np.sin(2 * np.pi * np.cumsum(48 + 34 * np.exp(-t / 0.018)) / sr) * np.exp(-t / 0.3)
    elif kind == "tr909":
        n = int(0.5 * sr)
        t = np.arange(n) / sr
        z = np.sin(2 * np.pi * np.cumsum(52 + 158 * np.exp(-t / 0.011)) / sr) * np.exp(-t / 0.18)
        z += 0.3 * ss.sosfilt(ss.butter(4, 2200, "highpass", fs=sr, output="sos"), rng.standard_normal(n)) * np.exp(-t / 0.003)
    else:
        raise KeyError(kind)
    k = min(z.size, int(0.05 * sr))
    z[z.size - k:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k))
    return 0.9 * z / np.max(np.abs(z))


def _finish(x: np.ndarray) -> np.ndarray:
    x = x + 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    return x * 10 ** (-1 / 20) / np.max(np.abs(x))


def kicks_over_held_bass(kind: str, *, bpm: float = 116.0, bars: int = 10, bass: float = 0.5,
                         gains: list[float] | None = None, sr: int = SR) -> tuple[np.ndarray, int, list[float]]:
    """Four-on-the-floor, closed hats on 8ths, one bass note held for the whole bar (gain ``bass``); ``gains`` scales
    every part of bar b (a quiet intro, a fade-out)."""
    beat = 60.0 / bpm
    x = np.zeros((2, int((0.5 + bars * 4 * beat + 1.5) * sr)))
    ref = []
    shot = kick_shot(kind, sr)
    hat = _faded(sd.hihat(0.6, False, sr, seed=4), sr) * 0.3
    roots = [31, 36, 33, 29]
    for b in range(bars):
        g = gains[b] if gains is not None else 1.0
        t0 = 0.5 + b * 4 * beat
        for s in range(4):
            i = int(round((t0 + s * beat) * sr))
            sd.place(x, sd.pan(shot * g, 0.0), i)
            ref.append(i / sr)
        for q in range(8):
            sd.place(x, sd.pan(hat * g, 0.3), int(round((t0 + q * beat / 2) * sr)))
        if bass:
            sd.place(x, sd.pan(sd.bass_note(roots[b % 4], 4 * beat * 0.95, 0.8, sr) * bass * g, 0.0), int(round(t0 * sr)))
    return _finish(x), sr, ref


def kicks_over_ducked_sub(kind: str, *, bpm: float = 126.0, bars: int = 10, bass: float = 0.8, depth: float = 0.92,
                          release_s: float = 0.15, sr: int = SR) -> tuple[np.ndarray, int, list[float]]:
    """EDM drop: a continuous sub bass (sine + 2 partials) sidechain-ducked at every kick (2 ms down, ``release_s``
    exponential recovery), so the low band hardly rises at the kick; hats on the off-beats."""
    beat = 60.0 / bpm
    n = int((0.5 + bars * 4 * beat + 1.0) * sr)
    t = np.arange(n) / sr
    f0 = np.full(n, 440 * 2 ** ((31 - 69) / 12))
    for b in range(bars):
        f0[int((0.5 + b * 4 * beat) * sr):] = 440 * 2 ** (([31, 31, 34, 29][b % 4] - 69) / 12)
    ph = 2 * np.pi * np.cumsum(f0) / sr
    sub = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
    g = np.ones(n)
    x = np.zeros((2, n))
    ref = []
    shot = kick_shot(kind, sr)
    hat = _faded(sd.hihat(0.6, False, sr, seed=4), sr) * 0.3
    for k in range(bars * 4):
        tk = 0.5 + k * beat
        i = int(round(tk * sr))
        ref.append(i / sr)
        sd.place(x, sd.pan(shot, 0.0), i)
        sd.place(x, sd.pan(hat, 0.3), int(round((tk + beat / 2) * sr)))
        m = (t >= tk - 0.002) & (t < tk + beat)
        env = 1 - depth * np.clip((t - tk + 0.002) / 0.002, 0, 1) * np.exp(-np.maximum(t - tk - 0.01, 0) / release_s)
        g = np.where(m, np.minimum(g, env), g)
    x += bass * 0.5 * sub * g
    return _finish(x), sr, ref


def fixture_roll(bpm: float = 180.0, *, crash: bool = True, sr: int = SR) -> tuple[np.ndarray, int, list[float]]:
    """The contract song's (long) kick on 16ths for 6 bars, under a crash every 2 s (review m21)."""
    step = 60.0 / bpm / 4
    ref = [0.5 + i * step for i in range(96)]
    x = np.zeros((2, int((ref[-1] + 1.5) * sr)))
    shot = kick_shot("fixture", sr)
    for t in ref:
        sd.place(x, sd.pan(shot, 0.0), int(round(t * sr)))
    if crash:
        t = 0.3
        while t < x.shape[1] / sr - 1.0:
            sd.place(x, sd.pan(sd.crash(1.0, 2.5, sr) * 0.5, 0.0), int(t * sr))
            t += 2.0
    return _finish(x), sr, ref


def kick_at_start(sr: int = SR) -> tuple[np.ndarray, int, list[float]]:
    """Kicks at 0, 1, 2 and 3 s: the first one on the file's first sample (review m20)."""
    x = np.zeros((2, int(4.0 * sr)))
    ref = []
    for k in range(4):
        sd.place(x, sd.pan(kick_shot("fixture", sr), 0.0), k * sr)
        ref.append(float(k))
    return _finish(x), sr, ref
