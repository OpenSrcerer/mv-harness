"""Dynamics segmentation (loud and quiet parts) and the intensity composite (pure numpy/scipy).

1. A 10 Hz feature matrix: short-term LU, bass and kick band dB, kick density, mid/high onset density, brightness
   (log2 centroid), spectral slope and stereo width, robust-standardised per song (median / IQR with a physical minimum
   scale, so a limited master's small LU moves still count once bass/kick change).
2. Foote novelty with Gaussian checkerboard kernels of +-4 s and +-8 s on that matrix.
3. Adaptive peak picking (prominence relative to the song's own novelty peaks, 3 s minimum distance), plus the hard
   boundaries of silences, stops and strong impacts; boundaries snap to downbeats.
4. When that finds too few parts (limited masters: the fixed-threshold prototype found 3 on Jeremy), candidate
   boundaries come from allin1 sections (when the stage can read them) or a 4-bar grid, kept where the feature contrast
   between the neighbouring blocks is high for this song.
5. Short parts are merged; adjacent parts of the same level whose features hardly differ are merged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from .detect import RATE, Inputs, density

DS = 10  # 100 Hz -> 10 Hz
LEVELS = ("silence", "quiet", "soft", "medium", "loud", "peak")


# ------------------------------------------------------------------------------------------------ features
@dataclass
class Features:
    names: list[str]
    raw: np.ndarray  # [m, k] 10 Hz physical values
    z: np.ndarray  # [m, k] standardised and weighted
    rate: int = RATE // DS


#: name -> (weight, minimum scale in physical units)
FEATURE_SPEC = {
    "st_lu": (1.5, 1.0),
    "bass_db": (1.0, 2.0),
    "kick_db": (0.75, 2.0),
    "kick_rate": (1.0, 0.5),
    "onset_rate": (0.75, 0.75),
    "bright_oct": (0.75, 0.15),
    "slope": (0.4, 0.6),
    "width": (0.4, 0.04),
}


def pool(v: np.ndarray, how: str = "mean") -> np.ndarray:
    m = v.size // DS
    if m == 0:
        return np.asarray([float(np.mean(v))]) if v.size else np.zeros(0)
    a = v[: m * DS].reshape(m, DS)
    if how == "power":
        return 10.0 * np.log10(np.mean(10.0 ** (a / 10.0), axis=1) + 1e-30)
    return a.mean(axis=1)


def series(inp: Inputs) -> dict[str, np.ndarray]:
    """The 100 Hz series behind the features (also used for the per-segment statistics)."""
    n = inp.n
    kr = density([k for k, _ in inp.kicks], [min(1.0, s) for _, s in inp.kicks], n, 2.0)
    orate = density(list(inp.onsets_mid) + list(inp.onsets_high), None, n, 2.0)
    from scipy import ndimage

    return {
        "mom_1s": ndimage.uniform_filter1d(inp.mom, size=101, mode="nearest"),
        "st_lu": inp.st - inp.integrated,
        "bass_db": inp.bass_db,
        "kick_db": inp.kick_db,
        "kick_rate": kr,
        "onset_rate": orate,
        "bright_oct": np.log2(np.maximum(inp.centroid_hz, 20.0)),
        "slope": inp.slope,
        "width": inp.width,
    }


def features(inp: Inputs, ser: dict[str, np.ndarray] | None = None,
             silences: Sequence[tuple[float, float]] = ()) -> Features:
    """10 Hz robust-standardised features (clipped at +-3 scale units before weighting). Frames inside detected
    silences hold the last sounding values: silences are hard boundaries already and would otherwise dominate the
    novelty of the whole song."""
    from scipy import ndimage

    ser = ser or series(inp)
    names = list(FEATURE_SPEC)
    cols = []
    for k in names:
        v = ser[k]
        cols.append(pool(v, "power") if k in ("bass_db", "kick_db") else pool(v))
    raw = np.stack(cols, axis=1)
    m = raw.shape[0]
    hole = np.zeros(m, bool)
    for a, b in silences:
        hole[max(0, int(a * 10)) : min(m, int(math.ceil(b * 10)))] = True
    if hole.any() and not hole.all():
        idx = np.where(~hole, np.arange(m), 0)
        np.maximum.accumulate(idx, out=idx)
        first = int(np.flatnonzero(~hole)[0])
        idx[:first] = first
        raw = raw[idx]
    raw = ndimage.median_filter(raw, size=(9, 1), mode="nearest")  # 0.9 s
    z = np.empty_like(raw)
    for j, k in enumerate(names):
        w, mscale = FEATURE_SPEC[k]
        med = np.median(raw[:, j])
        iqr = np.subtract(*np.percentile(raw[:, j], [75, 25]))
        z[:, j] = w * np.clip((raw[:, j] - med) / max(iqr / 1.349, mscale), -3.0, 3.0)
    return Features(names, raw, z)


# ------------------------------------------------------------------------------------------------ novelty
def foote(z: np.ndarray, half: int) -> np.ndarray:
    """Foote novelty of the self-distance matrix with a Gaussian-tapered checkerboard of half-width ``half``."""
    from scipy import signal

    m = z.shape[0]
    if m < 4:
        return np.zeros(m)
    half = max(2, min(half, m // 2))
    # self-similarity as negative Euclidean distance (computed blockwise to bound memory)
    g = signal.windows.gaussian(2 * half, half / 2.0)
    sgn = np.r_[-np.ones(half), np.ones(half)]
    K = np.outer(g * sgn, g * sgn)
    pad = np.pad(z, ((half, half), (0, 0)), mode="edge")
    nov = np.zeros(m)
    for i in range(m):
        blk = pad[i : i + 2 * half]
        d = np.sqrt(np.maximum(((blk[:, None, :] - blk[None, :, :]) ** 2).sum(-1), 0.0))
        nov[i] = -float((K * d).sum())  # cross-block distances minus within-block distances
    nov = np.maximum(nov, 0.0)
    return nov


def novelty(feat: Features, halves_s: Sequence[float] = (4.0, 8.0)) -> np.ndarray:
    """Mean of the per-scale novelty curves, each normalised to its maximum; 0..1 at 10 Hz."""
    out = np.zeros(feat.z.shape[0])
    for h in halves_s:
        nv = foote(feat.z, int(round(h * feat.rate)))
        mx = float(nv.max()) if nv.size else 0.0
        if mx > 0:
            out += nv / mx
    out /= max(1, len(halves_s))
    mx = float(out.max()) if out.size else 0.0
    return out / mx if mx > 0 else out


def upsample(v10: np.ndarray, n: int) -> np.ndarray:
    """10 Hz sample k is the mean over 100 Hz frames [10k, 10k + 10): centre (10k + 4.5) / 100 s."""
    if v10.size == 0:
        return np.zeros(n)
    xc = (np.arange(v10.size) * DS + (DS - 1) / 2.0)
    return np.interp(np.arange(n), xc, v10)


def pick_peaks(nov: np.ndarray, *, rate: int = RATE // DS, min_dist_s: float = 3.0, rel_prom: float = 0.35,
               abs_prom: float = 0.04) -> list[tuple[float, float]]:
    """(t, prominence) of novelty peaks whose prominence is >= rel_prom x the median prominence of the song's 8
    strongest peaks (and >= abs_prom)."""
    from scipy.signal import find_peaks

    pk, props = find_peaks(nov, distance=max(1, int(min_dist_s * rate)), prominence=abs_prom)
    if pk.size == 0:
        return []
    prom = props["prominences"]
    top = np.sort(prom)[::-1][:8]
    thr = max(abs_prom, rel_prom * float(np.median(top)))
    return [((p * DS + (DS - 1) / 2.0) / RATE, float(pr)) for p, pr in zip(pk, prom) if pr >= thr]


def pick_peaks_margin(nov: np.ndarray, z: np.ndarray, *, rate: int = RATE // DS, min_dist_s: float = 3.0,
                      rel_prom: float = 0.35, abs_prom: float = 0.04, band: Sequence[float] = (0.7, 1.3),
                      contrast_span_s: float = 8.0, contrast_min: float = 1.2,
                      report: list | None = None) -> list[tuple[float, float]]:
    """:func:`pick_peaks` with a margin (W4A-STABLE): a peak whose prominence is within ``band`` x the threshold is
    ambiguous (a resample or a gain change moves it across), so it is kept only when the feature contrast across it
    (:func:`contrast`, a block-median measure that does not flicker) is >= ``contrast_min``; above the band it is kept,
    below it dropped."""
    from scipy.signal import find_peaks

    pk, props = find_peaks(nov, distance=max(1, int(min_dist_s * rate)), prominence=abs_prom)
    if pk.size == 0:
        return []
    prom = props["prominences"]
    top = np.sort(prom)[::-1][:8]
    thr = max(abs_prom, rel_prom * float(np.median(top)))
    out = []
    for p, pr in zip(pk, prom):
        t = (p * DS + (DS - 1) / 2.0) / RATE
        if report is not None and pr >= max(abs_prom, band[0] * thr):
            report.append([round(t, 2), round(float(pr / thr), 3), round(contrast(z, t, contrast_span_s, rate), 3)])
        if pr >= band[1] * thr or (pr >= max(abs_prom, band[0] * thr) and contrast(z, t, contrast_span_s, rate) >= contrast_min):
            out.append((t, float(pr)))
    return out


def pick_peaks_in(nov: np.ndarray, t0: float, t1: float, *, rate: int = RATE // DS, min_dist_s: float = 3.0,
                  rel_prom: float = 0.5, abs_prom: float = 0.02) -> list[tuple[float, float]]:
    """Novelty peaks inside [t0, t1] with prominence (measured inside that window) >= rel_prom x the window's largest."""
    from scipy.signal import find_peaks

    i0, i1 = max(0, int(t0 * rate)), min(nov.size, int(math.ceil(t1 * rate)))
    if i1 - i0 < 3:
        return []
    seg = nov[i0:i1]
    pk, props = find_peaks(seg, distance=max(1, int(min_dist_s * rate)), prominence=abs_prom)
    if pk.size == 0:
        return []
    prom = props["prominences"]
    thr = max(abs_prom, rel_prom * float(prom.max()))
    return [(((i0 + q) * DS + (DS - 1) / 2.0) / RATE, float(pr)) for q, pr in zip(pk, prom) if pr >= thr]


# ------------------------------------------------------------------------------------------------ boundaries
@dataclass
class Boundary:
    t: float
    kind: str  # novelty | silence | stop | impact | allin1 | bar-grid | start | end
    strength: float = 1.0
    hard: bool = False  # exact event edge (silence/stop/impact): snapped only within a short tolerance


def downbeats(bars: Sequence[dict[str, Any]]) -> np.ndarray:
    return np.array(sorted(float(b["t"]) for b in bars)) if bars else np.zeros(0)


def bar_len(bars: Sequence[dict[str, Any]], t: float) -> float:
    if not bars:
        return 2.0
    ts = downbeats(bars)
    i = int(np.clip(np.searchsorted(ts, t) - 1, 0, len(bars) - 1))
    b = sorted(bars, key=lambda x: x["t"])[i]
    return float(b.get("d") or 2.0)


def snap(t: float, db: np.ndarray, tol: float) -> tuple[float, bool]:
    if db.size == 0:
        return t, False
    j = int(np.argmin(np.abs(db - t)))
    if abs(db[j] - t) <= tol:
        return float(db[j]), True
    return t, False


def grid_candidates(bars: Sequence[dict[str, Any]], every: int = 4, duration: float = 0.0) -> list[float]:
    """Every ``every``-th downbeat counted from bar 1 (a 4-bar phrase grid); a fixed 8 s grid without bars."""
    if not bars:
        return list(np.arange(8.0, max(duration - 4.0, 8.0), 8.0))
    bs = sorted(bars, key=lambda b: b["t"])
    return [float(b["t"]) for b in bs if int(b.get("bar", 0)) >= 1 and (int(b["bar"]) - 1) % every == 0]


def contrast(raw_z: np.ndarray, t: float, span_s: float, rate: int = RATE // DS) -> float:
    """Feature distance between the blocks [t - span, t) and [t, t + span) (standardised feature space)."""
    i = int(round(t * rate))
    s = max(2, int(round(span_s * rate)))
    a, b = raw_z[max(0, i - s) : i], raw_z[i : i + s]
    if a.shape[0] < 2 or b.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(np.median(a, axis=0) - np.median(b, axis=0)))


# ------------------------------------------------------------------------------------------------ segments
@dataclass
class Segment:
    t: float
    t1: float
    kind_in: str
    stats: dict[str, Any] = field(default_factory=dict)
    level: str = "medium"
    conf: float = 0.5
    silence: bool = False
    #: unsnapped time of the event (impact / stop) that created this part's start boundary: the downbeat snap can move
    #: the boundary by up to half a bar, the evidence (a drop impact) stays where it happened
    t_event: float | None = None

    @property
    def d(self) -> float:
        return self.t1 - self.t


def level_of(rel_lu: float, th: Sequence[float]) -> str:
    """quiet < th0 <= soft < th1 <= medium < th2 <= loud <= th3 < peak (LU relative to integrated)."""
    q, s, m, p = th
    if rel_lu < q:
        return "quiet"
    if rel_lu < s:
        return "soft"
    if rel_lu < m:
        return "medium"
    if rel_lu <= p:
        return "loud"
    return "peak"


def level_conf(rel_lu: float, th: Sequence[float], spread: float) -> float:
    margin = min(abs(rel_lu - x) for x in th)
    c = 0.5 + 0.5 * min(1.0, margin / 2.0)
    return float(np.clip(c * (1.0 - min(0.4, spread / 10.0)), 0.05, 1.0))


def seg_stats(inp: Inputs, ser: dict[str, np.ndarray], intensity: np.ndarray, t0: float, t1: float) -> dict[str, Any]:
    i, j = int(round(t0 * RATE)), max(int(round(t0 * RATE)) + 1, int(round(t1 * RATE)))
    j = min(j, inp.n)
    i = min(i, j - 1)
    st = inp.st[i:j]
    mom = inp.mom[i:j]
    # loudness trend: 1 s smoothed momentary loudness, 0.5 s trimmed at both ends (the 3 s short-term window would
    # smear the neighbours into short parts)
    sm = ser["mom_1s"][i:j]
    e = min(50, max(0, (sm.size - 20) // 2))
    sm = sm[e : sm.size - e]
    tt = np.arange(sm.size) / RATE
    trend = float(np.polyfit(tt, sm, 1)[0]) if sm.size >= 20 else 0.0

    def slope_of(v: np.ndarray) -> float:
        v = v[i:j]
        v = v[e : v.size - e]
        return float(np.polyfit(np.arange(v.size) / RATE, v, 1)[0]) if v.size >= 20 else 0.0
    return {
        "mean_lufs": float(np.mean(st)),
        "rel_lu": float(np.mean(st) - inp.integrated),
        "spread_lu": float(np.std(mom)),
        "mom_power_lufs": float(10.0 * np.log10(np.mean(10.0 ** (mom / 10.0)) + 1e-30)),
        "bass_db": float(10.0 * np.log10(np.mean(10.0 ** (inp.bass_db[i:j] / 10.0)) + 1e-30)),
        "kick_rate": float(np.mean(ser["kick_rate"][i:j])),
        "onset_rate": float(np.mean(ser["onset_rate"][i:j])),
        "brightness_hz": float(np.median(inp.centroid_hz[i:j])),
        "trend_lu_per_s": trend,
        "onset_trend": slope_of(ser["onset_rate"] + ser["kick_rate"]),
        "bright_trend": slope_of(ser["bright_oct"]),
        "energy": float(np.mean(intensity[i:j])),
    }


def intensity_curve(inp: Inputs, ser: dict[str, np.ndarray]) -> np.ndarray:
    """dyn.intensity: 0.45 x loudness (short-term LU vs integrated, -18 LU -> 0, +4 LU -> 1) + 0.2 x bass +
    0.2 x onset density (kicks + mid/high onsets) + 0.15 x brightness, the last three per-song p02-p98, smoothed
    with a 0.5 s zero-phase Hann window."""
    from scipy.signal import filtfilt

    def pn(v: np.ndarray) -> np.ndarray:
        lo, hi = np.percentile(v, 2), np.percentile(v, 98)
        return np.clip((v - lo) / (hi - lo), 0.0, 1.0) if hi - lo > 1e-9 else np.zeros_like(v)

    loud = np.clip((inp.st - inp.integrated + 18.0) / 22.0, 0.0, 1.0)
    bass = pn(inp.bass_db)
    dens = pn(ser["kick_rate"] + ser["onset_rate"])
    bright = pn(ser["bright_oct"])
    v = 0.45 * loud + 0.2 * bass + 0.2 * dens + 0.15 * bright
    silent = inp.mom <= -69.9
    v = np.where(silent, 0.0, v)
    k = np.hanning(51)
    k = k / k.sum()
    if v.size > 3 * k.size:
        v = filtfilt(k, [1.0], v)
    return np.clip(v, 0.0, 1.0)
