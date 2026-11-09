"""Dynamics event detectors (pure numpy/scipy): silences (Z), stops (X), impacts (I), decay tails (Y), plus the shared
input series. All times in seconds; 100 Hz series have sample i centred at i / 100 s; the fine level envelope is
200 Hz (5 ms RMS of the mix, centred).

Thresholds are relative to the song (integrated loudness, percentiles), so quiet and loud masters behave the same."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

RATE = 100
FINE_RATE = 200
LUFS_FLOOR = -70.0
DB_FLOOR = -120.0


# ------------------------------------------------------------------------------------------------ inputs
@dataclass
class Inputs:
    """Everything the dynamics stage reads, as arrays (100 Hz unless noted)."""

    st: np.ndarray  # short-term LUFS (centred 3 s)
    mom: np.ndarray  # momentary LUFS (centred 0.4 s)
    integrated: float
    bass_db: np.ndarray
    kick_db: np.ndarray
    centroid_hz: np.ndarray
    slope: np.ndarray
    width: np.ndarray
    kicks: list[tuple[float, float]]  # (t, strength)
    onsets_mid: list[float]
    onsets_high: list[float]
    bars: list[dict[str, Any]]  # rhythm bars: t, d, bar (+ in_pulse when present)
    fine_db: np.ndarray  # 200 Hz, 5 ms RMS of the mix in dBFS
    duration: float

    @property
    def n(self) -> int:
        return self.st.size

    def transients(self) -> np.ndarray:
        t = [k for k, _ in self.kicks] + list(self.onsets_mid) + list(self.onsets_high)
        return np.array(sorted(t)) if t else np.zeros(0)


def fine_envelope(x: np.ndarray, sr: int, rate: int = FINE_RATE, win_s: float = 0.005) -> np.ndarray:
    """Centred ``win_s`` RMS (mean square over channels) of the mix at ``rate`` Hz, dBFS floored at -120."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[None, :]
    z = (x * x).mean(axis=0)
    cs = np.concatenate([[0.0], np.cumsum(z)])
    nj = int(math.ceil(z.size * rate / sr))
    c = np.round(np.arange(nj) * sr / rate).astype(np.int64)
    h = max(1, int(round(win_s * sr / 2)))
    a, b = np.clip(c - h, 0, z.size), np.clip(c + h, 0, z.size)
    ms = (cs[b] - cs[a]) / (2 * h)
    with np.errstate(divide="ignore"):
        d = 10.0 * np.log10(ms)
    return np.maximum(np.nan_to_num(d, neginf=DB_FLOOR, nan=DB_FLOOR), DB_FLOOR)


def density(times: Sequence[float], weights: Sequence[float] | None, n: int, win_s: float = 2.0,
            rate: int = RATE) -> np.ndarray:
    """Events per second around each frame (Hann-weighted centred window of ``win_s``)."""
    imp = np.zeros(n)
    w = list(weights) if weights is not None else [1.0] * len(times)
    for t, v in zip(times, w):
        i = int(round(t * rate))
        if 0 <= i < n:
            imp[i] += v
    k = np.hanning(max(3, int(round(win_s * rate)) | 1))
    k = k / k.sum() * rate  # integrates to events per second
    return np.convolve(imp, k, mode="same")


def win_mean(v: np.ndarray, a: float, b: float, rate: int = RATE) -> float:
    i, j = max(0, int(round(a * rate))), min(v.size, int(round(b * rate)))
    if j <= i:
        return float(v[min(max(i, 0), v.size - 1)])
    return float(np.mean(v[i:j]))


def power_mean_db(v: np.ndarray) -> float:
    return float(10.0 * np.log10(np.mean(10.0 ** (np.asarray(v, dtype=np.float64) / 10.0)) + 1e-30))


def silence_threshold(integrated: float, rel_lu: float = 35.0, cap: float | None = None) -> float:
    """Momentary loudness below which the song is (near) silent: integrated - ``rel_lu`` LU (relative only, so a pure
    gain change of the master moves the threshold with it, W4V-GAIN-REAL), optionally at most ``cap`` LUFS, and at least
    just above the -70 LUFS floor (digital silence is always silent, even in a song that is silent throughout)."""
    thr = integrated - rel_lu
    if cap is not None:
        thr = min(thr, float(cap))
    return max(thr, LUFS_FLOOR + 0.5)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[(start, stop)) runs of True."""
    if mask.size == 0:
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _refine_edge(fine: np.ndarray, t_guess: float, thr: float, rising: bool, search_s: float = 0.35) -> float:
    """Exact edge on the 5 ms envelope near t_guess: the last crossing of ``thr`` (falling into silence) or the first
    crossing out of it (rising)."""
    j0 = max(0, int((t_guess - search_s) * FINE_RATE))
    j1 = min(fine.size - 1, int((t_guess + search_s) * FINE_RATE))
    seg = fine[j0 : j1 + 1] > thr
    if seg.size == 0:
        return t_guess
    if rising:
        idx = np.flatnonzero(seg)
        # first sound sample after the quiet part
        q = np.flatnonzero(~seg)
        if q.size == 0 or idx.size == 0:
            return t_guess
        after = idx[idx > q[0]]
        return (j0 + (after[0] if after.size else idx[0])) / FINE_RATE
    idx = np.flatnonzero(seg)
    q = np.flatnonzero(~seg)
    if q.size == 0 or idx.size == 0:
        return t_guess
    before = idx[idx < q[-1]]
    return (j0 + (before[-1] + 1 if before.size else q[0])) / FINE_RATE


# ------------------------------------------------------------------------------------------------ silences / stops
@dataclass
class Silence:
    t: float
    d: float
    depth_db: float
    edge: bool  # touches the start or the end of the song
    digital: bool


def detect_silences(inp: Inputs, *, rel_lu: float = 35.0, cap: float | None = None, min_s: float = 0.3,
                    min_edge_s: float = 1.0) -> list[Silence]:
    """Stretches where the momentary loudness stays below the silence threshold. The 0.4 s momentary window shrinks a
    silence by 0.2 s on each side, so the run is widened by 0.2 s and its edges are re-measured on the 5 ms envelope.
    Leading/trailing silence counts only from ``min_edge_s``."""
    thr = silence_threshold(inp.integrated, rel_lu, cap)
    out: list[Silence] = []
    fine_thr = thr  # the 5 ms RMS in dBFS is on (roughly) the same scale as LUFS for broadband music
    for a, b in _runs(inp.mom < thr):
        t0 = max(0.0, a / RATE - 0.2)
        t1 = min(inp.duration, b / RATE + 0.2 - 1.0 / RATE)
        if a > 0:
            t0 = _refine_edge(inp.fine_db, t0, fine_thr, rising=False)
        if b < inp.n:
            t1 = _refine_edge(inp.fine_db, t1, fine_thr, rising=True)
        t0 = max(0.0, t0)
        t1 = min(inp.duration, t1)
        d = t1 - t0
        edge = a == 0 or b >= inp.n
        if d < (min_edge_s if edge else min_s):
            continue
        core = inp.mom[a:b]
        lvl = float(np.median(core)) if core.size else LUFS_FLOOR
        i0, i1 = int(t0 * FINE_RATE), max(int(t0 * FINE_RATE) + 1, int(t1 * FINE_RATE))
        digital = bool(np.all(inp.fine_db[i0:i1] <= DB_FLOOR + 1e-6))
        out.append(Silence(t0, d, inp.integrated - lvl, edge, digital))
    return out


@dataclass
class Stop:
    t: float
    strength: float
    gap_s: float
    drop_db: float
    silence: bool


def detect_stops(inp: Inputs, silences: list[Silence], *, near_rel_lu: float = 20.0, min_gap_s: float = 0.25,
                 pre_rel_lu: float = 12.0, max_fall_s: float = 0.15, min_drop_db: float = 15.0) -> list[Stop]:
    """Sudden cuts to (near) silence: the 5 ms level falls by >= min_drop_db within max_fall_s from a passage that was
    at least integrated - pre_rel_lu, into a gap below integrated - near_rel_lu lasting >= min_gap_s (every non-edge
    silence that starts abruptly is a stop; so are near-silent breaks)."""
    near = inp.integrated - near_rel_lu
    cands: list[tuple[float, float]] = [(s.t, s.d) for s in silences if not (s.edge and s.t <= 0.0)]
    for a, b in _runs(inp.mom < near):
        t0, t1 = a / RATE - 0.2, b / RATE + 0.2
        if a == 0 or t1 - t0 < min_gap_s + 0.4 - 0.4:
            continue
        if any(abs(t0 - s) < 0.5 for s, _ in cands):
            continue
        t0 = _refine_edge(inp.fine_db, max(0.0, t0), near, rising=False)
        t1 = _refine_edge(inp.fine_db, min(inp.duration, t1), near, rising=True) if b < inp.n else inp.duration
        if t1 - t0 >= min_gap_s:
            cands.append((t0, t1 - t0))
    out: list[Stop] = []
    for t0, gap in sorted(cands):
        pre = win_mean(inp.mom, t0 - 1.0, t0 - 0.25)
        if pre < inp.integrated - pre_rel_lu:
            continue
        j = int(round(t0 * FINE_RATE))
        k = int(round(max_fall_s * FINE_RATE))
        before = float(np.max(inp.fine_db[max(0, j - k) : j + 1])) if j > 0 else DB_FLOOR
        after = float(np.median(inp.fine_db[j + 1 : j + 1 + max(2, int(min(gap, 0.5) * FINE_RATE))])) if j + 1 < inp.fine_db.size else DB_FLOOR
        drop = before - after
        if drop < min_drop_db:
            continue
        in_gap = win_mean(inp.mom, t0 + 0.2, t0 + max(0.25, gap - 0.2))
        depth = pre - in_gap
        sil = any(abs(s.t - t0) < 0.05 for s in silences)
        out.append(Stop(t0, float(np.clip(depth / 40.0, 0.0, 1.0)), gap, drop, sil))
    return out


# ------------------------------------------------------------------------------------------------ impacts
@dataclass
class Impact:
    t: float
    strength: float
    delta_lu: float
    delta_bass_db: float
    score: float
    snapped: bool
    after_silence: bool = False
    major: bool = False  # one of the song's biggest energy increases (kept as a part boundary)


def step_series(v: np.ndarray, pre: tuple[float, float], post: tuple[float, float], rate: int = RATE) -> np.ndarray:
    """d[i] = mean(v[i + post]) - mean(v[i + pre]) (windows in seconds relative to i, clamped at the edges)."""
    n = v.size
    cs = np.concatenate([[0.0], np.cumsum(v)])
    i = np.arange(n)

    def m(a: float, b: float) -> np.ndarray:
        lo = np.clip(i + int(round(a * rate)), 0, n)
        hi = np.clip(i + int(round(b * rate)), 0, n)
        hi = np.maximum(hi, lo + 1)
        hi = np.minimum(hi, n)
        lo = np.minimum(lo, hi - 1)
        return (cs[hi] - cs[lo]) / (hi - lo)

    return m(*post) - m(*pre)


def detect_impacts(inp: Inputs, silences: list[Silence], *, theta_lu: float = 4.0, theta_bass_db: float = 6.0,
                   theta_hit_lu: float = 6.0, theta_bright_oct: float = 0.5, min_score: float = 1.0,
                   min_dist_s: float = 1.0, min_prom: float = 0.3, start_s: float = 2.0,
                   major_rel: float = 0.5, major_min: float = 2.0) -> list[Impact]:
    """Sudden energy increases. Per frame:

    * sustained step: dLU = momentary loudness 0.25-1.5 s after minus 0.25-1.5 s before (LU), dBass = bass band dB
      0.1-1.5 s after minus before; the bass step counts only when the loudness does not fall and the bass after is a
      real part of the mix (>= the song's median bass - 6 dB), and needs 9 dB when the loudness rises < 1 LU;
    * hit: the momentary peak 0.05-0.35 s after minus the mean 0.2-1 s before (a final hit, a stab);
    * score = max(dLU / 4, dBass / 6, hit / 6) + 0.25 x clip(dBrightness / 0.5 oct, 0, 1).

    strength = clip(0.15 + 0.3 x score, 0, 1). Peaks with score >= 1 (prominence >= 0.3, at least 1 s apart) become impacts, placed on the transient (kick or mid/high
    onset) with the largest 5 ms level jump within [-0.3 s, +0.5 s] of the peak. The first 2 s of sound after the
    lead-in are the song's start, not an impact."""
    from scipy import ndimage
    from scipy.signal import find_peaks

    dl = step_series(inp.mom, (-1.5, -0.25), (0.25, 1.5))
    db = step_series(inp.bass_db, (-1.5, -0.1), (0.1, 1.5))
    lc = np.log2(np.maximum(inp.centroid_hz, 20.0))
    dc = step_series(lc, (-1.5, -0.1), (0.1, 1.5))
    cs = np.concatenate([[0.0], np.cumsum(inp.bass_db)])
    i = np.arange(inp.n)
    a, b = np.clip(i + 10, 0, inp.n), np.clip(i + 150, 1, inp.n)
    b = np.maximum(b, np.minimum(a + 1, inp.n))
    post_bass = (cs[b] - cs[np.minimum(a, b - 1)]) / np.maximum(b - np.minimum(a, b - 1), 1)
    sounding = inp.bass_db[inp.mom > silence_threshold(inp.integrated)]
    med_bass = float(np.median(sounding)) if sounding.size else -60.0
    bass_ok = (dl > -0.5) & (post_bass >= med_bass - 6.0)
    # momentary peak over [t + 0.05, t + 0.35] (the 0.4 s window puts a hit's peak ~0.2 s after it)
    peak_after = ndimage.maximum_filter1d(inp.mom, size=31, origin=-15, mode="nearest")
    peak_after = np.concatenate([peak_after[5:], np.full(5, peak_after[-1] if peak_after.size else 0.0)])
    cm = np.concatenate([[0.0], np.cumsum(inp.mom)])
    lo, hi = np.clip(i - 100, 0, inp.n), np.clip(i - 20, 1, inp.n)
    lo = np.minimum(lo, hi - 1)
    pre_mean = (cm[hi] - cm[lo]) / np.maximum(hi - lo, 1)
    hit = peak_after - pre_mean
    # a bass step without a loudness step (limited masters, a bass line entering) needs 1.5x the dB
    bass_term = np.where(bass_ok, db / (theta_bass_db * np.where(dl >= 1.0, 1.0, 1.5)), 0.0)
    s_sus = np.maximum(dl / theta_lu, bass_term)
    score = np.maximum.reduce([s_sus, hit / theta_hit_lu, np.zeros_like(dl)])
    score = score + 0.25 * np.clip(dc / theta_bright_oct, 0.0, 1.0) * (score > 0.5)
    if silences and silences[0].edge and silences[0].t <= 0.0:
        lead_end = silences[0].t + silences[0].d
    else:
        loud = np.flatnonzero(inp.mom > silence_threshold(inp.integrated))
        lead_end = max(0.0, loud[0] / RATE - 0.2) if loud.size else 0.0
    score[: int(round((lead_end + start_s) * RATE))] = 0.0  # the song's first sound is a start, not an impact
    pk, _ = find_peaks(score, height=min_score, distance=max(1, int(min_dist_s * RATE)), prominence=min_prom)
    tr = inp.transients()
    out: list[Impact] = []
    for k in pk:
        t = k / RATE
        snapped = False
        if tr.size:
            # the impact is the transient with the largest jump of the 5 ms level around the score peak
            near = tr[(tr >= t - 0.3) & (tr <= t + 0.5)]
            best, bj = 3.0, None
            for tc in near:
                jc = int(round(tc * FINE_RATE))
                post = float(np.max(inp.fine_db[jc : jc + 16])) if jc < inp.fine_db.size else -120.0
                pre = float(np.median(inp.fine_db[max(0, jc - 80) : max(1, jc - 10)]))
                if post - pre > best:
                    best, bj = post - pre, float(tc)
            if bj is not None:
                t, snapped = bj, True
        sc = float(score[k])
        after_sil = any(abs((z.t + z.d) - t) < 0.3 for z in silences)
        out.append(Impact(t, float(np.clip(0.15 + 0.3 * sc, 0.0, 1.0)), float(dl[k]), float(db[k]), sc, snapped,
                          after_sil))
    # major impacts: those ending a silence, and those scoring >= half the song's largest (and >= 2)
    top = max([im.score for im in out if not im.after_silence], default=0.0)
    for im in out:
        im.major = im.after_silence or im.score >= max(major_min, major_rel * top)
    return out


# ------------------------------------------------------------------------------------------------ decay tails
@dataclass
class DecayTail:
    t: float
    d: float
    strength: float
    rate_db_s: float
    drop_db: float


def detect_decay_tails(inp: Inputs, impacts: list[Impact], *, min_s: float = 1.0, min_drop_db: float = 10.0,
                       min_rate: float = 3.0, max_rate: float = 80.0, quiet_ratio: float = 0.3,
                       end_rel_db: float = 35.0) -> list[DecayTail]:
    """Ringing-out tails: after a hit (a transient), at least ``min_s`` without a comparable new attack while the 5 ms
    level (smoothed to 50 ms) falls by >= 10 dB at 3-80 dB/s. The tail ends at the next comparable attack, when the
    level is ``end_rel_db`` below the hit, or at the end of the song. Strength = loudness of the hit vs integrated."""
    from scipy import ndimage

    fine = ndimage.uniform_filter1d(inp.fine_db, size=10, mode="nearest")  # 50 ms
    hits: list[tuple[float, float]] = [(k, s) for k, s in inp.kicks] + [(t, 1.0) for t in inp.onsets_mid]
    hits += [(t, 0.6) for t in inp.onsets_high] + [(im.t, 2.0) for im in impacts]
    hits.sort()
    if not hits:
        return []
    times = np.array([h[0] for h in hits])
    out: list[DecayTail] = []
    last_end = -1.0
    for idx, (t0, _) in enumerate(hits):
        if t0 < last_end:
            continue
        j0 = int(round(t0 * FINE_RATE))
        if j0 >= fine.size - 2:
            continue
        pk_j = j0 + int(np.argmax(fine[j0 : j0 + int(0.12 * FINE_RATE)]))
        peak = float(fine[pk_j])
        if peak < inp.integrated - 25.0:
            continue
        # next comparable attack: a transient whose 5 ms level rises to within quiet_ratio (in dB: 10 dB) of the
        # current decayed level + 6 dB, i.e. a new event that re-excites the sound
        nxt = inp.duration
        for t1 in times[idx + 1 :]:
            if t1 <= t0 + 0.05:
                continue
            j = int(round(t1 * FINE_RATE))
            pre = float(fine[max(0, j - 4)])
            post = float(np.max(fine[j : j + 8])) if j < fine.size else pre
            if post - pre > 3.0 and post > peak - 20.0:
                nxt = float(t1)
                break
        if nxt - t0 < min_s:
            continue
        j_end = min(fine.size - 1, int(round(nxt * FINE_RATE)) - 1)
        seg = fine[pk_j : j_end + 1]
        if seg.size < int(min_s * FINE_RATE):
            continue
        below = np.flatnonzero(seg < peak - end_rel_db)
        k_end = int(below[0]) if below.size else seg.size - 1
        seg = seg[: k_end + 1]
        if seg.size < int(min_s * FINE_RATE * 0.8):
            continue
        drop = peak - float(np.min(seg[-max(2, seg.size // 5) :]))
        if drop < min_drop_db:
            continue
        tt = np.arange(seg.size) / FINE_RATE
        slope, icpt = np.polyfit(tt, seg, 1)
        rate = -float(slope)
        resid = seg - (slope * tt + icpt)
        r2 = 1.0 - float(np.var(resid)) / max(float(np.var(seg)), 1e-9)
        if not (min_rate <= rate <= max_rate) or r2 < 0.5:
            continue
        end = min(inp.duration, (pk_j + k_end) / FINE_RATE)
        if end - t0 < min_s:
            continue
        strength = float(np.clip((peak - (inp.integrated - 20.0)) / 25.0, 0.0, 1.0))
        out.append(DecayTail(float(t0), end - float(t0), strength, rate, drop))
        last_end = end
    return out


@dataclass
class Detections:
    silences: list[Silence] = field(default_factory=list)
    stops: list[Stop] = field(default_factory=list)
    impacts: list[Impact] = field(default_factory=list)
    decay_tails: list[DecayTail] = field(default_factory=list)
