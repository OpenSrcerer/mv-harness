# ruff: noqa: E501
"""Bar-synchronous features for the structure stage: timbre (MFCC), harmony (chroma), allin1 embeddings and label
probabilities, energy (RMS, bass, kick/onset density, brightness), plus self-similarity and Foote novelty.

All curves are at 100 Hz (frame i centred at i / 100 s); a bar [t, t + d) aggregates frames round(100 t) ..
round(100 (t + d)) - 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

FPS = 100.0


def bar_frames(bars: list[dict[str, Any]], n: int) -> list[tuple[int, int]]:
    out = []
    for b in bars:
        a = int(round(b["t"] * FPS))
        e = max(a + 1, int(round((b["t"] + b["d"]) * FPS)))
        out.append((min(max(a, 0), n - 1), min(max(e, 1), n)))
    return out


def pool(x: np.ndarray, spans: list[tuple[int, int]], how: str = "mean") -> np.ndarray:
    """x: [frames] or [frames, k] -> [bars] or [bars, k]."""
    x = np.asarray(x, np.float64)
    out = []
    for a, e in spans:
        seg = x[a:e] if e > a else x[a:a + 1]
        if how == "max":
            out.append(seg.max(axis=0))
        elif how == "median":
            out.append(np.median(seg, axis=0))
        else:
            out.append(seg.mean(axis=0))
    return np.asarray(out)


@dataclass
class BarFeatures:
    n: int
    t: np.ndarray                 # bar start times
    d: np.ndarray
    mfcc: np.ndarray              # [bars, 20]
    chroma: np.ndarray            # [bars, 12]
    emb: np.ndarray | None        # [bars, D]
    labels: np.ndarray | None     # [bars, L] allin1 label probs
    label_names: list[str]
    a1_boundary: np.ndarray       # [bars] max allin1 boundary activation within +-0.2 s of the bar start
    rms_db: np.ndarray
    bass_db: np.ndarray
    kick_rate: np.ndarray         # kick onsets per beat
    onset_rate: np.ndarray        # onsets per beat
    centroid: np.ndarray          # Hz
    silent: np.ndarray            # bool: bar is (near) silent
    extra: dict[str, Any] = field(default_factory=dict)


def audio_features(mono: np.ndarray, sr: int, n: int) -> dict[str, np.ndarray]:
    """Frame features at 100 Hz from the mix (mono float32)."""
    import librosa

    y = np.asarray(mono, np.float32)
    if sr != 44100:
        import soxr
        y = soxr.resample(y, sr, 44100).astype(np.float32)
        sr = 44100
    hop = 441
    M = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop, center=True))
    S = M ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    mel = librosa.feature.melspectrogram(S=S, sr=sr, n_mels=64)
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=20).T
    norm = 2048 * 2048 / 2
    rms = np.sqrt(np.maximum(S.sum(axis=0) / norm, 1e-14))
    lo = (freqs >= 30) & (freqs <= 150)
    bass = S[lo].sum(axis=0) / norm
    tot = S.sum(axis=0) + 1e-14
    centroid = (S * freqs[:, None]).sum(axis=0) / tot
    # percussive part (HPSS) so sustained bass notes do not read as kicks
    _, P = librosa.decompose.hpss(M, kernel_size=31)
    Pp = P ** 2
    lb = 10 * np.log10(np.maximum(Pp[lo].sum(axis=0) / norm, 1e-12))
    kick = np.maximum(0.0, lb - np.minimum.reduce([np.r_[np.full(j, lb[0]), lb[:-j]] for j in (1, 2, 3)]))
    pmel = librosa.feature.melspectrogram(S=Pp, sr=sr, n_mels=64)
    onset = librosa.onset.onset_strength(S=librosa.power_to_db(pmel), sr=sr, hop_length=hop)
    hf = (freqs >= 5000) & (freqs <= 16000)
    hb = 10 * np.log10(np.maximum(Pp[hf].sum(axis=0) / norm, 1e-12))
    hat = np.maximum(0.0, hb - np.minimum.reduce([np.r_[np.full(j, hb[0]), hb[:-j]] for j in (1, 2)]))

    def fit(a):
        a = np.asarray(a)
        if a.shape[0] >= n:
            return a[:n]
        pad = np.repeat(a[-1:], n - a.shape[0], axis=0) if a.shape[0] else np.zeros((n,) + a.shape[1:])
        return np.concatenate([a, pad], axis=0)

    return {"mfcc": fit(mfcc), "rms_db": fit(10 * np.log10(np.maximum(rms ** 2, 1e-12))),
            "bass_db": fit(10 * np.log10(np.maximum(bass, 1e-12))), "centroid": fit(centroid),
            "kick": fit(kick), "onset": fit(onset), "hat": fit(hat), "y44": y}


def own_chroma(y44: np.ndarray, n: int) -> np.ndarray:
    import librosa

    c = librosa.feature.chroma_cqt(y=np.asarray(y44, np.float32), sr=44100, hop_length=441, n_chroma=12).T
    if c.shape[0] >= n:
        return c[:n]
    return np.concatenate([c, np.zeros((n - c.shape[0], 12))], axis=0)


def peak_rate(env: np.ndarray, spans: list[tuple[int, int]], beats_per_bar: np.ndarray, rel: float = 0.35,
              min_dist: int = 8) -> np.ndarray:
    """Onset peaks per beat in each bar (peaks above rel x the song's p99, >= min_dist frames apart)."""
    e = np.asarray(env, float)
    thr = rel * (np.percentile(e, 99) if e.size else 0.0)
    pk = np.zeros(len(e), bool)
    if len(e) > 2:
        cand = np.nonzero((e[1:-1] > e[:-2]) & (e[1:-1] >= e[2:]) & (e[1:-1] > thr))[0] + 1
        last = -10 ** 9
        keep: list[int] = []
        for i in cand:
            if i - last >= min_dist:
                keep.append(int(i))
                last = i
            elif e[i] > e[keep[-1]]:
                keep[-1] = int(i)
                last = i
        pk[keep] = True
    out = np.zeros(len(spans))
    for k, (a, b) in enumerate(spans):
        out[k] = pk[a:b].sum() / max(1, beats_per_bar[k])
    return out


def zscore(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    if x.ndim == 1:
        x = x[:, None]
    mu, sd = x.mean(axis=0), x.std(axis=0)
    return (x - mu) / np.where(sd < 1e-9, 1.0, sd)


def cosine_ssm(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    nrm = np.linalg.norm(x, axis=1, keepdims=True)
    y = x / np.where(nrm < 1e-12, 1.0, nrm)
    return y @ y.T


def foote(S: np.ndarray, k: int) -> np.ndarray:
    """Foote novelty at each bar boundary i (between bar i-1 and bar i) with a Gaussian-tapered checkerboard of
    half-size k bars; edges use the available part of the kernel."""
    n = S.shape[0]
    out = np.zeros(n)
    g = np.exp(-0.5 * ((np.arange(k) + 0.5) / (0.5 * k)) ** 2)
    for i in range(1, n):
        a0, b1 = max(0, i - k), min(n, i + k)
        wa = g[: i - a0][::-1]
        wb = g[: b1 - i]
        A = S[a0:i, a0:i]
        B = S[i:b1, i:b1]
        C = S[a0:i, i:b1]
        wA = np.outer(wa, wa)
        wB = np.outer(wb, wb)
        wC = np.outer(wa, wb)
        within = (np.sum(A * wA) + np.sum(B * wB)) / max(1e-9, wA.sum() + wB.sum())
        cross = np.sum(C * wC) / max(1e-9, wC.sum())
        out[i] = max(0.0, within - cross)
    return out


def norm01(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    hi = np.percentile(x, 98) if x.size else 0.0
    lo = np.min(x) if x.size else 0.0
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def melody_residual(chroma: np.ndarray, spans: list[tuple[int, int]], nsub: int = 4) -> np.ndarray:
    """Per-bar melodic fingerprint: the chroma of ``nsub`` sub-bar slices (each unit-normalised) minus the bar's mean
    slice. The static harmony (a pad or chord bed that holds through the bar) cancels; what stays is the movement
    inside the bar (melody, riffs, arpeggios), which repeats when the tune repeats whatever the arrangement
    (drums, bass, sound design) does. Sections without such movement get near-zero vectors and no repeat evidence."""
    rows = []
    d = chroma.shape[1]
    for a, e in spans:
        e = max(e, a + nsub)
        edges = np.linspace(a, e, nsub + 1).astype(int)
        sub = np.zeros((nsub, d))
        for q in range(nsub):
            seg = chroma[edges[q]:max(edges[q + 1], edges[q] + 1)]
            if len(seg):
                sub[q] = seg.mean(axis=0)
        sub = sub / (np.linalg.norm(sub, axis=1, keepdims=True) + 1e-9)
        rows.append((sub - sub.mean(axis=0, keepdims=True)).reshape(-1))
    return np.asarray(rows, float)


def bar_pattern(envs: list[np.ndarray], spans: list[tuple[int, int]], nslots: int = 16) -> np.ndarray:
    """Per-bar rhythm-pattern fingerprint: each envelope (kick, percussive onset strength, hat-band flux) max-pooled
    into ``nslots`` slots per bar (proportional, so a 3/4 bar is still one pattern), scaled by the song's p99 and
    concatenated. Two bars with the same drum/onset pattern give the same vector whatever the pitched material does,
    so a groove change (verse swing -> chorus ride + crash) is a boundary even when the harmony does not move."""
    rows = []
    scaled = [np.asarray(e, float) / max(1e-9, float(np.percentile(e, 99))) for e in envs]
    for a, e in spans:
        e = max(e, a + nslots)
        top = scaled[0].shape[0] - 1
        edges = np.linspace(a, e, nslots + 1).astype(int)
        parts = []
        for env in scaled:
            parts.append([float(env[min(edges[q], top):max(edges[q + 1], edges[q] + 1)].max()) for q in range(nslots)])
        rows.append(np.concatenate(parts))
    X = np.asarray(rows, float)
    return np.clip(X, 0, 2.0)
