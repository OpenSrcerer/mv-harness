# ruff: noqa: E501
"""Tracker runners and DSP features for the rhythm stage (arrays in, explicit local model paths).

* beat_this final0 (``Audio2Frames``): beat / downbeat logits at 50 fps from a mono float32 array.
* madmom-infer ``RNNDownBeatProcessor`` on a 44.1 kHz mono float32 array (weights via XDG_CACHE_HOME, set by the
  runner and verified by ``ctx.model('madmom_downbeats_blstm')``), and ``DBNDownBeatTrackingProcessor``.
* DSP: librosa mel onset strength at 100 fps, a low-band (kick) flux, a short-window RMS level and the PLP pulse.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .fusion import FPS, resample_to, sigmoid


def to_sr(x: np.ndarray, sr: int, target: int) -> np.ndarray:
    x = np.asarray(x, np.float32).reshape(-1)
    if sr == target:
        return x
    import soxr
    return soxr.resample(x, sr, target).astype(np.float32)


# ------------------------------------------------------------------------------------------- beat_this
def beat_this_logits(mono: np.ndarray, sr: int, ckpt: str) -> tuple[np.ndarray, np.ndarray]:
    from beat_this.inference import Audio2Frames

    a2f = Audio2Frames(checkpoint_path=str(ckpt), device="cpu")
    bl, dl = a2f(np.asarray(mono, np.float32), int(sr))
    return (bl.detach().cpu().numpy().astype(np.float32).reshape(-1),
            dl.detach().cpu().numpy().astype(np.float32).reshape(-1))


def beat_this_post(bl: np.ndarray, dl: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """beat_this's own minimal postprocessor (peak picking on the logits)."""
    import torch
    from beat_this.model.postprocessor import Postprocessor

    beats, downbeats = Postprocessor(type="minimal")(torch.from_numpy(np.asarray(bl, np.float32)),
                                                     torch.from_numpy(np.asarray(dl, np.float32)))
    return np.asarray(beats, float), np.asarray(downbeats, float)


# ------------------------------------------------------------------------------------------- madmom
def madmom_activations(mono44k: np.ndarray) -> np.ndarray:
    from madmom_infer.features.downbeats import RNNDownBeatProcessor

    return np.asarray(RNNDownBeatProcessor()(np.asarray(mono44k, np.float32)), np.float32)


def madmom_dbn(act: np.ndarray, beats_per_bar=(3, 4), min_bpm: float = 55.0, max_bpm: float = 215.0) -> np.ndarray:
    """[[t, beat_in_bar], ...] from madmom's joint beat/downbeat DBN."""
    from madmom_infer.features.downbeats import DBNDownBeatTrackingProcessor

    proc = DBNDownBeatTrackingProcessor(beats_per_bar=list(beats_per_bar), min_bpm=float(min_bpm),
                                        max_bpm=float(max_bpm), fps=FPS)
    out = np.asarray(proc(np.asarray(act, np.float32)))
    return out.reshape(-1, 2) if out.size else np.zeros((0, 2))


# ------------------------------------------------------------------------------------------- DSP
def dsp_features(mono44k: np.ndarray, n: int, sr: int = 44100) -> dict[str, Any]:
    """onset (mel flux), kick (30-150 Hz flux), level_db (23 ms RMS), plp at 100 fps, length n."""
    import librosa

    y = np.asarray(mono44k, np.float32)
    hop = int(round(sr / FPS))
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, n_fft=2048)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop, center=True))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    lo = (freqs >= 30) & (freqs <= 150)
    lb = np.log1p(100.0 * S[lo].sum(axis=0))
    kick = np.maximum(0.0, np.diff(lb, prepend=lb[0]))
    mid = (freqs > 150) & (freqs <= 4000)
    mb = np.log1p(100.0 * S[mid].sum(axis=0))
    snare = np.maximum(0.0, np.diff(mb, prepend=mb[0]))
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop, center=True)[0]
    level_db = 20 * np.log10(np.maximum(rms, 1e-6))
    try:
        plp = librosa.beat.plp(onset_envelope=onset, sr=sr, hop_length=hop)
    except Exception:  # noqa: BLE001
        plp = np.zeros_like(onset)

    def fit(x):
        x = np.asarray(x, np.float64).reshape(-1)
        return x[:n] if len(x) >= n else np.concatenate([x, np.zeros(n - len(x))])

    return {"onset": fit(onset), "kick": fit(kick), "snare": fit(snare), "level_db": fit(level_db), "plp": fit(plp)}


def librosa_tempo(onset: np.ndarray, sr: int = 44100) -> float | None:
    import librosa

    try:
        t = librosa.feature.tempo(onset_envelope=np.asarray(onset, np.float32), sr=sr, hop_length=int(sr / FPS))
        return float(np.atleast_1d(t)[0])
    except Exception:  # noqa: BLE001
        return None


def beat_this_probs(bl: np.ndarray, dl: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    return resample_to(sigmoid(bl), 50.0, n), resample_to(sigmoid(dl), 50.0, n)
