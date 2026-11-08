# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Reference measurements for the fixture's physical curves (numpy/scipy/pyloudnorm; deterministic).

These are *fixture-quality* measurements of the rendered audio, not the production algorithms: they give the
curves physically meaningful values (band powers, loudness, stereo, stem levels) so downstream builders get
realistic inputs. Their recipes are documented in every function and in provenance notes. Event-driven
curves (hit envelopes, drum envelopes, beat activations, accents) are built from the ground-truth events
with the contract's flash rule (conventions.flash_samples).

Conventions: 100 Hz frames, sample i centred at i/100 s (centre sample round(i * sr / 100)); dB channels floored
at -120 dBFS, LUFS at -70; "dBFS" is 10*log10(mean square) (a full-scale sine reads -3.01 dBFS).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import signal

from mvh.contract.conventions import flash_samples, n_curve_frames

__all__ = [
    "Frames",
    "frames_of",
    "stft_power",
    "band_db",
    "pnorm",
    "viz_bands",
    "flux",
    "timbre",
    "stereo",
    "loudness_curves",
    "integrated_and_lra",
    "true_peak_db",
    "rms_peak_db",
    "flash_envelope",
    "activity",
    "DB_FLOOR",
    "LUFS_FLOOR",
]

DB_FLOOR = -120.0
LUFS_FLOOR = -70.0
RATE = 100
WIN = 2048


class Frames:
    def __init__(self, n_samples: int, sr: int, rate: int = RATE):
        self.n_samples, self.sr, self.rate = n_samples, sr, rate
        self.n = n_curve_frames(n_samples, sr, rate)
        self.centres = np.round(np.arange(self.n) * sr / rate).astype(np.int64)
        self.t = np.arange(self.n) / rate


def frames_of(n_samples: int, sr: int) -> Frames:
    return Frames(n_samples, sr)


def _windows(x: np.ndarray, fr: Frames, win: int = WIN) -> np.ndarray:
    """[n_frames, win] centred windows of mono x (zero padded at the edges)."""
    pad = np.pad(x, (win // 2, win // 2))
    idx = fr.centres[:, None] + np.arange(win)[None, :]
    return pad[idx]


def stft_power(x: np.ndarray, fr: Frames, win: int = WIN) -> tuple[np.ndarray, np.ndarray]:
    """Per-bin mean-square power (Parseval-normalised, Hann window): sum over bins = mean square of the windowed frame."""
    w = np.hanning(win)
    X = np.fft.rfft(_windows(x, fr, win) * w, axis=1)
    P = np.abs(X) ** 2 / (win * np.sum(w * w))
    P[:, 1:-1] *= 2.0
    return P, np.fft.rfftfreq(win, 1.0 / fr.sr)


def _db(p: np.ndarray, floor: float = DB_FLOOR) -> np.ndarray:
    with np.errstate(divide="ignore"):
        d = 10.0 * np.log10(p)
    return np.maximum(np.nan_to_num(d, neginf=floor, nan=floor), floor)


def band_db(P: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    m = (freqs >= lo) & (freqs < hi)
    return _db(P[:, m].sum(axis=1))


def pnorm(v: np.ndarray, lo_p: float = 2.0, hi_p: float = 99.5) -> tuple[np.ndarray, float, float]:
    """Per-song p02-p99.5 normalisation to 0..1 (clipped); returns (values, lo, hi)."""
    lo, hi = float(np.percentile(v, lo_p)), float(np.percentile(v, hi_p))
    if hi - lo < 1e-9:
        return np.zeros_like(v), lo, hi
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0), lo, hi


def viz_edges() -> np.ndarray:
    return np.geomspace(32.0, 16000.0, 129)


def viz_bands(P: np.ndarray, freqs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Approximation of the viz/js/audio.js band map (NOT the exact port - the spectral module owns that):
    128 log bands 32 Hz-16 kHz, band dB + 2.6 dB/oct tilt (0 at 1 kHz), mapped -88..-18 dB -> 0..1 after a per-song
    gain that puts the p99 of all band values at -22 dB. Returns ([n, 128] in 0..1, edges)."""
    edges = viz_edges()
    bins = np.searchsorted(freqs, edges)
    cols = []
    for k in range(128):
        a, b = bins[k], max(bins[k + 1], bins[k] + 1)
        cols.append(P[:, a:b].mean(axis=1))
    B = _db(np.stack(cols, axis=1))
    fc = np.sqrt(edges[:-1] * edges[1:])
    B = B + 2.6 * np.log2(fc / 1000.0)[None, :]
    live = B[B > DB_FLOOR + 10]
    gain = -22.0 - float(np.percentile(live, 99)) if live.size else 0.0
    V = np.clip((B + gain + 88.0) / 70.0, 0.0, 1.0)
    return V, edges


def flux(P: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Half-wave rectified frame-to-frame increase of log power (dB/10) summed over the band's bins."""
    m = (freqs >= lo) & (freqs < hi)
    L = np.log10(P[:, m] + 1e-10)
    d = np.diff(L, axis=0, prepend=L[:1])
    return np.maximum(d, 0.0).sum(axis=1)


def timbre(P: np.ndarray, freqs: np.ndarray) -> dict[str, np.ndarray]:
    """centroid_hz, rolloff_hz (85 %), flatness (20 Hz-16 kHz), slope_db_oct (least squares of dB vs log2 f, 100 Hz-10 kHz).
    Silent frames (total power < 1e-12) read 0."""
    tot = P.sum(axis=1)
    live = tot > 1e-12
    cen = np.where(live, (P * freqs[None, :]).sum(axis=1) / np.maximum(tot, 1e-30), 0.0)
    c = np.cumsum(P, axis=1)
    roll_idx = np.argmax(c >= 0.85 * c[:, -1:], axis=1)
    roll = np.where(live, freqs[roll_idx], 0.0)
    m = (freqs >= 20) & (freqs < 16000)
    Pm = P[:, m] + 1e-20
    flat = np.where(live, np.exp(np.mean(np.log(Pm), axis=1)) / np.mean(Pm, axis=1), 0.0)
    ms = (freqs >= 100) & (freqs < 10000)
    xo = np.log2(freqs[ms])
    xo = xo - xo.mean()
    y = 10 * np.log10(P[:, ms] + 1e-20)
    slope = np.where(live, (y - y.mean(axis=1, keepdims=True)) @ xo / np.sum(xo * xo), 0.0)
    return {
        "centroid_hz": cen,
        "rolloff_hz": roll,
        "flatness": np.clip(flat, 0, 1),
        "slope_db_oct": np.clip(slope, -30, 10),
    }


def stereo(x2: np.ndarray, fr: Frames, win: int = WIN) -> dict[str, np.ndarray]:
    w = np.hanning(win) ** 2
    L = _windows(x2[0], fr, win)
    R = _windows(x2[1], fr, win)
    el, er = (L * L) @ w, (R * R) @ w
    lr = (L * R) @ w
    M, S = (L + R) / 2, (L - R) / 2
    em, es = (M * M) @ w, (S * S) @ w
    live = (el + er) > 1e-12
    width = np.where(live, es / np.maximum(em + es, 1e-30), 0.0)
    bal = np.where(live, (er - el) / np.maximum(er + el, 1e-30), 0.0)
    corr = np.where(live, lr / np.sqrt(np.maximum(el * er, 1e-30)), 0.0)
    return {
        "width": np.clip(width, 0, 1),
        "balance": np.clip(bal, -1, 1),
        "correlation": np.clip(corr, -1, 1),
    }


def _k_weight(x2: np.ndarray, sr: int) -> np.ndarray:
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    out = np.empty_like(x2)
    for c in range(x2.shape[0]):
        y = x2[c]
        for f in meter._filters.values():
            y = f.apply_filter(y)
        out[c] = y
    return out


def _windowed_ms(z: np.ndarray, centres: np.ndarray, half: int) -> np.ndarray:
    """Mean of z over [c - half, c + half) (zero outside the signal; the window length stays 2*half)."""
    cs = np.concatenate([[0.0], np.cumsum(z)])
    a = np.clip(centres - half, 0, z.size)
    b = np.clip(centres + half, 0, z.size)
    return (cs[b] - cs[a]) / (2 * half)


def loudness_curves(x2: np.ndarray, fr: Frames) -> dict[str, np.ndarray]:
    """BS.1770 K-weighted momentary (0.4 s) and short-term (3 s) loudness, centred windows, floored at -70 LUFS."""
    kw = _k_weight(x2, fr.sr)
    z = (kw**2).sum(axis=0)
    out = {}
    for name, dur in (("momentary_lufs", 0.4), ("short_term_lufs", 3.0)):
        ms = _windowed_ms(z, fr.centres, int(round(dur * fr.sr / 2)))
        with np.errstate(divide="ignore"):
            lu = -0.691 + 10 * np.log10(ms)
        out[name] = np.maximum(np.nan_to_num(lu, neginf=LUFS_FLOOR), LUFS_FLOOR)
    return out


def integrated_and_lra(x2: np.ndarray, sr: int) -> dict[str, float]:
    """Integrated loudness (pyloudnorm, BS.1770-4) and LRA (EBU Tech 3342: 3 s blocks at 10 Hz, abs gate -70,
    relative gate -20 LU, 10th-95th percentile)."""
    import pyloudnorm as pyln

    integ = float(pyln.Meter(sr).integrated_loudness(x2.T))
    kw = _k_weight(x2, sr)
    z = (kw**2).sum(axis=0)
    hop, blk = int(0.1 * sr), int(3.0 * sr)
    starts = np.arange(0, max(1, z.size - blk + 1), hop)
    cs = np.concatenate([[0.0], np.cumsum(z)])
    ms = (cs[starts + blk] - cs[starts]) / blk
    with np.errstate(divide="ignore"):
        st = -0.691 + 10 * np.log10(ms)
    st = st[st > -70.0]
    if st.size == 0:
        return {
            "integrated_lufs": integ,
            "lra_lu": 0.0,
            "lra_low_lufs": LUFS_FLOOR,
            "lra_high_lufs": LUFS_FLOOR,
        }
    rel = -0.691 + 10 * np.log10(np.mean(10 ** ((st + 0.691) / 10))) - 20.0
    st = st[st > rel]
    lo, hi = float(np.percentile(st, 10)), float(np.percentile(st, 95))
    return {"integrated_lufs": integ, "lra_lu": hi - lo, "lra_low_lufs": lo, "lra_high_lufs": hi}


def true_peak_db(x2: np.ndarray) -> float:
    up = signal.resample_poly(x2, 4, 1, axis=1)
    return float(20 * np.log10(max(np.max(np.abs(up)), 1e-12)))


def rms_peak_db(x2: np.ndarray, fr: Frames, win: int = WIN) -> tuple[np.ndarray, np.ndarray]:
    """46 ms (2048-sample) centred RMS (mean over channels) and sample peak, in dBFS (floored)."""
    z = (x2**2).mean(axis=0)
    ms = _windowed_ms(z, fr.centres, win // 2)
    rms = _db(ms)
    a = np.abs(x2).max(axis=0)
    pad = np.pad(a, (win // 2, win // 2))
    idx = fr.centres[:, None] + np.arange(0, win, 8)[None, :]  # strided peak search (8-sample stride)
    pk = pad[idx].max(axis=1)
    with np.errstate(divide="ignore"):
        pdb = np.maximum(np.nan_to_num(20 * np.log10(pk), neginf=DB_FLOOR), DB_FLOOR)
    return rms, pdb


def flash_envelope(n: int, events: list[tuple[float, float]], tau_s: float, rate: int = RATE) -> np.ndarray:
    """Event-driven max channel: each (t, value) holds `value` at floor(t*rate) and ceil(t*rate) (flash rule) and
    decays exponentially (time constant tau_s) after the event; overlapping events combine by max."""
    e = np.zeros(n)
    for t, v in events:
        a, b = flash_samples(t, rate)
        for i in (a, b):
            if 0 <= i < n:
                e[i] = max(e[i], v)
        j = np.arange(b + 1, min(n, b + 1 + int(6 * tau_s * rate) + 1))
        if j.size:
            e[j] = np.maximum(e[j], v * np.exp(-(j / rate - t) / tau_s))
    return e


def activity(
    rms_db: np.ndarray,
    rel_db: np.ndarray,
    active_db: float = -45.0,
    within_db: float = 18.0,
    attack_ms: float = 300.0,
    release_ms: float = 500.0,
    rate: int = RATE,
) -> np.ndarray:
    """stem_activity rule: active where rms > active_db and rel > -within_db; gaps shorter than release_ms are closed,
    then runs shorter than attack_ms are dropped (no onset delay)."""
    raw = (rms_db > active_db) & (rel_db > -within_db)
    a = raw.copy()
    gap = int(round(release_ms * rate / 1000))
    i, n = 0, a.size
    while i < n:
        if not a[i]:
            j = i
            while j < n and not a[j]:
                j += 1
            if 0 < i and j < n and j - i < gap:
                a[i:j] = True
            i = j
        else:
            i += 1
    run = int(round(attack_ms * rate / 1000))
    i = 0
    while i < n:
        if a[i]:
            j = i
            while j < n and a[j]:
                j += 1
            if j - i < run:
                a[i:j] = False
            i = j
        else:
            i += 1
    return a


def segments(mask: np.ndarray, rate: int = RATE) -> list[tuple[float, float]]:
    """[(t, d)] runs of True (frame i covers [i/rate - 0.5/rate, i/rate + 0.5/rate) clipped at 0)."""
    out = []
    n = mask.size
    i = 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            t0 = max(0.0, (i - 0.5) / rate)
            t1 = (j - 0.5) / rate
            out.append((round(t0, 6), round(t1 - t0, 6)))
            i = j
        else:
            i += 1
    return out


def env_follower(
    x: np.ndarray, sr: int, attack_s: float = 0.010, release_s: float = 0.060, step_ms: float = 1.0
) -> np.ndarray:
    """Peak follower on |x| at 1 kHz resolution; returns values per 1 ms step."""
    hop = int(round(sr * step_ms / 1000))
    n = int(math.ceil(x.size / hop))
    pk = np.abs(np.pad(x, (0, n * hop - x.size))).reshape(n, hop).max(axis=1)
    aa = math.exp(-step_ms / 1000 / attack_s)
    ar = math.exp(-step_ms / 1000 / release_s)
    out = np.empty(n)
    y = 0.0
    for i, v in enumerate(pk):
        c = aa if v > y else ar
        y = c * y + (1 - c) * v
        out[i] = y
    return out
