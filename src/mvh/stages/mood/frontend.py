# ruff: noqa: E501  (long literals and docstrings)
"""numpy port of the Essentia TensorflowPredictMusiCNN front end (16 kHz, n_fft 512, hop 256, 96 Slaney mel bands,
log10(1 + 10000 x)), plus the patching used by the msd-musicnn (187 x 96) and discogs-effnet (128 x 96) models.
Ported from docs/research/prototypes/lyrics-meaning/mood_onnx.py."""
from __future__ import annotations

import numpy as np

SR = 16000
N_FFT = 512
HOP = 256
N_MELS = 96
MUSICNN_PATCH, MUSICNN_HOP = 187, 93      # 3.008 s patches every 1.488 s
EFFNET_PATCH, EFFNET_HOP = 128, 62        # 2.064 s patches every 0.992 s


def _hz_to_mel(f):
    f = np.asanyarray(f, float)
    lin = 1000 / (200 / 3)
    logstep = np.log(6.4) / 27
    return np.where(f >= 1000, lin + np.log(np.maximum(f, 1e-10) / 1000) / logstep, f / (200 / 3))


def _mel_to_hz(m):
    m = np.asanyarray(m, float)
    lin = 1000 / (200 / 3)
    logstep = np.log(6.4) / 27
    return np.where(m >= lin, 1000 * np.exp(logstep * (m - lin)), (200 / 3) * m)


def mel_filterbank(sr: int = SR, n_fft: int = N_FFT, n_mels: int = N_MELS, fmin: float = 0.0, fmax: float = 8000.0) -> np.ndarray:
    fft_f = np.linspace(0, sr / 2, n_fft // 2 + 1)
    mel_f = _mel_to_hz(np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2))
    fdiff = np.diff(mel_f)
    ramps = mel_f[:, None] - fft_f[None, :]
    w = np.zeros((n_mels, len(fft_f)))
    for i in range(n_mels):
        lo = -ramps[i] / fdiff[i]
        hi = ramps[i + 2] / fdiff[i + 1]
        w[i] = np.maximum(0, np.minimum(lo, hi))
    w *= (2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels]))[:, None]
    return w.astype(np.float32)


_FB: np.ndarray | None = None


def log_mel(y: np.ndarray) -> np.ndarray:
    """[frames, 96] float32. Frame j covers samples [256 j, 256 j + 512) (no centring, as Essentia's FrameCutter)."""
    global _FB
    if _FB is None:
        _FB = mel_filterbank()
    y = np.asarray(y, np.float32).reshape(-1)
    if len(y) < N_FFT:
        y = np.pad(y, (0, N_FFT - len(y)))
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)
    n = 1 + (len(y) - N_FFT) // HOP
    out = np.empty((n, N_MELS), np.float32)
    step = 2048
    for a in range(0, n, step):
        b = min(n, a + step)
        idx = np.arange(N_FFT)[None, :] + HOP * np.arange(a, b)[:, None]
        spec = np.abs(np.fft.rfft(y[idx] * win, axis=1)) ** 2
        out[a:b] = np.log10(1 + 10000 * (spec @ _FB.T)).astype(np.float32)
    return out


def patch_starts(n_frames: int, size: int, hop: int) -> list[int]:
    """Frame index of every patch: a regular grid, plus one patch aligned to the end when the tail is over half a hop.
    Inputs shorter than one patch give a single zero-padded patch."""
    if n_frames <= size:
        return [0]
    starts = list(range(0, n_frames - size + 1, hop))
    if n_frames - (starts[-1] + size) > hop // 2:
        starts.append(n_frames - size)
    return starts


def make_patches(x: np.ndarray, size: int, hop: int) -> tuple[np.ndarray, list[int]]:
    if x.shape[0] < size:
        x = np.pad(x, ((0, size - x.shape[0]), (0, 0)))
    starts = patch_starts(x.shape[0], size, hop)
    return np.stack([x[s:s + size] for s in starts]), starts


def patch_centres_s(starts: list[int], size: int) -> np.ndarray:
    """Centre time (s) of each patch's audio span."""
    span = ((size - 1) * HOP + N_FFT) / SR
    return np.array([s * HOP / SR + span / 2 for s in starts])
