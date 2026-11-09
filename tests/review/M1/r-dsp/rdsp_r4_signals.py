"""Signals for the R-DSP round-4 review of M1 hits.kick (W3).

Every kick rule of select_kick_events was tuned on ONE synthetic kick (tests/synth/dsp.kick: a 158 -> 48 Hz sweep with a
3 ms click). These are other common kick designs (acoustic, TR-808, TR-909, ...) and two mix situations the tuned cases
do not cover: a sidechain-ducked sub bass (EDM drops) and a quiet section. Truth = the one-shots' first samples.
"""
from __future__ import annotations

import numpy as np
from scipy import signal as ss

SR = 44100


def _norm(z):
    return 0.9 * z / np.max(np.abs(z))


def _fade(z, sr, fade=0.05):
    k = min(z.size, int(fade * sr))
    z = z.copy()
    z[z.size - k:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k))
    return z


def make(kind: str, sr: int = SR, vel: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(3)
    if kind == "fixture":
        from tests.synth import dsp
        from tests.synth.m1.signals import _faded
        return _faded(dsp.kick(0.95, sr), sr) * vel
    if kind == "tr808":  # bridged-T: ~50 Hz, small pitch drop, long decay, no click
        n = int(0.9 * sr)
        t = np.arange(n) / sr
        f = 50 + 30 * np.exp(-t / 0.02)
        z = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.35)
    elif kind == "tr909":  # fast big sweep + click
        n = int(0.5 * sr)
        t = np.arange(n) / sr
        f = 50 + 150 * np.exp(-t / 0.012)
        z = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.2)
        hp = ss.butter(4, 2000, "highpass", fs=sr, output="sos")
        z += 0.3 * ss.sosfilt(hp, rng.standard_normal(n)) * np.exp(-t / 0.003)
    elif kind == "acoustic":  # 60 Hz body, little sweep, beater click, shell resonance
        n = int(0.5 * sr)
        t = np.arange(n) / sr
        f = 60 + 12 * np.exp(-t / 0.03)
        z = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.12)
        z += 0.35 * np.sin(2 * np.pi * 115 * t) * np.exp(-t / 0.05)
        bp = ss.butter(2, [1500, 6000], "bandpass", fs=sr, output="sos")
        z += 0.5 * ss.sosfilt(bp, rng.standard_normal(n)) * np.exp(-t / 0.004)
    elif kind == "subthump":  # 55 Hz sine, no sweep, no click
        n = int(0.6 * sr)
        t = np.arange(n) / sr
        z = np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.12) * np.minimum(1, t / 0.002)
    elif kind == "distorted":
        from tests.synth import dsp
        z = np.tanh(4 * dsp.kick(0.95, sr))
    elif kind == "trap808":  # long sustained 808 (a kick that is also the bass)
        n = int(1.2 * sr)
        t = np.arange(n) / sr
        f = 45 + 45 * np.exp(-t / 0.03)
        z = np.tanh(1.5 * np.sin(2 * np.pi * np.cumsum(f) / sr)) * np.exp(-t / 0.8)
    elif kind == "lowtuned":  # sweep that stays below ~110 Hz (dubstep / hip-hop kick)
        n = int(0.5 * sr)
        t = np.arange(n) / sr
        f = 42 + 60 * np.exp(-t / 0.025)
        z = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.25)
        hp = ss.butter(4, 1500, "highpass", fs=sr, output="sos")
        z += 0.2 * ss.sosfilt(hp, rng.standard_normal(n)) * np.exp(-t / 0.003)
    else:
        raise KeyError(kind)
    return _norm(_fade(z, sr)) * vel


def song(kind: str, bpm=120.0, bars=12, hats=True, bass=0.0, sr=SR, kick_gain=0.9, gains=None):
    from tests.synth import dsp
    from tests.synth.m1.signals import _faded
    beat = 60 / bpm
    dur = 0.5 + bars * 4 * beat + 1.5
    x = np.zeros((2, int(dur * sr)))
    ref = []
    roots = [33, 29, 36, 31]
    for b in range(bars):
        t0 = 0.5 + b * 4 * beat
        g = kick_gain * (gains[b] if gains is not None else 1.0)
        for s in range(4):
            i = int(round((t0 + s * beat) * sr))
            dsp.place(x, dsp.pan(make(kind, sr) * g, 0.0), i)
            ref.append(i / sr)
        if hats:
            for q in range(8):
                dsp.place(x, dsp.pan(_faded(dsp.hihat(0.6, False, sr, seed=4), sr) * 0.3 * (gains[b] if gains is not None else 1.0), 0.3),
                          int(round((t0 + q * beat / 2) * sr)))
        if bass:
            dsp.place(x, dsp.pan(dsp.bass_note(roots[b % 4], 4 * beat * 0.95, 0.8, sr) * bass * (gains[b] if gains is not None else 1.0), 0.0),
                      int(round(t0 * sr)))
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    x *= 10 ** (-1 / 20) / np.max(np.abs(x))
    return x, ref


def duck_song(kind="fixture", bpm=128.0, bars=12, bass_gain=0.7, depth=0.95, rel=0.18, kick_gain=0.9, sr=SR, hats=True):
    from tests.synth import dsp
    from tests.synth.m1.signals import _faded
    beat = 60 / bpm
    dur = 0.5 + bars * 4 * beat + 1.0
    n = int(dur * sr)
    x = np.zeros((2, n))
    ref = []
    t = np.arange(n) / sr
    # continuous sub bass (saw-ish, 3 partials), root changes every bar
    f0 = np.zeros(n)
    roots = [33, 33, 36, 31]
    for b in range(bars + 1):
        a = int((0.5 + b * 4 * beat) * sr)
        f0[max(0, a):] = 440 * 2 ** ((roots[b % 4] - 69) / 12)
    f0[: int(0.5 * sr)] = f0[int(0.5 * sr)]
    ph = 2 * np.pi * np.cumsum(f0) / sr
    bass = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
    g = np.ones(n)
    for b in range(bars):
        for s in range(4):
            tk = 0.5 + b * 4 * beat + s * beat
            i = int(round(tk * sr))
            ref.append(i / sr)
            dsp.place(x, dsp.pan(make(kind, sr) * kick_gain, 0.0), i)
            if hats:
                dsp.place(x, dsp.pan(_faded(dsp.hihat(0.6, False, sr, seed=4), sr) * 0.3, 0.3), int(round((tk + beat / 2) * sr)))
            m = t >= tk - 0.002
            env = 1 - depth * np.clip((t - tk + 0.002) / 0.002, 0, 1) * np.exp(-np.maximum(t - tk - 0.01, 0) / rel)
            g = np.where(m & (t < tk + beat), np.minimum(g, env), g)
    x += bass_gain * 0.5 * bass * g
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    x *= 10 ** (-1 / 20) / np.max(np.abs(x))
    return x, ref
