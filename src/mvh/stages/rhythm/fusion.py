# ruff: noqa: E501
"""Rhythm fusion core (pure numpy; no model imports): tempo arbitration, beat tracking on a fused activation,
sub-frame refinement and transient snapping, pulse regions and the virtual grid, the 2-of-3 downbeat vote with a
meter HMM over beats, tempo segments and per-segment feel.

Every function takes plain arrays at FPS = 100 (frame i is centred at i / 100 s) so it can be unit-tested on
synthetic activations without the models.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

FPS = 100.0
RELATIONS = ((1.0, "x1"), (2.0, "x2"), (0.5, "x0.5"), (1.5, "x1.5"), (2 / 3, "x0.667"), (4 / 3, "x1.333"), (0.75, "x0.75"))


# ============================================================================================ basics
def f_measure(est: Sequence[float], ref: Sequence[float], tol: float = 0.07) -> float:
    """mir_eval-style F-measure with one-to-one greedy matching inside +-tol."""
    e = np.sort(np.asarray(est, float))
    r = np.sort(np.asarray(ref, float))
    if len(e) == 0 and len(r) == 0:
        return 1.0
    if len(e) == 0 or len(r) == 0:
        return 0.0
    used = np.zeros(len(r), bool)
    hit = 0
    j0 = 0
    for t in e:
        while j0 < len(r) and r[j0] < t - tol:
            j0 += 1
        best, bd = -1, tol + 1e-12
        j = j0
        while j < len(r) and r[j] <= t + tol:
            if not used[j] and abs(r[j] - t) <= bd:
                best, bd = j, abs(r[j] - t)
            j += 1
        if best >= 0:
            used[best] = True
            hit += 1
    p, rc = hit / len(e), hit / len(r)
    return 0.0 if hit == 0 else 2 * p * rc / (p + rc)


def resample_to(x: np.ndarray, src_fps: float, n: int, fps: float = FPS, shift: float = 0.0) -> np.ndarray:
    """Linear resampling of a frame-centred activation (frame j at j/src_fps + shift seconds) to n frames at fps."""
    x = np.asarray(x, np.float64).reshape(-1)
    if len(x) == 0:
        return np.zeros(n)
    t = np.arange(n) / fps
    return np.interp(t, np.arange(len(x)) / src_fps + shift, x, left=x[0], right=0.0)


def fit_len(x: np.ndarray | None, n: int) -> np.ndarray | None:
    if x is None:
        return None
    x = np.asarray(x, np.float64).reshape(-1)
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros(n - len(x))])


def norm01(x: np.ndarray, q: float = 99.5) -> np.ndarray:
    x = np.maximum(np.asarray(x, np.float64), 0.0)
    hi = np.percentile(x, q) if x.size else 0.0
    if hi <= 1e-12:
        return np.zeros_like(x)
    return np.clip(x / hi, 0.0, 1.0)


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(x, np.float64), -60, 60)))


def bpm_of(beats: Sequence[float] | None) -> float | None:
    if beats is None:
        return None
    b = np.asarray(beats, float)
    if len(b) < 4:
        return None
    ibi = np.diff(b)
    ibi = ibi[(ibi > 0.15) & (ibi < 2.5)]
    return float(60.0 / np.median(ibi)) if len(ibi) else None


def local_peaks(x: np.ndarray, thr: float, min_dist: int) -> np.ndarray:
    x = np.asarray(x, float)
    if len(x) < 3:
        return np.zeros(0, int)
    c = (x[1:-1] >= x[:-2]) & (x[1:-1] > x[2:]) & (x[1:-1] >= thr)
    idx = np.nonzero(c)[0] + 1
    if min_dist <= 1 or len(idx) == 0:
        return idx
    keep: list[int] = []
    for i in idx[np.argsort(-x[idx], kind="stable")]:
        if all(abs(i - k) >= min_dist for k in keep):
            keep.append(int(i))
    return np.array(sorted(keep), int)


def parabolic(x: np.ndarray, i: int) -> float:
    """Sub-frame peak position by a parabola through x[i-1..i+1]."""
    if i <= 0 or i >= len(x) - 1:
        return float(i)
    a, b, c = x[i - 1], x[i], x[i + 1]
    den = a - 2 * b + c
    if abs(den) < 1e-12:
        return float(i)
    off = 0.5 * (a - c) / den
    return float(i + max(-0.5, min(0.5, off)))


# ============================================================================================ tempo arbitration
def smooth_same(x: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """np.convolve(x, kernel, 'same') with the output always len(x), also when the kernel is longer than the signal."""
    x = np.asarray(x, float)
    m = len(kernel)
    c = np.convolve(x, kernel, mode="full")
    s0 = (m - 1) // 2
    return c[s0:s0 + len(x)]


def tempogram_peaks(onset: np.ndarray, fps: float = FPS, win_s: float = 8.0, lo: float = 45.0, hi: float = 260.0,
                    k: int = 8) -> list[tuple[float, float]]:
    """Peaks of the windowed-autocorrelation tempogram averaged over the song: [(bpm, salience 0..1)]."""
    o = np.asarray(onset, float)
    o = o - smooth_same(o, np.ones(int(fps)) / fps)  # remove slow trend
    o = np.maximum(o, 0)
    w = int(win_s * fps)
    hop = w // 2
    lag_lo, lag_hi = int(60 * fps / hi), int(math.ceil(60 * fps / lo))
    acc = np.zeros(lag_hi + 2)
    nwin = 0
    for s in range(0, max(1, len(o) - w + 1), max(1, hop)):
        seg = o[s:s + w]
        if seg.std() < 1e-9:
            continue
        seg = (seg - seg.mean()) * np.hanning(len(seg))
        f = np.fft.rfft(seg, 2 * len(seg))
        ac = np.fft.irfft(f * np.conj(f))[: lag_hi + 2]
        if ac[0] <= 0:
            continue
        acc += ac / ac[0]
        nwin += 1
    if nwin == 0:
        return []
    acc /= nwin
    lags = np.arange(len(acc))
    vals = acc.copy()
    vals[:lag_lo] = -np.inf
    out = []
    for i in range(max(lag_lo, 1), lag_hi + 1):
        if vals[i] > vals[i - 1] and vals[i] >= vals[i + 1] and vals[i] > 0:
            li = parabolic(acc, i)
            out.append((60 * fps / li, float(acc[i])))
    if not out:
        return []
    mx = max(v for _, v in out)
    out = sorted(((b, v / mx) for b, v in out), key=lambda p: -p[1])[:k]
    _ = lags
    return out


def _grid_positions(n_frames: int, period: float, phase: float) -> np.ndarray:
    k = np.arange(int((n_frames - phase) / period) + 1)
    return phase + k * period


def metrical_evidence(drum: np.ndarray, bpm: float, fps: float = FPS, win_s: float = 6.0) -> dict[str, float]:
    """How well a beat level at ``bpm`` explains the drum onset envelope (kick + snare evidence).

    Per window (best phase), on = mean envelope at grid positions, off = at half-beat positions;
    contrast = (on - off) / (on + off); coverage = share of grid positions carrying a clear hit.
    A too-slow level has strong half-beat positions (low contrast); a too-fast level leaves half its beats empty
    (low coverage). Returns window-energy-weighted means."""
    d = np.asarray(drum, float)
    n = len(d)
    period = 60.0 * fps / bpm
    if period < 4 or n < 4 * period:
        return {"contrast": 0.0, "coverage": 0.0, "score": 0.0}
    w = min(max(int(win_s * fps), int(4 * period)), n)      # the window never exceeds the song
    hop = w // 2
    dpad = np.concatenate([d, np.zeros(int(2 * period) + 4)])
    # local max over +-2 frames, robust to small phase errors
    mx = np.maximum.reduce([np.roll(dpad, s) for s in (-2, -1, 0, 1, 2)])
    thr_global = 0.5 * np.percentile(d[d > 0], 60) if np.any(d > 0) else 0.0
    cs, cv, ws = [], [], []
    nph = max(4, int(round(period)))
    for s in range(0, max(1, n - w + 1), max(1, hop)):
        e = float(d[s:s + w].sum())
        if e <= 1e-9:
            continue
        best = None
        for ph in np.linspace(0, period, nph, endpoint=False):
            pos = s + _grid_positions(w, period, ph)
            pos = pos[pos < s + w]
            on = mx[np.round(pos).astype(int)]
            if best is None or on.mean() > best[0]:
                off = mx[np.round(pos + period / 2).astype(int)]
                best = (on.mean(), off.mean(), np.mean(on >= max(thr_global, 0.25 * on.max())))
        on_m, off_m, cov = best
        cs.append((on_m - off_m) / (on_m + off_m + 1e-12))
        cv.append(cov)
        ws.append(e)
    if not ws:
        return {"contrast": 0.0, "coverage": 0.0, "score": 0.0}
    ws_a = np.asarray(ws)
    c = float(np.average(cs, weights=ws_a))
    v = float(np.average(cv, weights=ws_a))
    return {"contrast": round(c, 4), "coverage": round(v, 4), "score": round(max(c, 0.0) * v ** 0.75, 4)}


def tempo_prior(bpm: float, centre: float = 120.0, sigma_oct: float = 0.7) -> float:
    return float(math.exp(-0.5 * (math.log2(bpm / centre) / sigma_oct) ** 2))


@dataclass
class Arbitration:
    bpm: float
    candidates: list[dict[str, Any]]
    evidence: dict[str, Any]
    ambiguous: bool
    margin: float


def arbitrate_tempo(estimates: Mapping[str, float | None], peaks: Sequence[tuple[float, float]], drum: np.ndarray, *,
                    weights: Mapping[str, float] | None = None, forced: float | None = None, fps: float = FPS,
                    lo: float = 50.0, hi: float = 230.0) -> Arbitration:
    """Pick the beat level among the tracker estimates, the tempogram peaks and their x2 / x0.5 relatives.

    score = 1.0 consensus (share of tracker weight within 4 %) + 1.0 metrical (drum contrast x coverage)
          + 0.4 tempogram salience + 0.6 resonance prior (log-normal around 120 BPM, sigma 0.7 octave)."""
    w = {"beat_this": 1.0, "madmom": 1.0, "allin1": 1.0, "librosa": 0.5}
    w.update(weights or {})
    raw: list[tuple[float, str]] = []
    for k, v in estimates.items():
        if v:
            raw.append((float(v), k))
    for b, _ in peaks:
        raw.append((float(b), "tempogram"))
    cands: list[float] = []
    for b, _src in raw:
        for m in (1.0, 2.0, 0.5):
            x = b * m
            if lo <= x <= hi and not any(abs(x / c - 1) < 0.035 for c in cands):
                cands.append(x)
    if forced:
        cands = [float(forced)] + [c for c in cands if abs(c / forced - 1) >= 0.035]
    if not cands:
        cands = [120.0]
    wsum = sum(w.get(k, 0.5) for k, v in estimates.items() if v) or 1.0
    rows = []
    for c in cands:
        # refine the candidate to the weighted mean of the estimates that support it
        sup = [(v, w.get(k, 0.5)) for k, v in estimates.items() if v and abs(v / c - 1) < 0.04]
        sup += [(b, 0.25) for b, _ in peaks if abs(b / c - 1) < 0.03]
        cc = float(sum(v * ww for v, ww in sup) / sum(ww for _, ww in sup)) if sup and not (forced and c == forced) else c
        cons = sum(w.get(k, 0.5) for k, v in estimates.items() if v and abs(v / cc - 1) < 0.04) / wsum
        sal = max([s for b, s in peaks if abs(b / cc - 1) < 0.04], default=0.0)
        met = metrical_evidence(drum, cc, fps)
        pri = tempo_prior(cc)
        score = 1.0 * cons + 1.0 * met["score"] + 0.4 * sal + 0.6 * pri
        rows.append({"bpm": round(cc, 3), "score": round(score, 4),
                     "parts": {"consensus": round(cons, 3), "metrical": met["score"], "contrast": met["contrast"],
                               "coverage": met["coverage"], "salience": round(sal, 3), "prior": round(pri, 3)},
                     "supported_by": sorted(k for k, v in estimates.items() if v and abs(v / cc - 1) < 0.04)})
    rows.sort(key=lambda r: -r["score"])
    best = rows[0] if not forced else next(r for r in rows if abs(r["bpm"] / forced - 1) < 1e-9 or r is rows[0])
    if forced:
        best = {"bpm": float(forced), "score": None, "parts": {}, "supported_by": ["override"]}
    chosen = float(best["bpm"])
    # relation labels w.r.t. the chosen tempo; keep the closest candidate per relation
    out, seen = [], set()
    others = [r for r in rows if abs(r["bpm"] / chosen - 1) >= 0.035]
    out.append({"bpm": round(chosen, 3), "score": 1.0, "relation": "x1"})
    top = rows[0]["score"] if rows[0]["score"] else 1.0
    for r in others:
        ratio = r["bpm"] / chosen
        rel = min(RELATIONS, key=lambda m: abs(math.log(ratio / m[0])))
        tag = rel[1] if abs(math.log(ratio / rel[0])) < 0.05 else f"x{ratio:.3f}"
        if tag in seen or tag == "x1":
            continue
        seen.add(tag)
        out.append({"bpm": round(r["bpm"], 3), "score": round(max(0.0, r["score"] / top), 3), "relation": tag})
    second = next((r for r in rows if abs(r["bpm"] / chosen - 1) >= 0.035), None)
    margin = (rows[0]["score"] - second["score"]) if (second and not forced) else 1.0
    amb = bool(second is not None and not forced and margin < 0.25)
    return Arbitration(chosen, out, {"rows": rows, "estimates": {k: (round(v, 3) if v else None) for k, v in estimates.items()},
                                     "tempogram_peaks": [[round(b, 2), round(s, 3)] for b, s in peaks], "forced": forced},
                       amb, round(float(margin), 4))


# ============================================================================================ beat tracking
def track_beats(act: np.ndarray, bpm_lo: float, bpm_hi: float, fps: float = FPS, transition_lambda: float = 100.0,
                observation_lambda: int = 16) -> np.ndarray:
    """Beat-only HMM (madmom-infer BeatStateSpace / BeatTransitionModel / RNNBeatTrackingObservationModel) on a 0..1
    activation, tempo restricted to [bpm_lo, bpm_hi]. Returns sub-frame beat positions in frames (parabolic peak
    of the activation inside each beat range)."""
    from madmom_infer.features.beats_hmm import (
        BeatStateSpace,
        BeatTransitionModel,
        RNNBeatTrackingObservationModel,
    )
    from madmom_infer.ml.hmm import HiddenMarkovModel

    class _Obs(RNNBeatTrackingObservationModel):
        # madmom-infer 0.2.0's port calls np.asarray(..., ndmin=1), which numpy 2.5 rejects; same densities as madmom
        def log_densities(self, observations):
            o = np.atleast_1d(np.asarray(observations, np.float64))
            out = np.empty((len(o), 2), np.float64)
            out[:, 0] = np.log((1.0 - o) / (self.observation_lambda - 1))
            out[:, 1] = np.log(o)
            return out

    a = np.clip(np.asarray(act, np.float64), 1e-6, 1 - 1e-6)
    min_i, max_i = 60.0 * fps / bpm_hi, 60.0 * fps / bpm_lo
    st = BeatStateSpace(min_i, max_i)
    tm = BeatTransitionModel(st, transition_lambda)
    om = _Obs(st, observation_lambda)
    path, _ = HiddenMarkovModel(tm, om).viterbi(a.astype(np.float32))
    rng = om.pointers[path] >= 1
    idx = np.nonzero(np.diff(rng.astype(int)))[0] + 1
    if rng[0]:
        idx = np.r_[0, idx]
    if rng[-1]:
        idx = np.r_[idx, rng.size]
    out = []
    for s, e in zip(idx[::2], idx[1::2]):
        k = int(s + np.argmax(a[s:e]))
        out.append(parabolic(a, k))
    return np.asarray(out, float)


# ============================================================================================ transients
@dataclass
class Transients:
    times: np.ndarray
    rise_db: np.ndarray


def transients(x: np.ndarray, sr: int, hop_s: float = 0.001, win_s: float = 0.004, min_rise_db: float = 6.0,
               lowpass_hz: float | None = 200.0) -> Transients:
    """Sharp energy onsets (broadband and low band): time of the steepest log-energy rise, with the rise over
    10 ms in dB. Used to snap beats onto the physical attack (PLAN §5 rhythm step 2)."""
    x = np.asarray(x, np.float64).reshape(-1)
    hop = max(1, int(round(sr * hop_s)))
    win = max(hop, int(round(sr * win_s)))
    bands = [x]
    if lowpass_hz:
        from scipy.signal import butter, sosfiltfilt
        sos = butter(2, lowpass_hz / (sr / 2), btype="low", output="sos")
        bands.append(sosfiltfilt(sos, x))
    times_all, rise_all = [], []
    for y in bands:
        c = np.concatenate([[0.0], np.cumsum(y * y)])
        n = (len(y) - win) // hop + 1
        if n <= 12:
            continue
        starts = np.arange(n) * hop
        e = (c[starts + win] - c[starts]) / win
        db = 10 * np.log10(e + 1e-12)
        db = np.maximum(db, -120.0)
        # rise over the previous 10 ms (relative to the minimum there)
        k = max(2, int(round(0.010 / hop_s)))
        prev_min = np.minimum.reduce([np.r_[np.full(j, db[0]), db[:-j]] for j in range(1, k + 1)])
        rise = db - prev_min
        d = np.diff(db, prepend=db[0])
        cand = local_peaks(d, 1.0, int(round(0.020 / hop_s)))
        for i in cand:
            r = float(np.max(rise[i:i + k])) if i + k <= len(rise) else float(rise[i])
            if r >= min_rise_db and db[min(len(db) - 1, i + k)] > -70:
                times_all.append((starts[i] + win / 2) / sr)
                rise_all.append(r)
    if not times_all:
        return Transients(np.zeros(0), np.zeros(0))
    o = np.argsort(times_all)
    return Transients(np.asarray(times_all)[o], np.asarray(rise_all)[o])


def estimate_lag(beats: Sequence[float] | None, tr: "Transients", win: float = 0.04, min_matches: int = 20,
                 thresholds: Sequence[float] = (15.0, 12.0, 9.0)) -> tuple[float | None, int, float | None]:
    """A tracker's systematic latency against the physical attacks: median of (strongest transient within +-win
    minus beat) over its beats, using the strictest rise threshold that still gives min_matches matches.
    Returns (lag_s or None, matches, threshold). On the synthetic song beat_this reads -20 ms (late), allin1 +10 ms,
    madmom 0 ms, exactly the offsets against the ground truth."""
    if beats is None or len(beats) == 0 or len(tr.times) == 0:
        return None, 0, None
    b = np.asarray(beats, float)
    for thr in thresholds:
        sel = tr.rise_db >= thr
        tt, rr = tr.times[sel], tr.rise_db[sel]
        if len(tt) < min_matches:
            continue
        offs = []
        for t in b:
            lo, hi = np.searchsorted(tt, [t - win, t + win])
            if hi > lo:
                j = lo + int(np.argmax(rr[lo:hi]))
                offs.append(tt[j] - t)
        if len(offs) >= min_matches:
            return float(np.clip(np.median(offs), -win, win)), len(offs), float(thr)
    return None, 0, None


def snap_beats(beats: np.ndarray, tr: Transients, window: float = 0.025, min_rise_db: float = 15.0,
               mode: str = "nearest") -> tuple[np.ndarray, np.ndarray]:
    """Move each beat onto a transient within +-window with rise >= min_rise_db: the nearest one (default; the
    trackers are latency-calibrated, so the attack that belongs to the beat is the closest) or the strongest.
    Returns (beats, snapped)."""
    b = np.asarray(beats, float).copy()
    snapped = np.zeros(len(b), bool)
    if len(tr.times) == 0:
        return b, snapped
    sel = tr.rise_db >= min_rise_db
    tt, rr = tr.times[sel], tr.rise_db[sel]
    for i, t in enumerate(b):
        lo, hi = np.searchsorted(tt, [t - window, t + window])
        if hi <= lo:
            continue
        if mode == "strongest":
            j = lo + int(np.argmax(rr[lo:hi]))
        else:
            j = lo + int(np.argmin(np.abs(tt[lo:hi] - t)))
        b[i] = tt[j]
        snapped[i] = True
    # keep monotonic
    for i in range(1, len(b)):
        if b[i] <= b[i - 1] + 0.05:
            b[i] = beats[i]
            snapped[i] = False
    return b, snapped


# ============================================================================================ pulse + virtual grid
def sample_max(x: np.ndarray, t: np.ndarray, fps: float = FPS, win_s: float = 0.04) -> np.ndarray:
    x = np.asarray(x, float)
    w = int(round(win_s * fps))
    out = np.zeros(len(t))
    for i, tt in enumerate(t):
        c = int(round(tt * fps))
        lo, hi = max(0, c - w), min(len(x), c + w + 1)
        out[i] = x[lo:hi].max() if hi > lo else 0.0
    return out


def pulse_flags(beats: np.ndarray, act: np.ndarray, level_db: np.ndarray | None, fps: float = FPS, *,
                rel: float = 0.3, floor: float = 0.08, silence_db: float = -60.0, min_run: int = 2,
                onset_times: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """in_pulse per beat from the fused activation at the beat (median over +-2 beats); a beat whose span is >= 90 %
    below ``silence_db`` and has no attack within +-40 ms is vetoed (digital silence: trackers keep ticking there).
    Returns (flags, evidence)."""
    b = np.asarray(beats, float)
    if len(b) == 0:
        return np.zeros(0, bool), np.zeros(0)
    ev = sample_max(act, b, fps)
    sm = np.array([np.median(ev[max(0, i - 2): i + 3]) for i in range(len(ev))])
    ref = np.percentile(ev, 75) if len(ev) else 0.0
    thr = max(floor, rel * ref)
    flags = sm >= thr
    if level_db is not None and len(level_db):
        ld = np.asarray(level_db, float)
        ends = np.r_[b[1:], b[-1] + (b[-1] - b[-2] if len(b) > 1 else 0.5)]
        for i, (t0, t1) in enumerate(zip(b, ends)):
            lo, hi = int(round(t0 * fps)), max(int(round(t0 * fps)) + 1, int(round(t1 * fps)))
            seg = ld[lo:hi]
            if len(seg) and np.mean(seg < silence_db) >= 0.9:
                has_onset = False
                if onset_times is not None and len(onset_times):
                    j = np.searchsorted(onset_times, t0)
                    has_onset = any(0 <= q < len(onset_times) and abs(onset_times[q] - t0) <= 0.04 for q in (j - 1, j))
                if not has_onset:
                    flags[i] = False
    # remove runs shorter than min_run (flip to the surrounding state)
    if min_run > 1 and len(flags) > 2:
        changed = True
        while changed:
            changed = False
            i = 0
            while i < len(flags):
                j = i
                while j < len(flags) and flags[j] == flags[i]:
                    j += 1
                if j - i < min_run and i > 0 and j < len(flags) and flags[i - 1] == flags[j]:
                    flags[i:j] = flags[i - 1]
                    changed = True
                i = j
    return flags, ev


def regularize_grid(beats: np.ndarray, flags: np.ndarray, duration: float, *, onset_times: np.ndarray | None = None,
                    act: np.ndarray | None = None, fps: float = FPS, beats_per_bar: int = 4,
                    lead_virtual_min_beats: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Make the grid cover the song (D11): uniform virtual beats through internal no-pulse gaps and up to the end;
    leading no-pulse beats are dropped, pickups are recovered backwards where onsets support them, and a long
    beatless intro (>= lead_virtual_min_beats beats) gets virtual beats back to t >= 0.
    Returns (beats, in_pulse)."""
    b = np.asarray(beats, float)
    f = np.asarray(flags, bool)
    if len(b) == 0 or not f.any():
        return b, f
    pulse_idx = np.nonzero(f)[0]
    first, last = int(pulse_idx[0]), int(pulse_idx[-1])
    out_t: list[float] = []
    out_f: list[bool] = []
    # ---------------- leading: pickups + virtual intro
    ibi0 = float(np.median(np.diff(b[first:first + 9]))) if last - first >= 2 else 0.5
    lead: list[tuple[float, bool]] = []
    t = b[first] - ibi0
    onset_ok = True
    while t > 0.02 and onset_ok:
        ok = False
        if onset_times is not None and len(onset_times):
            j = np.searchsorted(onset_times, t)
            near = [onset_times[k] for k in (j - 1, j) if 0 <= k < len(onset_times)]
            ok = any(abs(x - t) <= 0.05 for x in near)
        if not ok and act is not None:
            ok = sample_max(act, np.array([t]), fps, 0.05)[0] >= 0.3
        if ok:
            lead.append((t, True))
            t -= ibi0
        else:
            onset_ok = False
    lead = lead[::-1]
    t0 = lead[0][0] if lead else b[first]
    if t0 / ibi0 >= lead_virtual_min_beats:
        k = int(math.floor(t0 / ibi0 + 1e-9))
        virt = [t0 - j * ibi0 for j in range(k, 0, -1)]
        virt = [x for x in virt if x >= 0.0]
        out_t += virt
        out_f += [False] * len(virt)
    for x, fl in lead:
        out_t.append(x)
        out_f.append(fl)
    # ---------------- body
    i = first
    while i <= last:
        if f[i]:
            out_t.append(float(b[i]))
            out_f.append(True)
            i += 1
            continue
        j = i
        while j <= last and not f[j]:
            j += 1
        # gap between pulse beats i-1 and j
        ta, tb = b[i - 1], b[j]
        loc = np.r_[np.diff(b[max(first, i - 5): i]), np.diff(b[j: j + 5])]
        loc_ibi = float(np.median(loc)) if len(loc) else ibi0
        nint = max(1, int(round((tb - ta) / loc_ibi)))
        for kk in range(1, nint):
            out_t.append(float(ta + kk * (tb - ta) / nint))
            out_f.append(False)
        i = j
    # ---------------- trailing
    ibi1 = float(np.median(np.diff(b[max(first, last - 8): last + 1]))) if last - first >= 2 else ibi0
    t = b[last] + ibi1
    while t < duration - 0.25 * ibi1:
        out_t.append(float(t))
        out_f.append(False)
        t += ibi1
    return np.asarray(out_t), np.asarray(out_f, bool)


# ============================================================================================ downbeats
def votes_on_grid(beats: np.ndarray, downbeats: Sequence[float] | None, tol: float | None = None) -> np.ndarray:
    """1 for each grid beat that has a tracker downbeat within +-tol (default: a quarter of the local IBI, <= 70 ms)."""
    b = np.asarray(beats, float)
    v = np.zeros(len(b))
    if downbeats is None or len(downbeats) == 0 or len(b) == 0:
        return v
    ibi = np.diff(b, append=b[-1] + (b[-1] - b[-2] if len(b) > 1 else 0.5))
    d = np.sort(np.asarray(downbeats, float))
    for t in d:
        i = int(np.argmin(np.abs(b - t)))
        lim = tol if tol is not None else min(0.07, 0.3 * ibi[i])
        if abs(b[i] - t) <= lim:
            v[i] = 1.0
    return v


@dataclass
class MeterPath:
    position: np.ndarray       # beat_in_bar (1..m) per beat
    meter: np.ndarray          # nominal beats per bar per beat
    irregular: np.ndarray      # True for beats in a bar that ended early (break)


def decode_meter(score: np.ndarray, *, meters: Sequence[int] = (3, 4), theta: float | None = None,
                 switch_cost: float = 1.25, break_cost: float = 4.0, meter_bias: Mapping[int, float] | None = None) -> MeterPath:
    """Viterbi over beats: states (meter m, position p). A downbeat (p = 1) on beat i earns score[i] - theta;
    meter switches cost switch_cost x g and bars ending early break_cost x g, where g is the median gain of the
    beats scoring above theta (so the costs scale with the evidence). Any start state is allowed (pickups)."""
    s = np.asarray(score, float)
    n = len(s)
    if n == 0:
        return MeterPath(np.zeros(0, int), np.zeros(0, int), np.zeros(0, bool))
    th = float(np.mean(s) + 0.5 * np.std(s)) if theta is None else theta
    above = s[s > th] - th
    g = float(np.median(above)) if len(above) else 1.0
    switch_cost, break_cost = switch_cost * g, break_cost * g
    bias = dict(meter_bias or {})
    states = [(m, p) for m in meters for p in range(1, m + 1)]
    S = len(states)
    idx = {st: k for k, st in enumerate(states)}
    NEG = -1e18
    dp = np.full((n, S), NEG)
    bp = np.full((n, S), -1, int)
    brk = np.zeros((n, S), bool)
    for k, (m, p) in enumerate(states):
        dp[0, k] = (s[0] - th + bias.get(m, 0.0)) if p == 1 else 0.0
    for i in range(1, n):
        for k, (m, p) in enumerate(states):
            em = (s[i] - th + bias.get(m, 0.0)) if p == 1 else 0.0
            best, arg, isbrk = NEG, -1, False
            if p > 1:
                q = idx[(m, p - 1)]
                if dp[i - 1, q] > best:
                    best, arg = dp[i - 1, q], q
            else:
                for (m2, p2) in states:
                    q = idx[(m2, p2)]
                    c = dp[i - 1, q]
                    if p2 == m2:
                        c -= 0.0 if m2 == m else switch_cost
                        b_ = False
                    elif p2 >= 2:
                        c -= break_cost + (0.0 if m2 == m else switch_cost)
                        b_ = True
                    else:
                        continue
                    if c > best:
                        best, arg, isbrk = c, q, b_
            dp[i, k] = best + em
            bp[i, k] = arg
            brk[i, k] = isbrk
    k = int(np.argmax(dp[-1]))
    pos = np.zeros(n, int)
    met = np.zeros(n, int)
    irr = np.zeros(n, bool)
    for i in range(n - 1, -1, -1):
        m, p = states[k]
        pos[i], met[i] = p, m
        if brk[i, k]:
            irr[i - 1] = True
        k = bp[i, k] if i > 0 else k
    # mark every beat of a bar that ended early
    for i in range(n - 1, -1, -1):
        if irr[i]:
            j = i
            while j >= 0 and pos[j] != 1:
                irr[j] = True
                j -= 1
            if j >= 0:
                irr[j] = True
    return MeterPath(pos, met, irr)


def phase_report(beats: np.ndarray, position: np.ndarray, tracker_db: Mapping[str, Sequence[float] | None]) -> dict[str, dict[str, Any]]:
    """Per tracker: downbeat F against the fused downbeats, and the beat shift (-2..+2) that would maximise it."""
    b = np.asarray(beats, float)
    fused = b[position == 1]
    out: dict[str, dict[str, Any]] = {}
    for k, db in tracker_db.items():
        if db is None or len(db) == 0:
            continue
        v = votes_on_grid(b, db)
        idx = np.nonzero(v)[0]
        res = {}
        for sh in (-2, -1, 0, 1, 2):
            j = idx + sh
            j = j[(j >= 0) & (j < len(b))]
            res[sh] = f_measure(b[j], fused, 0.07)
        best = max(res, key=lambda s: (res[s], -abs(s)))
        out[k] = {"f": round(res[0], 3), "best_shift": int(best), "f_best": round(res[best], 3)}
    return out


# ============================================================================================ tempo segments + feel
def local_bpm(beats: np.ndarray, half: int = 2) -> np.ndarray:
    b = np.asarray(beats, float)
    if len(b) < 2:
        return np.full(len(b), 120.0)
    ibi = np.diff(b)
    out = np.zeros(len(b))
    for i in range(len(b)):
        seg = ibi[max(0, i - half): min(len(ibi), i + half)]
        out[i] = 60.0 / np.median(seg) if len(seg) else 60.0 / ibi[-1]
    return out


def feel_labels(beats: np.ndarray, tracker_beats: Mapping[str, Sequence[float] | None], half_win: int = 8) -> np.ndarray:
    """Per beat: 'normal' | 'half_time' | 'double_time' from the trackers' local tempo relative to the grid
    (majority of the trackers that have beats in the +-half_win window)."""
    b = np.asarray(beats, float)
    n = len(b)
    lab = np.array(["normal"] * n, dtype=object)
    if n < 4:
        return lab
    gl = local_bpm(b, 4)
    tr = {k: np.sort(np.asarray(v, float)) for k, v in tracker_beats.items() if v is not None and len(v) >= 4}
    for i in range(n):
        t0, t1 = b[max(0, i - half_win)], b[min(n - 1, i + half_win)]
        votes = []
        for v in tr.values():
            seg = v[(v >= t0) & (v <= t1)]
            if len(seg) < 4:
                continue
            ibi = np.diff(seg)
            ibi = ibi[ibi > 0.1]
            if not len(ibi):
                continue
            r = (60.0 / np.median(ibi)) / gl[i]
            if abs(r / 0.5 - 1) < 0.12:
                votes.append("half_time")
            elif abs(r / 2.0 - 1) < 0.12:
                votes.append("double_time")
            else:
                votes.append("normal")
        if votes:
            vals, cnt = np.unique(votes, return_counts=True)
            top = vals[np.argmax(cnt)]
            if cnt.max() * 2 > len(votes) and top != "normal":
                lab[i] = top
    # smooth: runs shorter than 8 beats revert to their neighbours
    i = 0
    while i < n:
        j = i
        while j < n and lab[j] == lab[i]:
            j += 1
        if j - i < 8 and lab[i] != "normal":
            lab[i:j] = "normal"
        i = j
    return lab


def tempo_segments(beats: np.ndarray, in_pulse: np.ndarray, feel: np.ndarray, duration: float, *, change: float = 0.04,
                   persist: int = 4) -> list[dict[str, Any]]:
    """Piecewise tempo grid: new segment when the local tempo moves > change for >= persist beats, or the feel
    changes. Covers [0, duration)."""
    b = np.asarray(beats, float)
    n = len(b)
    if n < 2:
        return [{"t": 0.0, "d": float(duration), "bpm": 120.0, "stable": False, "feel": "normal"}]
    lb = local_bpm(b, 2)
    bounds = [0]
    ref = lb[0]
    i = 1
    while i < n:
        if feel[i] != feel[bounds[-1]]:
            bounds.append(i)
            ref = lb[i]
            i += 1
            continue
        if abs(lb[i] / ref - 1) > change:
            j = i
            while j < n and abs(lb[j] / ref - 1) > change and feel[j] == feel[bounds[-1]]:
                j += 1
            if j - i >= persist:
                bounds.append(i)
                ref = float(np.median(lb[i:j]))
                i = j
                continue
        i += 1
    segs = []
    for k, s in enumerate(bounds):
        e = bounds[k + 1] if k + 1 < len(bounds) else n
        sel = np.arange(s, e)
        selp = sel[np.asarray(in_pulse, bool)[sel]] if np.asarray(in_pulse, bool)[sel].any() else sel
        ibis = np.diff(b[max(0, selp[0]): selp[-1] + 2]) if len(selp) else np.diff(b)
        bpm = float(60.0 / np.median(ibis)) if len(ibis) else float(lb[s])
        spread = (np.percentile(lb[selp], 90) - np.percentile(lb[selp], 10)) / max(bpm, 1e-6) if len(selp) else 1.0
        t0 = 0.0 if k == 0 else float(b[s])
        t1 = float(duration) if k + 1 == len(bounds) else float(b[bounds[k + 1]])
        if t1 - t0 <= 1e-6:
            continue
        segs.append({"t": round(t0, 6), "d": round(t1 - t0, 6), "bpm": round(bpm, 3), "stable": bool(spread < 0.03),
                     "feel": str(feel[s])})
    # merge neighbours with equal feel and tempo within 1.5 %
    merged: list[dict[str, Any]] = []
    for sgm in segs:
        if merged and merged[-1]["feel"] == sgm["feel"] and abs(merged[-1]["bpm"] / sgm["bpm"] - 1) < 0.015:
            m = merged[-1]
            tot = m["d"] + sgm["d"]
            m["bpm"] = round((m["bpm"] * m["d"] + sgm["bpm"] * sgm["d"]) / tot, 3)
            m["d"] = round(sgm["t"] + sgm["d"] - m["t"], 6)
            m["stable"] = m["stable"] and sgm["stable"]
        else:
            merged.append(dict(sgm))
    return merged


@dataclass
class Bars:
    beats: list[dict[str, Any]] = field(default_factory=list)
    bars: list[dict[str, Any]] = field(default_factory=list)
    changes: list[dict[str, Any]] = field(default_factory=list)


def build_bars(beats: np.ndarray, mp: MeterPath, in_pulse: np.ndarray, strength: np.ndarray, beat_conf: np.ndarray,
               bar_conf: Mapping[int, float], duration: float) -> Bars:
    """events/beats.json and events/bars.json items from the decoded meter path (D12: pickup = bar 0)."""
    b = np.asarray(beats, float)
    n = len(b)
    out = Bars()
    if n == 0:
        return out
    first_db = next((i for i in range(n) if mp.position[i] == 1), n)
    bar_of = np.zeros(n, int)
    bar = 0
    for i in range(n):
        if mp.position[i] == 1 and i >= first_db:
            bar += 1
        bar_of[i] = bar if i >= first_db else 0
    # nominal meter per bar: the meter state of its first beat (pickup: that of bar 1)
    nominal: dict[int, int] = {}
    for i in range(n):
        nominal.setdefault(int(bar_of[i]), int(mp.meter[i] if bar_of[i] > 0 else (mp.meter[first_db] if first_db < n else mp.meter[i])))
    for i in range(n):
        bb = int(bar_of[i])
        bib = int(mp.position[i])
        nb = nominal[bb]
        out.beats.append({"beat_index": i, "t": round(float(b[i]), 6), "bar": bb, "beat_in_bar": max(1, min(bib, nb)),
                          "beats_in_bar": nb, "in_pulse": bool(in_pulse[i]), "strength": round(float(strength[i]), 4),
                          "conf": round(float(beat_conf[i]), 4)})
    starts: dict[int, int] = {}
    for i in range(n):
        starts.setdefault(int(bar_of[i]), i)
    keys = sorted(starts)
    prev_m = None
    for k, bb in enumerate(keys):
        s = starts[bb]
        e = starts[keys[k + 1]] if k + 1 < len(keys) else n
        t0 = float(b[s])
        t1 = float(b[e]) if e < n else min(float(duration), float(b[-1] + (b[-1] - b[-2] if n > 1 else 0.5)))
        if t1 <= t0:
            t1 = t0 + 1e-3
        ip = np.asarray(in_pulse[s:e], bool)
        item = {"bar": bb, "t": round(t0, 6), "d": round(t1 - t0, 6), "beats_in_bar": nominal[bb], "n_beats": int(e - s),
                "first_beat": int(s), "pickup": bb == 0, "in_pulse": bool(ip.mean() >= 0.5) if len(ip) else False,
                "conf": round(float(bar_conf.get(bb, 0.5)), 4)}
        if bool(mp.irregular[s]) or (bb > 0 and e - s != nominal[bb] and e < n):
            item["irregular"] = True
        out.bars.append(item)
        if bb > 0:
            if prev_m is not None and nominal[bb] != prev_m:
                out.changes.append({"t": round(t0, 6), "bar": bb, "beats_per_bar": nominal[bb]})
            prev_m = nominal[bb]
    return out
