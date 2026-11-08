# ruff: noqa: E501  (long formulas, tables and docstrings)
"""EBU R128 / ITU-R BS.1770-4 measurements (numpy/scipy + pyloudnorm's K-weighting filters; no I/O except ffmpeg).

* K-weighting: pyloudnorm's two-stage filter (high shelf + RLB high-pass, designed for the actual sample rate),
  channel weights 1.0 (L, R, C) and 1.41 (Ls, Rs); the LFE (index 3 of 6 channels) is excluded.
* Momentary (0.4 s) and short-term (3 s) loudness as **centred** windows at 100 Hz: the value at t covers
  [t - w/2, t + w/2) (zeros outside the signal, the window length is kept), floored at -70 LUFS. A spec (trailing)
  meter shows the same number at t + w/2 (``curve_offsets_s``).
* Integrated loudness: pyloudnorm (BS.1770-4: 400 ms blocks, 75 % overlap, -70 LUFS absolute and -10 LU relative gates).
* LRA: EBU Tech 3342 (3 s short-term blocks every 0.1 s, -70 LUFS absolute gate, -20 LU relative gate, P95 - P10).
* True peak: 4x (2x at 96 kHz) polyphase oversampling per channel (BS.1770-4 Annex 2), processed in chunks.
* ffmpeg ``ebur128=peak=true`` is run as an independent cross-check (integrated, LRA, true peak).
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

LUFS_FLOOR = -70.0
DB_FLOOR = -120.0
RATE = 100


def channel_weights(n_ch: int) -> list[float]:
    """BS.1770 weights: 1.0 for L, R, C; 1.41 for the surrounds; 0 for the LFE of a 5.1 layout."""
    if n_ch <= 3:
        return [1.0] * n_ch
    if n_ch == 6:  # L R C LFE Ls Rs
        return [1.0, 1.0, 1.0, 0.0, 1.41, 1.41]
    return [1.0, 1.0, 1.0] + [1.41] * (n_ch - 3)


def k_weight(x: np.ndarray, sr: int) -> np.ndarray:
    """K-weighted copy of a [ch, n] signal (float64)."""
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    out = np.empty(x.shape, dtype=np.float64)
    for c in range(x.shape[0]):
        y = np.asarray(x[c], dtype=np.float64)
        for f in meter._filters.values():
            y = f.apply_filter(y)
        out[c] = y
    return out


def weighted_power(xk: np.ndarray) -> np.ndarray:
    """z[n] = sum_c G_c * y_c[n]^2 of the K-weighted signal."""
    w = channel_weights(xk.shape[0])
    z = np.zeros(xk.shape[1])
    for c in range(xk.shape[0]):
        if w[c]:
            z += w[c] * xk[c] * xk[c]
    return z


def centres(n_samples: int, sr: int, rate: int = RATE) -> np.ndarray:
    nf = -(-n_samples * rate // sr)
    i = np.arange(nf, dtype=np.int64)
    return (i * sr * 2 + rate) // (2 * rate)


def centred_mean(z: np.ndarray, c: np.ndarray, win: int) -> np.ndarray:
    """Mean of z over [c - win/2, c + win/2) with zeros outside the signal (the divisor stays ``win``)."""
    cs = np.concatenate([[0.0], np.cumsum(z)])
    h = win // 2
    a = np.clip(c - h, 0, z.size)
    b = np.clip(c - h + win, 0, z.size)
    return (cs[b] - cs[a]) / win


def lufs(ms: np.ndarray, floor: float = LUFS_FLOOR) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        v = -0.691 + 10.0 * np.log10(ms)
    return np.maximum(np.nan_to_num(v, nan=floor, neginf=floor), floor)


def loudness_curves(z: np.ndarray, sr: int, n_samples: int) -> dict[str, np.ndarray]:
    c = centres(n_samples, sr)
    return {
        "momentary": lufs(centred_mean(z, c, int(round(0.4 * sr)))),
        "short_term": lufs(centred_mean(z, c, int(round(3.0 * sr)))),
    }


def integrated(x: np.ndarray, sr: int) -> float:
    """BS.1770-4 integrated loudness (pyloudnorm). -70 (floor) for a signal below the absolute gate."""
    import pyloudnorm as pyln

    data = np.asarray(x, dtype=np.float64).T
    if data.shape[0] < int(0.4 * sr):
        return LUFS_FLOOR
    if data.shape[1] == 6:
        data = data[:, [0, 1, 2, 4, 5]]  # pyloudnorm's weights are [1, 1, 1, 1.41, 1.41]; drop the LFE
    with np.errstate(divide="ignore"):
        v = float(pyln.Meter(sr).integrated_loudness(data))
    return v if math.isfinite(v) else LUFS_FLOOR


def short_term_blocks(z: np.ndarray, sr: int, hop_s: float = 0.1, win_s: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """(start times, LUFS) of the 3 s short-term blocks every 0.1 s (EBU Tech 3342), whole blocks only."""
    blk = int(round(win_s * sr))
    hop = int(round(hop_s * sr))
    if z.size < blk:
        return np.zeros(1), lufs(np.array([z.sum() / blk]))
    starts = np.arange(0, z.size - blk + 1, hop)
    cs = np.concatenate([[0.0], np.cumsum(z)])
    ms = (cs[starts + blk] - cs[starts]) / blk
    return starts / sr, lufs(ms, floor=-np.inf)


def loudness_range(z: np.ndarray, sr: int) -> dict[str, float]:
    """EBU Tech 3342 LRA: absolute gate -70 LUFS, relative gate -20 LU below the power mean, P95 - P10."""
    _, st = short_term_blocks(z, sr)
    st = st[st > -70.0]
    if st.size == 0:
        return {"lra_lu": 0.0, "lra_low_lufs": LUFS_FLOOR, "lra_high_lufs": LUFS_FLOOR, "lra_threshold_lufs": LUFS_FLOOR}
    rel = -0.691 + 10.0 * math.log10(float(np.mean(10.0 ** ((st + 0.691) / 10.0)))) - 20.0
    g = st[st > rel]
    if g.size == 0:
        g = st
    lo, hi = float(np.percentile(g, 10)), float(np.percentile(g, 95))
    return {"lra_lu": hi - lo, "lra_low_lufs": lo, "lra_high_lufs": hi, "lra_threshold_lufs": rel}


def true_peak(x: np.ndarray, sr: int, chunk: int = 1 << 18) -> float:
    """Linear true peak (max over channels) by polyphase oversampling (4x below 96 kHz, 2x below 192 kHz)."""
    from scipy import signal

    up = 4 if sr < 96000 else 2 if sr < 192000 else 1
    x = np.asarray(x, dtype=np.float64)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if up == 1 or x.size == 0:
        return peak
    pad = 64
    for c in range(x.shape[0]):
        y = x[c]
        n = y.size
        for a in range(0, n, chunk):
            lo, hi = max(0, a - pad), min(n, a + chunk + pad)
            u = signal.resample_poly(y[lo:hi], up, 1, window=("kaiser", 10.0))
            i0 = (a - lo) * up
            i1 = i0 + (min(n, a + chunk) - a) * up
            peak = max(peak, float(np.max(np.abs(u[i0:i1]))))
    return peak


def db(v: float, floor: float = DB_FLOOR) -> float:
    return max(floor, 20.0 * math.log10(v)) if v > 0 else floor


def level_curves(x: np.ndarray, sr: int, win: int) -> dict[str, np.ndarray]:
    """Centred ``win``-sample RMS (mean square over channels) and sample peak (max |x| over channels) in dBFS, and
    the crest factor (peak - RMS, 0 in silence)."""
    from scipy import ndimage

    x = np.asarray(x, dtype=np.float64)
    n = x.shape[1]
    c = centres(n, sr)
    z = (x * x).mean(axis=0)
    ms = centred_mean(z, c, win)
    with np.errstate(divide="ignore", invalid="ignore"):
        rms_db = np.maximum(np.nan_to_num(10.0 * np.log10(ms), nan=DB_FLOOR, neginf=DB_FLOOR), DB_FLOOR)
    a = np.abs(x).max(axis=0)
    # max over [c - win//2, c - win//2 + win) (scipy's origin-0 window for this size)
    mx = ndimage.maximum_filter1d(a, size=win, mode="constant", cval=0.0) if n else a
    pk = mx[np.clip(c, 0, max(0, n - 1))] if n else np.zeros(c.size)
    with np.errstate(divide="ignore"):
        peak_db = np.maximum(np.nan_to_num(20.0 * np.log10(pk), neginf=DB_FLOOR), DB_FLOOR)
    live = rms_db > DB_FLOOR + 1e-6
    crest = np.where(live, np.clip(peak_db - rms_db, 0.0, 60.0), 0.0)
    return {"rms_db": rms_db, "peak_db": peak_db, "crest_db": crest}


def clipped_samples(x: np.ndarray, level: float = 1.0 - 2.0**-15) -> int:
    """Samples (all channels) whose magnitude reaches full scale (|x| >= 1 - 2^-15, i.e. the 16-bit maximum)."""
    return int(np.count_nonzero(np.abs(np.asarray(x)) >= level))


# ------------------------------------------------------------------------------------------------ ffmpeg ebur128
_RX = {
    "integrated_lufs": re.compile(r"Integrated loudness:\s*\n\s*I:\s*(-?[\d.]+|-inf)\s*LUFS"),
    "lra_lu": re.compile(r"Loudness range:\s*\n\s*LRA:\s*(-?[\d.]+)\s*LU"),
    "true_peak_dbtp": re.compile(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS"),
}


def parse_ebur128(text: str) -> dict[str, float]:
    i = text.rfind("Summary:")
    s = text[i:] if i >= 0 else text
    out: dict[str, float] = {}
    for k, rx in _RX.items():
        m = rx.search(s)
        if m:
            v = m.group(1)
            out[k] = -math.inf if v == "-inf" else float(v)
    return out


def ffmpeg_ebur128(path: Path, timeout: float | None = 900.0) -> dict[str, float]:
    """Run ffmpeg's ebur128 filter (true peak on) on a file and parse its summary (values have 0.1 resolution)."""
    from mvh.io.ffmpeg import run_ffmpeg

    r = run_ffmpeg(
        ["-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
        timeout=timeout,
        loglevel="info",
    )
    err = r.stderr.decode("utf-8", errors="replace") if isinstance(r.stderr, bytes) else str(r.stderr)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg ebur128 failed (exit {r.returncode})")
    out = parse_ebur128(err)
    if "integrated_lufs" not in out:
        raise RuntimeError("ffmpeg ebur128: no summary in the output")
    return out


def summary_stats(st: np.ndarray, mom: np.ndarray, t: np.ndarray, integrated_lufs: float) -> dict[str, Any]:
    """Readable loud/quiet facts: short-term percentiles, the loudest and quietest (non-silent) moments."""
    live = st > LUFS_FLOOR + 1e-6
    pool = st[live] if live.any() else st
    out: dict[str, Any] = {
        "short_term_percentiles": {f"p{p}": round(float(np.percentile(pool, p)), 2) for p in (10, 50, 90, 95)},
    }
    if st.size:
        i = int(np.argmax(st))
        out["loudest"] = {"t": round(float(t[i]), 2), "short_term_lufs": round(float(st[i]), 2),
                          "rel_lu": round(float(st[i] - integrated_lufs), 2)}
        j = int(np.argmax(mom))
        out["momentary_max"] = {"t": round(float(t[j]), 2), "lufs": round(float(mom[j]), 2)}
        # quietest non-silent stretch: the lowest short-term value whose whole 3 s window has sound (momentary above
        # integrated - 40 LU everywhere in it), so lead-in silence and fade-outs to nothing do not count
        from scipy import ndimage

        sounding = mom > integrated_lufs - 40.0
        full = ndimage.minimum_filter1d(sounding.astype(np.int8), size=int(3.0 * RATE) + 1, mode="constant", cval=0) > 0
        cand = live & full
        if cand.any():
            k = int(np.flatnonzero(cand)[np.argmin(st[cand])])
            out["quietest"] = {"t": round(float(t[k]), 2), "short_term_lufs": round(float(st[k]), 2),
                               "rel_lu": round(float(st[k] - integrated_lufs), 2)}
    return out
