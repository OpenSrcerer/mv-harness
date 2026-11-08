# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Deterministic signal generators (numpy + scipy.signal only). Every random source takes an explicit seed.

All generators return float64 mono arrays at ``sr`` unless stated. One-shots start at sample 0 (the event time
is the one-shot's first sample: the ground-truth onset of PLAN §7.2 "event time = the one-shot's sample onset").
"""

from __future__ import annotations

import numpy as np
from scipy import signal

__all__ = [
    "midi_hz",
    "hz_midi",
    "note_name",
    "env_adsr",
    "exp_decay",
    "rng",
    "additive",
    "kick",
    "snare",
    "tom",
    "hihat",
    "ride",
    "crash",
    "bass_note",
    "pad_note",
    "piano_note",
    "riser",
    "pan",
    "place",
    "db_to_lin",
]

SR = 44100
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_hz(m: float | np.ndarray) -> float | np.ndarray:
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=np.float64) - 69.0) / 12.0)


def hz_midi(f: float | np.ndarray) -> float | np.ndarray:
    return 69.0 + 12.0 * np.log2(np.asarray(f, dtype=np.float64) / 440.0)


def note_name(m: int) -> str:
    """C4 = 60, sharps as '#'."""
    return f"{NOTE_NAMES[int(m) % 12]}{int(m) // 12 - 1}"


def db_to_lin(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def exp_decay(n: int, tau_s: float, sr: int = SR) -> np.ndarray:
    return np.exp(-np.arange(n) / (tau_s * sr))


def env_adsr(n_on: int, a: float, d: float, s: float, r: float, sr: int = SR) -> np.ndarray:
    """ADSR envelope for a note held n_on samples, plus the release tail (length n_on + r*sr)."""
    na, nd, nr = max(1, int(a * sr)), max(1, int(d * sr)), max(1, int(r * sr))
    e = np.empty(n_on + nr)
    t = np.arange(n_on)
    held = np.where(t < na, t / na, s + (1 - s) * np.exp(-(t - na) / nd))
    e[:n_on] = held
    last = held[-1] if n_on else 0.0
    e[n_on:] = last * (1 - np.arange(nr) / nr) ** 2
    return e


def additive(
    f0: np.ndarray | float,
    n: int,
    amps,
    sr: int = SR,
    phase0: float = 0.0,
    inharm: float = 0.0,
    partial_env=None,
) -> np.ndarray:
    """Band-limited additive tone. f0: Hz (scalar or per-sample array); amps: list of harmonic amplitudes (k=1..).
    partial_env(k) -> per-sample envelope array for harmonic k (optional)."""
    f = np.broadcast_to(np.asarray(f0, dtype=np.float64), (n,))
    ph = 2 * np.pi * np.cumsum(f) / sr + phase0
    out = np.zeros(n)
    fmax = float(np.max(f)) if n else 0.0
    for k, a in enumerate(amps, start=1):
        if a == 0:
            continue
        mult = k * np.sqrt(1.0 + inharm * k * k)
        if mult * fmax >= 0.45 * sr:
            break
        comp = a * np.sin(mult * ph)
        if partial_env is not None:
            comp = comp * partial_env(k)
        out += comp
    return out


def _sos(kind: str, f, order: int = 4, sr: int = SR):
    return signal.butter(order, f, btype=kind, fs=sr, output="sos")


def _noise(n: int, seed: int) -> np.ndarray:
    return rng(seed).standard_normal(n)


# ------------------------------------------------------------------------------------------------ drums
def kick(vel: float = 1.0, sr: int = SR, seed: int = 1) -> np.ndarray:
    n = int(0.45 * sr)
    t = np.arange(n) / sr
    f = 48.0 + 110.0 * np.exp(-t / 0.03)
    body = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.20)
    click = signal.sosfilt(_sos("highpass", 1500), _noise(n, seed)) * np.exp(-t / 0.003) * 0.35
    x = body + click
    return vel * 0.95 * x / np.max(np.abs(x))


def snare(vel: float = 1.0, sr: int = SR, seed: int = 2) -> np.ndarray:
    n = int(0.35 * sr)
    t = np.arange(n) / sr
    tone = (np.sin(2 * np.pi * 185 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)) * np.exp(-t / 0.06)
    nz = signal.sosfilt(_sos("bandpass", [1200, 9000], 2), _noise(n, seed)) * np.exp(-t / 0.11)
    x = 0.55 * tone + 1.4 * nz
    return vel * 0.9 * x / np.max(np.abs(x))


def tom(pitch_hz: float, vel: float = 1.0, sr: int = SR, seed: int = 3) -> np.ndarray:
    n = int(0.6 * sr)
    t = np.arange(n) / sr
    f = pitch_hz * (1 + 0.45 * np.exp(-t / 0.04))
    x = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.22)
    x += 0.15 * signal.sosfilt(_sos("bandpass", [300, 3000], 2), _noise(n, seed)) * np.exp(-t / 0.02)
    return vel * 0.9 * x / np.max(np.abs(x))


def hihat(vel: float = 1.0, open_: bool = False, sr: int = SR, seed: int = 4) -> np.ndarray:
    n = int((0.45 if open_ else 0.12) * sr)
    t = np.arange(n) / sr
    x = signal.sosfilt(_sos("highpass", 7000), _noise(n, seed)) * np.exp(-t / (0.22 if open_ else 0.03))
    return vel * 0.8 * x / np.max(np.abs(x))


def _metal(n: int, freqs, sr: int) -> np.ndarray:
    t = np.arange(n) / sr
    return sum(np.sign(np.sin(2 * np.pi * f * t + i)) for i, f in enumerate(freqs)) / len(freqs)


def ride(vel: float = 1.0, sr: int = SR, seed: int = 5) -> np.ndarray:
    n = int(1.2 * sr)
    t = np.arange(n) / sr
    m = _metal(n, [3150, 3720, 4610, 5280, 6170, 7230], sr)
    x = signal.sosfilt(_sos("highpass", 2500), m) * np.exp(-t / 0.5) * 0.6
    x += signal.sosfilt(_sos("highpass", 5000), _noise(n, seed)) * np.exp(-t / 0.08) * 0.5
    return vel * 0.7 * x / np.max(np.abs(x))


def crash(vel: float = 1.0, length_s: float = 2.5, sr: int = SR, seed: int = 6) -> np.ndarray:
    n = int(length_s * sr)
    t = np.arange(n) / sr
    x = signal.sosfilt(_sos("highpass", 3000), _noise(n, seed)) * np.exp(-t / (length_s / 3.2))
    x += (
        0.4
        * signal.sosfilt(_sos("highpass", 2000), _metal(n, [2750, 3390, 4420, 5810], sr))
        * np.exp(-t / (length_s / 4))
    )
    x[: int(0.002 * sr)] *= np.linspace(0, 1, int(0.002 * sr), endpoint=False)
    return vel * 0.85 * x / np.max(np.abs(x))


# ------------------------------------------------------------------------------------------------ pitched voices
def bass_note(midi: int, dur_s: float, vel: float = 1.0, sr: int = SR) -> np.ndarray:
    """Synth bass: saw-ish additive (rolled off) + sub sine; returns note + 60 ms release."""
    n_on = int(round(dur_s * sr))
    env = env_adsr(n_on, 0.004, 0.12, 0.65, 0.06, sr)
    n = env.size
    f0 = float(midi_hz(midi))
    amps = [1.0 / k * np.exp(-k * f0 / 900.0) for k in range(1, 40)]
    x = additive(f0, n, amps, sr) + 0.6 * np.sin(2 * np.pi * f0 * np.arange(n) / sr)
    return vel * 0.5 * x * env


def pad_note(
    midi: int, dur_s: float, vel: float = 1.0, sr: int = SR, detune_cents: float = 7.0
) -> np.ndarray:
    """Stereo pad [2, n]: two detuned band-limited saws per side, slow attack, 0.6 s release."""
    n_on = int(round(dur_s * sr))
    env = env_adsr(n_on, 0.18, 0.5, 0.8, 0.6, sr)
    n = env.size
    f0 = float(midi_hz(midi))
    amps = [1.0 / k * np.exp(-k * f0 / 2200.0) for k in range(1, 60)]
    out = np.zeros((2, n))
    for side, cents in ((0, -detune_cents), (1, detune_cents)):
        f = f0 * 2 ** (cents / 1200)
        out[side] = 0.5 * (
            additive(f, n, amps, sr, phase0=0.3 * side)
            + additive(f * 2 ** (3 / 1200), n, amps, sr, phase0=1.1)
        )
    return vel * 0.16 * out * env


def piano_note(midi: int, dur_s: float, vel: float = 1.0, sr: int = SR) -> np.ndarray:
    """Plucked/piano-like additive tone with per-partial decay; note-off damps over 0.12 s."""
    n_on = int(round(dur_s * sr))
    nr = int(0.12 * sr)
    n = n_on + nr
    t = np.arange(n) / sr
    f0 = float(midi_hz(midi))
    damp = np.ones(n)
    damp[n_on:] = np.linspace(1, 0, nr) ** 2
    att = np.minimum(1.0, t / 0.002)
    amps = [1.0 / k**1.3 for k in range(1, 24)]
    x = additive(f0, n, amps, sr, inharm=0.0004, partial_env=lambda k: np.exp(-t * (0.8 + 0.5 * k)))
    return vel * 0.35 * x * damp * att


def riser(dur_s: float, sr: int = SR, seed: int = 7, f_lo: float = 200.0, f_hi: float = 8000.0) -> np.ndarray:
    """Noise sweep (time-varying gaussian band in the STFT domain) + exponential sine sweep; rising amplitude."""
    n = int(round(dur_s * sr))
    nz = _noise(n + 4096, seed)
    nper = 2048
    f, tt, Z = signal.stft(nz, fs=sr, nperseg=nper, noverlap=nper * 3 // 4)
    pos = np.clip(tt / dur_s, 0, 1)
    fc = f_lo * (f_hi / f_lo) ** pos
    lf = np.log2(np.maximum(f, 1.0))[:, None]
    mask = np.exp(-0.5 * ((lf - np.log2(fc)[None, :]) / 0.35) ** 2)
    _, y = signal.istft(Z * mask, fs=sr, nperseg=nper, noverlap=nper * 3 // 4)
    y = np.asarray(y[:n], dtype=np.float64)
    if y.size < n:
        y = np.pad(y, (0, n - y.size))
    y /= np.max(np.abs(y)) + 1e-12
    t = np.arange(n) / sr
    fs_ = 100.0 * (10.0 ** (t / dur_s))
    sweep = np.sin(2 * np.pi * np.cumsum(fs_) / sr)
    amp = (t / dur_s) ** 1.5
    return (0.55 * y + 0.25 * sweep) * amp


def pan(x: np.ndarray, p: float) -> np.ndarray:
    """Constant-power pan of a mono signal; p in [-1 (left), 1 (right)] -> [2, n]."""
    a = (p + 1) * np.pi / 4
    return np.vstack([np.cos(a) * x, np.sin(a) * x])


def place(track: np.ndarray, x: np.ndarray, start: int) -> None:
    """Add x ([ch, n] or [n]) into track ([ch, N]) at sample index start (clipped at the end)."""
    if x.ndim == 1:
        x = np.vstack([x, x]) if track.shape[0] == 2 else x[None, :]
    if start >= track.shape[1]:
        return
    m = min(x.shape[1], track.shape[1] - start)
    track[:, start : start + m] += x[:, :m]
