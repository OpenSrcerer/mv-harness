"""Signals for the R-DSP round-5 review of M1 hits.kick (W3 verify after fixer-m1-r4).

fixer-m1-r4 added kick routes "click" (acoustic kick over a held bass), "duck" (sidechain-ducked bass) and "808". The
click and duck routes need a 1.5-5 kHz "click" >= 15 dB above the 50-10 ms before the onset. That only happens when
the click band is almost empty before the kick, as in the sparse synthetic mixes of the round-4 tests. These signals
add what a real mix has there (a quiet sustained lead chord) and kick-free textures with a click-band transient on a
low-band onset (a pluck bass with hats, low piano chords, a snare on a new bass note). Truth = one-shot first samples.
"""
from __future__ import annotations

import numpy as np
from rdsp_r4_signals import SR
from tests.synth import dsp
from tests.synth.m1.signals import _faded


def lead_bed(n: int, sr: int = SR, notes=(57, 60, 64, 69)) -> np.ndarray:
    """A sustained, slightly detuned saw chord (A3 C4 E4 A4, partials 1/k): a lead / pad that fills 1.5-5 kHz.
    Peak-normalised to 1."""
    out = np.zeros(n)
    for m in notes:
        f0 = dsp.midi_hz(m)
        for det in (-0.1, 0.1):
            out += dsp.additive(f0 * 2 ** (det / 12), n, [1.0 / k for k in range(1, 60)], sr, phase0=m * 0.37 + det)
    return out / np.max(np.abs(out))


def with_bed(x: np.ndarray, gain: float) -> np.ndarray:
    """Add the lead chord at ``gain`` (peak, linear; the kicks peak at 0.9) and renormalise to -1 dBFS."""
    y = x + gain * lead_bed(x.shape[1])[None, :]
    return y * (10 ** (-1 / 20) / np.max(np.abs(y)))


def _pluck_bass(midi: int, dur: float, sr: int = SR, f_hi: float = 1500.0, f_lo: float = 120.0, tau: float = 0.05):
    """Saw bass through a low-pass whose cutoff falls from f_hi to f_lo (tau): a pluck / acid bass. No kick."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    f0 = dsp.midi_hz(midi)
    fc = f_lo + (f_hi - f_lo) * np.exp(-t / tau)
    x = dsp.additive(f0, n, [1.0 / k for k in range(1, 60)], sr, partial_env=lambda k: 1.0 / np.sqrt(1 + (k * f0 / fc) ** 8))
    env = np.minimum(1, t / 0.003) * np.exp(-t / 0.4)
    k = min(n, int(0.02 * sr))
    env[n - k:] *= np.linspace(1, 0, k)
    return 0.5 * x * env


def kick_free(kind: str, bpm: float = 124.0, bars: int = 12, sr: int = SR) -> np.ndarray:
    """Kick-free textures (truth: no kick):
    * "pluck_hats": a pluck bass on every 8th with a closed hat on each note (house / disco);
    * "piano_low": low piano chords on every beat, the left hand an octave above the bass root (A2 ... );
    * "snare_bass": a snare on 2 and 4, each starting a new held bass note."""
    beat = 60 / bpm
    x = np.zeros((2, int((0.5 + bars * 4 * beat + 1.5) * sr)))
    roots = [33, 36, 31, 29]
    hat = _faded(dsp.hihat(0.6, False, sr, seed=4), sr) * 0.3
    for b in range(bars):
        t0 = 0.5 + b * 4 * beat
        r = roots[b % 4]
        if kind == "pluck_hats":
            for q in range(8):
                i = int(round((t0 + q * beat / 2) * sr))
                dsp.place(x, dsp.pan(_pluck_bass(r, beat / 2, sr) * 0.9, 0.0), i)
                dsp.place(x, dsp.pan(hat, 0.3), i)
        elif kind == "piano_low":
            for s in range(4):
                i = int(round((t0 + s * beat) * sr))
                for m in (r + 12, r + 24, r + 28, r + 31):
                    dsp.place(x, dsp.pan(dsp.piano_note(m, beat * 0.9, 0.9, sr), 0.0), i)
        elif kind == "snare_bass":
            for s in (1, 3):
                i = int(round((t0 + s * beat) * sr))
                dsp.place(x, dsp.pan(_faded(dsp.snare(0.9, sr), sr) * 0.8, 0.0), i)
                dsp.place(x, dsp.pan(dsp.bass_note(roots[(b * 2 + s) % 4], 2 * beat * 0.95, 0.8, sr) * 0.7, 0.0), i)
        else:
            raise KeyError(kind)
    x += 10 ** (-70 / 20) * np.random.default_rng(1).standard_normal(x.shape)
    return x * (10 ** (-1 / 20) / np.max(np.abs(x)))
