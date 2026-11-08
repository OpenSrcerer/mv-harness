# ruff: noqa: E501  (long docstrings and tables)
"""Fitting separator I/O to the song's timebase (main env).

Separators run at 44.1 kHz stereo. Stems must be sample-aligned with the mix, the same length and the same
channel count (CONTRACT §1). ``stereo44`` prepares the model input from ``ctx.audio('mix', sr=44100)``;
``to_mix`` brings a 44.1 kHz stereo stem back (ffmpeg/soxr resampling when the song is not 44.1 kHz, then
channels and length).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = ["is_mono", "side_to_mid_db", "stereo44", "fit_channels", "fit_length", "to_mix"]


def is_mono(x: np.ndarray, side_db: float = -30.0) -> bool:
    """True for a one-channel signal or a (near) dual-mono pair: side (L-R) energy at least ``side_db`` below the mid
    (L+R) energy (correlation > ~0.998)."""
    a = np.asarray(x)
    if a.ndim == 1 or a.shape[0] == 1:
        return True
    left, right = a[0].astype(np.float64), a[1].astype(np.float64)
    mid = float(np.sum((left + right) ** 2))
    side = float(np.sum((left - right) ** 2))
    if mid <= 0.0:
        return side <= 0.0
    return 10.0 * np.log10(max(side, 1e-30) / mid) <= side_db


def side_to_mid_db(x: np.ndarray) -> float:
    """Side (L-R) energy over mid (L+R) energy in dB: the stereo width the karaoke model's pan cue lives on. ``-inf`` for
    one channel or an exact dual mono; about -8 .. -15 dB for an ordinary stereo mix; <= -20 dB is a narrow master."""
    a = np.asarray(x)
    if a.ndim == 1 or a.shape[0] == 1:
        return float("-inf")
    left, right = a[0].astype(np.float64), a[1].astype(np.float64)
    mid = float(np.sum((left + right) ** 2))
    side = float(np.sum((left - right) ** 2))
    if mid <= 0.0:
        return float("-inf") if side <= 0.0 else float("inf")
    return 10.0 * float(np.log10(max(side, 1e-30) / mid))


def stereo44(x: np.ndarray) -> np.ndarray:
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    if a.shape[0] == 1:
        return np.repeat(a, 2, axis=0)
    if a.shape[0] > 2:
        # downmix L/R from the first two channels plus the rest equally (multichannel input is rare)
        rest = a[2:].mean(axis=0, dtype=np.float64) if a.shape[0] > 2 else 0.0
        return np.stack([a[0] + 0.5 * rest, a[1] + 0.5 * rest]).astype(np.float32)
    return a


def fit_channels(a: np.ndarray, channels: int) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    if a.shape[0] == channels:
        return a
    if channels == 1:
        return a.mean(axis=0, dtype=np.float64).astype(np.float32)[None, :]
    if a.shape[0] == 1:
        return np.repeat(a, channels, axis=0)
    out = np.zeros((channels, a.shape[1]), dtype=np.float32)
    out[: min(channels, a.shape[0])] = a[: min(channels, a.shape[0])]
    return out


def fit_length(a: np.ndarray, n: int) -> np.ndarray:
    if a.shape[1] == n:
        return a
    if a.shape[1] > n:
        return np.ascontiguousarray(a[:, :n])
    return np.pad(a, ((0, 0), (0, n - a.shape[1])))


def to_mix(stem: np.ndarray, sr_in: int, sr_mix: int, n_mix: int, channels: int, scratch: Path) -> np.ndarray:
    a = np.asarray(stem, dtype=np.float32)
    if int(sr_in) != int(sr_mix):
        from mvh.io import audio as aio
        from mvh.io.wav import write_wav

        scratch = Path(scratch)
        scratch.mkdir(parents=True, exist_ok=True)
        tmp = scratch / "resample.wav"
        write_wav(tmp, a, int(sr_in))
        a = aio.decode(tmp, sr=int(sr_mix)).samples
    return fit_length(fit_channels(a, channels), n_mix)
