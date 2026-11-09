"""Offline, non-causal port of the analysis in ``viz/js/audio.js`` (pure numpy/scipy; no I/O).

What is ported **faithfully** (same constants, same formulas, same order of operations):
* the AnalyserNode front end: Web Audio periodic Blackman window (alpha 0.16), ``|X| / N`` magnitudes, per-bin dB
  ``20 log10(|X| / N)`` floored at -200, on the mono down-mix ``0.5 (L + R)``; ``frequencyBinCount = N / 2``;
* the 128-band log map (32 Hz..16 kHz, mean of per-bin dB for wide bands, linear interpolation in dB for bands
  narrower than one bin), the 2.6 dB/oct tilt, the -88..-18 dB range, the soft knee ``v / (1 + 0.18 v)``;
* the band smoothing (22 ms attack / 110 ms release), the bass/mid/high energies (30 ms / 140 ms), ``level``;
* ``_hitEnvelope`` (8 ms / 90 ms followers, the attack-size reference, threshold 0.35, smoothstep, the -46 dB kick
  gate on the raw kick band power, one hit per note with the 4 dB re-arm, 0.18 s release);
* per-band spectral flux on the normalised bands with the viz ranges, multipliers (1.55 / 1.7), floor 0.012,
  refractory gaps (0.16 / 0.12 / 0.08 s), energy gates and strength formulas.

What is **offline** (PLAN §5 spectral; documented in provenance):
* frames are centred (frame i covers samples [c - N/2, c + N/2) with c = round(i * sr / 100)) at a fixed 100 Hz;
* a per-song gain replaces the 6 s AGC: ``g = clamp(0.95 / max(p99.5(max_k raw_k), 0.2), 0.6, 3.5)``;
* the hit reference is the centred +-8 s median of the attack sizes (instead of the causal running average), and the
  kick gate is relative: ``max(-46, p95(kick dB) - 30)``;
* mid/high hit events are the viz hits (an attack whose envelope exceeded 0.3 while armed) refined on a 400 Hz
  zero-phase band envelope; kick events are low-band onsets judged on kick evidence (a swept attack or an acoustic body,
  :func:`select_kick_events`); the hit envelopes are shifted earlier by the median detection lag so their flash lands on
  the onset frame (contract flash rule);
* the flux threshold is a centred mean (0.8 s, current frame excluded) instead of the trailing 48-frame history; onset
  times are refined on the same 400 Hz envelopes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ------------------------------------------------------------------------------------------------ viz constants
NUM_BANDS = 128
F_MIN = 32.0
F_MAX = 16000.0
MIN_DB = -88.0
MAX_DB = -18.0
DB_RANGE = MAX_DB - MIN_DB
TILT_DB_PER_OCT = 2.6
VIZ_FFT_SIZE = 2048
HIT_THRESHOLD = 0.35
HIT_RELEASE = 0.18
KICK_GATE_DB = -46.0
HIT_FLOOR = 0.05
REF_FLOOR = 0.075
REARM_DB = 4.0
RATE = 100
DT = 1.0 / RATE
DB_FLOOR = -120.0

VIZ_BANDS = {"bass": (32.0, 150.0), "mid": (150.0, 2200.0), "high": (2200.0, 16000.0)}
KICK_BAND = (35.0, 100.0)
FINE_BANDS = {
    "sub": (20.0, 60.0),
    "bass": (60.0, 150.0),
    "lowmid": (150.0, 500.0),
    "mid": (500.0, 2000.0),
    "highmid": (2000.0, 4000.0),
    "presence": (4000.0, 6000.0),
    "air": (6000.0, 16000.0),
}
#: viz flux ranges (Hz): bass onsets use 32-260 Hz, mid 300-2200 Hz, high 2500-14000 Hz
FLUX_RANGES = {"bass": (32.0, 260.0), "mid": (300.0, 2200.0), "high": (2500.0, 14000.0)}
FLUX_MULT = {"bass": 1.55, "mid": 1.7, "high": 1.7}
FLUX_FLOOR = 0.012
ONSET_GAP_S = {"bass": 0.16, "mid": 0.12, "high": 0.08}
ONSET_ENERGY_GATE = {"bass": 0.08, "mid": 0.06, "high": 0.05}
#: viz strength = clamp(base + (f - thr) / (thr + 1e-4) * 0.3, base, 1); offline strength s = (viz - base) / (1 - base)
ONSET_STRENGTH_BASE = {"bass": 0.55, "mid": 0.6, "high": 0.6}
#: band edges (Hz) of the 400 Hz refinement envelopes (None = no low/high cut); kick hits and bass onsets use "low"
REFINE_BANDS = {
    "low": (None, 400.0),
    "mid": (150.0, 2200.0),
    "high": (2200.0, None),
    "click": (1000.0, None),
}


def clamp(v, a, b):
    return np.minimum(np.maximum(v, a), b)


def smoothstep01(x):
    x = clamp(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def js_round(x: float) -> int:
    """JavaScript Math.round (half up)."""
    return int(math.floor(x + 0.5))


# ------------------------------------------------------------------------------------------------ framing
def fft_size(sr: int) -> int:
    """viz uses a 2048-point analyser (43-46 ms at 44.1/48 kHz); keep that duration at higher rates."""
    k = max(0, round(math.log2(max(sr, 1) / 48000.0)))
    return VIZ_FFT_SIZE * (2**k)


def n_frames(n_samples: int, sr: int, rate: int = RATE) -> int:
    return -(-n_samples * rate // sr)


def frame_centres(n_samples: int, sr: int, rate: int = RATE) -> np.ndarray:
    i = np.arange(n_frames(n_samples, sr, rate), dtype=np.int64)
    return (i * sr * 2 + rate) // (2 * rate)


def webaudio_blackman(n: int) -> np.ndarray:
    """Web Audio AnalyserNode window: a0 - a1 cos(2 pi i / N) + a2 cos(4 pi i / N), alpha = 0.16 (periodic)."""
    a = 0.16
    a0, a1, a2 = (1 - a) / 2, 0.5, a / 2
    i = np.arange(n)
    return a0 - a1 * np.cos(2 * np.pi * i / n) + a2 * np.cos(4 * np.pi * i / n)


# ------------------------------------------------------------------------------------------------ band map
@dataclass
class BandMap:
    sr: int
    n_fft: int
    lo: np.ndarray  # band low edge in bins
    hi: np.ndarray
    centre: np.ndarray
    tilt: np.ndarray
    edges_hz: np.ndarray
    centres_hz: np.ndarray
    ranges: dict[str, tuple[int, int]]
    kick_bins: tuple[int, int]
    weights: np.ndarray  # [128, nb] linear map from per-bin dB to band dB (viz rule)

    @property
    def nb(self) -> int:
        return self.n_fft // 2


def band_map(sr: int, n_fft: int) -> BandMap:
    """viz ``_computeBandMap`` for a given sample rate and FFT size."""
    bin_w = sr / n_fft
    ratio = F_MAX / F_MIN
    k = np.arange(NUM_BANDS)
    f0 = F_MIN * ratio ** (k / NUM_BANDS)
    f1 = F_MIN * ratio ** ((k + 1) / NUM_BANDS)
    fc = np.sqrt(f0 * f1)
    nb = n_fft // 2
    W = np.zeros((NUM_BANDS, nb), np.float64)
    lo, hi, c = f0 / bin_w, f1 / bin_w, fc / bin_w
    for b in range(NUM_BANDS):
        if hi[b] - lo[b] < 1.0:
            i = min(nb - 2, max(0, int(math.floor(c[b]))))
            f = float(np.clip(c[b] - i, 0.0, 1.0))
            W[b, i] += 1.0 - f
            W[b, i + 1] += f
        else:
            i0, i1 = int(math.floor(lo[b])), min(nb, int(math.ceil(hi[b])))
            if i1 > i0:
                W[b, i0:i1] = 1.0 / (i1 - i0)

    def idx(f: float) -> int:
        return int(np.clip(js_round(math.log(f / F_MIN) / math.log(ratio) * NUM_BANDS), 0, NUM_BANDS - 1))

    ranges = {
        "bass": (idx(32), idx(150)),
        "kick": (idx(35), idx(100)),
        "mid": (idx(150), idx(2200)),
        "high": (idx(2200), idx(16000)),
        "flux_bass": (idx(32), idx(260)),
        "flux_mid": (idx(300), idx(2200)),
        "flux_high": (idx(2500), idx(14000)),
    }
    i0 = max(1, int(math.ceil(35 / bin_w)))
    i1 = max(i0, int(math.floor(100 / bin_w)))
    edges = F_MIN * ratio ** (np.arange(NUM_BANDS + 1) / NUM_BANDS)
    return BandMap(sr, n_fft, lo, hi, c, TILT_DB_PER_OCT * np.log2(fc / F_MIN), edges, fc, ranges, (i0, i1), W)


def viz_band_db(d: np.ndarray, bm: BandMap) -> np.ndarray:
    """viz raw band dB (before tilt) from AnalyserNode per-bin dB ``d`` [frames, N/2]: the mean (or the in-dB
    interpolation) of the bins, then ``if (!(db > -200)) db = -200`` on the band, as viz does. ``d`` holds the
    unfloored bin dB (exact zeros as -1000, standing in for the analyser's -Infinity)."""
    return np.maximum(d @ bm.weights.T, -200.0)


def kick_band_db(d: np.ndarray, bm: BandMap) -> np.ndarray:
    """viz kick band: 10 log10 of the mean bin power over the kick bins (bins at -200 dB contribute 0), -200 when
    silent."""
    k0, k1 = bm.kick_bins
    seg = d[:, k0 : k1 + 1]
    pw = np.where(seg > -200.0, 10.0 ** (seg / 10.0), 0.0).sum(axis=1) / (k1 - k0 + 1)
    with np.errstate(divide="ignore"):
        return np.where(pw > 0, 10.0 * np.log10(np.maximum(pw, 1e-300)), -200.0)


# ------------------------------------------------------------------------------------------------ STFT pass
@dataclass
class Frames:
    """Everything the stage needs from one centred STFT pass (reduced per chunk; the spectrogram is not kept)."""

    sr: int
    n_samples: int
    n_fft: int
    t: np.ndarray
    viz_db: np.ndarray  # [n, 128] viz band dB (mean of per-bin AnalyserNode dB), no tilt
    kick_viz_db: np.ndarray  # [n] viz kick band power dB (mean power of the kick bins)
    phys_db: dict[str, np.ndarray]  # band powers in dBFS (mean square, mid + side)
    log_band_db: np.ndarray  # [n, 128] physical power per log band (dBFS per band, for the slope)
    centroid_hz: np.ndarray
    rolloff_hz: np.ndarray
    flatness: np.ndarray
    rms_mono: np.ndarray  # rectangular RMS of the mono frame (viz level)
    width: np.ndarray
    balance: np.ndarray
    correlation: np.ndarray
    total_ms: np.ndarray  # broadband mean-square power (mid + side) of the frame


def _db(p, floor: float = DB_FLOOR):
    with np.errstate(divide="ignore", invalid="ignore"):
        d = 10.0 * np.log10(p)
    return np.maximum(np.nan_to_num(d, nan=floor, neginf=floor, posinf=-floor), floor)


def analyse_frames(x: np.ndarray, sr: int, *, chunk: int = 512) -> Frames:
    """One centred STFT pass over a [ch, n] float signal (mono is duplicated; > 2 channels use the first two)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[None, :]
    L = x[0]
    R = x[1] if x.shape[0] > 1 else x[0]
    n = L.size
    N = fft_size(sr)
    bm = band_map(sr, N)
    centres = frame_centres(n, sr)
    nf = centres.size
    half = N // 2
    mid = 0.5 * (L + R)
    side = 0.5 * (L - R)
    pm = np.pad(mid, (half, half + 1))
    ps = np.pad(side, (half, half + 1))
    w = webaudio_blackman(N)
    nb_full = N // 2 + 1
    freqs = np.arange(nb_full) * sr / N
    # Parseval: mean square of the windowed frame = (|X0|^2 + 2 sum|Xk|^2 + |XN/2|^2) / (N sum w^2)
    pscale = np.full(nb_full, 2.0 / (N * np.sum(w * w)))
    pscale[0] /= 2.0
    pscale[-1] /= 2.0
    nyq = sr / 2.0

    def band_mask(lo: float, hi: float) -> np.ndarray:
        return (freqs >= lo) & (freqs < min(hi, nyq + 1e-9))

    phys_bands = {f"bands.{k}": v for k, v in VIZ_BANDS.items()}
    phys_bands["bands.kick"] = KICK_BAND
    phys_bands.update({f"fine.{k}": v for k, v in FINE_BANDS.items()})
    Wp = np.stack([band_mask(*v).astype(np.float64) for v in phys_bands.values()], axis=1)  # [bins, nbands]
    # physical log bands: mean power per bin inside each viz log band (power spectral density per bin, dB)
    Wl = np.zeros((nb_full, NUM_BANDS))
    Wl[: bm.nb, :] = bm.weights.T
    shape_m = (freqs >= 20.0) & (freqs < min(20000.0, nyq))
    f_shape = freqs[shape_m]
    viz_db = np.empty((nf, NUM_BANDS), np.float32)
    kick_viz = np.empty(nf, np.float64)
    phys = np.empty((nf, Wp.shape[1]), np.float64)
    logb = np.empty((nf, NUM_BANDS), np.float32)
    cen = np.empty(nf)
    roll = np.empty(nf)
    flat = np.empty(nf)
    tot = np.empty(nf)
    ar = np.arange(N)
    for s in range(0, nf, chunk):
        c = centres[s : s + chunk]
        idx = c[:, None] + ar[None, :]
        Xm = np.fft.rfft(pm[idx] * w, axis=1)
        Xs = np.fft.rfft(ps[idx] * w, axis=1)
        pm2 = Xm.real**2 + Xm.imag**2
        ps2 = Xs.real**2 + Xs.imag**2
        # AnalyserNode dB of the mono down-mix (bins 0 .. N/2 - 1)
        with np.errstate(divide="ignore"):
            d = 10.0 * np.log10(pm2[:, : bm.nb] / (N * N))
        d = np.maximum(np.nan_to_num(d, neginf=-1000.0), -1000.0)
        viz_db[s : s + chunk] = viz_band_db(d, bm)
        kick_viz[s : s + chunk] = kick_band_db(d, bm)
        P = (pm2 + ps2) * pscale[None, :]  # mean-square power per bin (mid + side = mean over L/R)
        phys[s : s + chunk] = P @ Wp
        logb[s : s + chunk] = _db(P @ Wl)
        tot[s : s + chunk] = P.sum(axis=1)
        Ps = P[:, shape_m]
        st = Ps.sum(axis=1)
        live = st > 1e-14
        cen[s : s + chunk] = np.where(live, (Ps @ f_shape) / np.maximum(st, 1e-300), 0.0)
        cs = np.cumsum(Ps, axis=1)
        ri = np.argmax(cs >= 0.85 * cs[:, -1:], axis=1)
        roll[s : s + chunk] = np.where(live, f_shape[ri], 0.0)
        lg = np.log(Ps + 1e-20)
        flat[s : s + chunk] = np.where(live, np.exp(lg.mean(axis=1)) / np.maximum(Ps.mean(axis=1), 1e-300), 0.0)

    # time-domain features over the same centred window (rectangular)
    def wsum(z: np.ndarray) -> np.ndarray:
        cs = np.concatenate([[0.0], np.cumsum(z)])
        a = np.clip(centres - half, 0, n)
        b = np.clip(centres + half, 0, n)
        return cs[b] - cs[a]

    sm = wsum(mid * mid)
    sl, sr_, slr = wsum(L * L), wsum(R * R), wsum(L * R)
    ss = wsum(side * side)
    rms_mono = np.sqrt(np.maximum(sm, 0.0) / N)
    live = (sl + sr_) > 1e-12 * N
    width = np.where(live, ss / np.maximum(sm + ss, 1e-300), 0.0)
    balance = np.where(live, (sr_ - sl) / np.maximum(sl + sr_, 1e-300), 0.0)
    corr = np.where(live, slr / np.sqrt(np.maximum(sl * sr_, 1e-300)), 1.0)
    return Frames(
        sr=sr,
        n_samples=n,
        n_fft=N,
        t=np.arange(nf) / RATE,
        viz_db=viz_db,
        kick_viz_db=kick_viz,
        phys_db={k: _db(phys[:, j]) for j, k in enumerate(phys_bands)},
        log_band_db=logb,
        centroid_hz=cen,
        rolloff_hz=roll,
        flatness=np.clip(flat, 0.0, 1.0),
        rms_mono=rms_mono,
        width=np.clip(width, 0.0, 1.0),
        balance=np.clip(balance, -1.0, 1.0),
        correlation=np.clip(corr, -1.0, 1.0),
        total_ms=tot,
    )


def spectral_slope(log_band_db: np.ndarray, centres_hz: np.ndarray, lo: float = 100.0, hi: float = 10000.0,
                   live: np.ndarray | None = None) -> np.ndarray:
    """Least-squares slope of band dB vs log2(f) over the log bands in [lo, hi] (dB/oct); silent frames read 0."""
    m = (centres_hz >= lo) & (centres_hz <= hi)
    xo = np.log2(centres_hz[m])
    xo = xo - xo.mean()
    y = log_band_db[:, m].astype(np.float64)
    s = (y - y.mean(axis=1, keepdims=True)) @ xo / np.sum(xo * xo)
    if live is not None:
        s = np.where(live, s, 0.0)
    return np.clip(s, -30.0, 10.0)


# ------------------------------------------------------------------------------------------------ viz values
def per_song_gain(bands_raw: np.ndarray, pct: float = 99.5) -> float:
    """Offline stand-in for the viz AGC: the gain that puts the p99.5 of the per-frame band maximum at 0.95."""
    pk = float(np.percentile(bands_raw.max(axis=1), pct)) if bands_raw.size else 0.0
    return float(np.clip(0.95 / max(pk, 0.2), 0.6, 3.5))


def asym_smooth(v: np.ndarray, attack_s: float, release_s: float, dt: float = DT, init: float | np.ndarray = 0.0) -> np.ndarray:
    """viz one-pole smoother with separate attack/release (``p + (v - p) * (v > p ? aA : aR)``), along axis 0."""
    aA = 1.0 - math.exp(-dt / attack_s)
    aR = 1.0 - math.exp(-dt / release_s)
    out = np.empty_like(v, dtype=np.float64)
    p = np.zeros(v.shape[1:]) + init
    for i in range(v.shape[0]):
        x = v[i]
        p = p + (x - p) * np.where(x > p, aA, aR)
        out[i] = p
    return out


@dataclass
class VizValues:
    gain: float
    bands_raw: np.ndarray  # [n, 128] (tilted, mapped, before gain)
    norm: np.ndarray  # [n, 128] normalised (gain + soft knee), unsmoothed
    bands: np.ndarray  # [n, 128] smoothed (viz audio.bands; spectrum128 = round(255 * bands))
    energy: dict[str, np.ndarray]  # unsmoothed eBass/eMid/eHigh
    smooth: dict[str, np.ndarray]  # audio.bass / mid / high
    level: np.ndarray
    kick_e: np.ndarray  # eKick (raw kick band power mapped to 0..)


def viz_values(fr: Frames, bm: BandMap | None = None) -> VizValues:
    bm = bm or band_map(fr.sr, fr.n_fft)
    raw = (fr.viz_db.astype(np.float64) + bm.tilt[None, :] - MIN_DB) / DB_RANGE
    raw = np.maximum(raw, 0.0)
    g = per_song_gain(raw)
    v = raw * g
    norm = np.minimum(v / (1.0 + 0.18 * v), 1.0)
    bands = asym_smooth(norm, 0.022, 0.11)
    energy = {}
    smooth = {}
    for b in ("bass", "mid", "high"):
        a, z = bm.ranges[b]
        energy[b] = norm[:, a : z + 1].mean(axis=1)
        smooth[b] = asym_smooth(energy[b][:, None], 0.03, 0.14)[:, 0]
    lv = fr.rms_mono * g * 2.2
    lv = lv / (1.0 + 0.3 * lv)
    level = asym_smooth(lv[:, None], 0.03, 0.14)[:, 0]
    kick_e = np.maximum(0.0, (fr.kick_viz_db + 2.0 - MIN_DB) / DB_RANGE)
    return VizValues(g, raw, norm, bands, energy, smooth, level, kick_e)


# ------------------------------------------------------------------------------------------------ hit envelope
@dataclass
class Episode:
    """One attack of the viz follower pair (rise grows, then falls below half its maximum)."""

    i_start: int  # first frame with rise > 0
    i_peak: int  # frame of the largest gated rise / reference
    i_end: int  # frame where the attack ended
    x: float  # peak gated rise / reference ("1 ~ a typical attack")
    v_free: float  # peak envelope value without the one-hit-per-note arming (0..1)
    v_armed: float  # peak envelope value with arming (the value viz shows)
    viz_hit: bool  # viz registered a hit (v_armed > 0.3 while armed)


@dataclass
class HitResult:
    raw: np.ndarray  # viz raw envelope (with arming)
    free: np.ndarray  # raw envelope without arming
    released: np.ndarray
    rise: np.ndarray
    fast: np.ndarray
    ref: np.ndarray
    gate: np.ndarray
    episodes: list[Episode] = field(default_factory=list)
    attacks: int = 0
    gate_db: float | None = None

    @property
    def viz_hits(self) -> list[Episode]:
        return [e for e in self.episodes if e.viz_hit]


def _one_pole(e: np.ndarray, tau: float, dt: float) -> np.ndarray:
    from scipy.signal import lfilter

    a = 1.0 - math.exp(-dt / tau)
    if e.size == 0:
        return e.copy()
    y, _ = lfilter([a], [1.0, -(1.0 - a)], e, zi=[(1.0 - a) * e[0]])
    return y


def centred_median_ref(times: np.ndarray, sizes: np.ndarray, n: int, half_s: float, *, rate: int = RATE,
                       floor: float = REF_FLOOR, grid_s: float = 0.1) -> np.ndarray:
    """Per-frame reference = median of the attack sizes within +-half_s (centred), computed on a 10 Hz grid and held;
    windows with fewer than 3 attacks use the song median."""
    if sizes.size == 0:
        return np.full(n, 0.2)
    order = np.argsort(times, kind="stable")
    times, sizes = times[order], sizes[order]
    glob = float(np.median(sizes))
    step = max(1, int(round(grid_s * rate)))
    gi = np.arange(0, n, step)
    lo = np.searchsorted(times, (gi - half_s * rate) / rate, side="left")
    hi = np.searchsorted(times, (gi + half_s * rate) / rate, side="right")
    g = np.array([float(np.median(sizes[a:b])) if b - a >= 3 else glob for a, b in zip(lo, hi)])
    ref = np.repeat(g, step)[:n]
    return np.maximum(floor, ref)


def hit_envelope(e: np.ndarray, *, gate_db: float | None = None, threshold: float = HIT_THRESHOLD,
                 release_s: float = HIT_RELEASE, hit_floor: float = HIT_FLOOR, ref_floor: float = REF_FLOOR,
                 rearm_db: float = REARM_DB, median_ref_s: float | None = 8.0, dt: float = DT) -> HitResult:
    """viz ``_hitEnvelope`` over a whole band-energy series ``e`` (0..1 scale of the viz dB map).

    median_ref_s None reproduces the causal viz reference (running average of attack sizes); a number uses the offline
    centred median of the attack sizes within +-median_ref_s. Every attack episode is returned (with and without the
    viz arming) so the stage can pick events offline."""
    e = np.asarray(e, dtype=np.float64)
    n = e.size
    fast = _one_pole(e, 0.008, dt)
    slow = _one_pole(e, 0.09, dt)
    rise = np.maximum(0.0, fast - slow)
    if gate_db is not None:
        level_db = fast * DB_RANGE + MIN_DB - 2.0
        gate = smoothstep01((level_db - (gate_db - 3.0)) / 6.0)
    else:
        gate = np.ones(n)
    # pass 1: attack episodes (independent of the reference)
    ended = np.zeros(n, bool)
    a_t: list[float] = []
    a_s: list[float] = []
    cur = 0.0
    ipk = 0
    for i in range(n):
        r = rise[i]
        if r > cur:
            cur = r
            ipk = i
        elif cur > 0 and r < cur * 0.5:
            if cur > hit_floor:
                a_t.append(ipk / RATE)
                a_s.append(cur)
            cur = 0.0
            ended[i] = True
    if median_ref_s is not None:
        ref = centred_median_ref(np.array(a_t), np.array(a_s), n, median_ref_s, floor=ref_floor)
    else:
        ref = np.empty(n)
        r_ = 0.2
        cur = 0.0
        k = math.exp(-dt / 20.0)
        for i in range(n):
            r = rise[i]
            if r > cur:
                cur = r
            elif cur > 0 and r < cur * 0.5:
                if cur > hit_floor:
                    r_ += (cur - r_) * (0.3 if cur < r_ else 0.12)
                cur = 0.0
            r_ = max(ref_floor, r_ * k)
            ref[i] = r_
    # pass 2: the envelope with arming (one hit per note), and every episode
    thr = min(max(threshold, 0.0), 0.95)
    x = rise / ref
    xg = x * gate
    v_all = smoothstep01((x - thr) / (1.15 - thr)) * gate
    raw = np.zeros(n)
    episodes: list[Episode] = []
    armed = True
    hit_level = 0.0
    min_since = 0.0
    attack_v = 0.0
    attack_level = 0.0
    a_start = -1
    a_ix = 0
    a_x = 0.0
    a_vf = 0.0
    rearm = rearm_db / DB_RANGE
    for i in range(n):
        v = v_all[i]
        f = fast[i]
        if a_start < 0 and rise[i] > 0:
            a_start = i
        if xg[i] > a_x:
            a_x = xg[i]
            a_ix = i
        if v > a_vf:
            a_vf = v
        min_since = min(min_since, f)
        if not armed and (hit_level - min_since > rearm or x[i] > 2.2):
            armed = True
        if not armed:
            v = 0.0
        if v > attack_v:
            attack_v = v
        if f > attack_level:
            attack_level = f
        if ended[i]:
            hit = attack_v > 0.3 and armed
            if hit:
                armed = False
                hit_level = attack_level
                min_since = f
            if a_x > 0:
                episodes.append(Episode(max(a_start, 0), a_ix, i, float(a_x), float(a_vf), float(attack_v), bool(hit)))
            attack_v = 0.0
            attack_level = f
            a_start, a_x, a_vf = -1, 0.0, 0.0
        raw[i] = v
    released = release(raw, release_s, dt)
    return HitResult(raw, v_all, released, rise, fast, ref, gate, episodes, len(a_s), gate_db)


def release(raw: np.ndarray, release_s: float = HIT_RELEASE, dt: float = DT) -> np.ndarray:
    """viz: ``v > prev ? v : prev + (v - prev) * (1 - exp(-dt / hitRelease))``."""
    a = 1.0 - math.exp(-dt / release_s)
    out = np.empty_like(raw)
    p = 0.0
    for i in range(raw.size):
        v = raw[i]
        p = v if v > p else p + (v - p) * a
        out[i] = p
    return out


# ------------------------------------------------------------------------------------------------ 400 Hz envelopes
ENV_RATE = 400


def band_envelope(mono: np.ndarray, sr: int, lo: float | None, hi: float | None, rate: int = ENV_RATE) -> np.ndarray:
    """Zero-phase band envelope at ``rate`` Hz (sample j centred at j / rate): Butterworth filter applied forwards and
    backwards (sosfiltfilt) after a zero-phase polyphase decimation, Hilbert magnitude for bands up to 2.2 kHz (power
    otherwise), RMS over each 1 / rate window."""
    from scipy import signal

    x = np.asarray(mono, dtype=np.float64)
    n = x.size
    top = hi if hi is not None else min(16000.0, 0.45 * sr)
    q = max(1, int(sr // (4.0 * top)))
    if q > 1:
        x = signal.resample_poly(x, 1, q)
    fs = sr / q
    nyq = fs / 2.0
    lo_ = lo if lo is not None and lo > 0 else None
    hi_ = hi if hi is not None and hi < 0.95 * nyq else None
    if lo_ and hi_:
        sos = signal.butter(4, [lo_, hi_], btype="bandpass", fs=fs, output="sos")
    elif lo_:
        sos = signal.butter(4, lo_, btype="highpass", fs=fs, output="sos")
    elif hi_:
        sos = signal.butter(4, hi_, btype="lowpass", fs=fs, output="sos")
    else:
        sos = None
    y = signal.sosfiltfilt(sos, x) if sos is not None else x
    if top <= 2200.0:
        m = signal.hilbert(y, N=_fast_len(y.size))[: y.size]
        a2 = m.real**2 + m.imag**2
    else:
        a2 = y * y
    cs = np.concatenate([[0.0], np.cumsum(a2)])
    nj = int(math.ceil(n * rate / sr))
    tc = np.arange(nj) / rate
    a = np.clip(np.round((tc - 0.5 / rate) * fs).astype(np.int64), 0, a2.size)
    b = np.clip(np.round((tc + 0.5 / rate) * fs).astype(np.int64), 0, a2.size)
    ms = (cs[b] - cs[a]) / np.maximum(b - a, 1)
    return np.sqrt(np.maximum(ms, 0.0))


def _fast_len(n: int) -> int:
    from scipy import fft as sfft

    return int(sfft.next_fast_len(n))


def env_db(env: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(env, 1e-7))


def step_contrast(edb: np.ndarray, k: int) -> np.ndarray:
    """s[j] = mean(edb[j+1 .. j+k]) - mean(edb[j-k+1 .. j]): the dB step between samples j and j+1, measured with
    k-sample boxes on each side so ripple (beating partials) does not look like an onset."""
    n = edb.size
    c = np.concatenate([[0.0], np.cumsum(edb)])
    j = np.arange(n)
    a, b = np.clip(j - k + 1, 0, n), np.clip(j + 1, 0, n)
    pre = (c[b] - c[a]) / np.maximum(b - a, 1)
    a2, b2 = np.clip(j + 1, 0, n), np.clip(j + 1 + k, 0, n)
    post = np.where(b2 > a2, (c[b2] - c[a2]) / np.maximum(b2 - a2, 1), pre)
    return post - pre


#: box lengths (400 Hz samples) of the step contrast per refinement envelope: 10 ms for the low band, 5 ms above
STEP_K = {"low": 4, "mid": 2, "high": 2, "click": 2}
#: weight of the >= 1 kHz "click" step added to the band's own step (a drum attack is broadband)
CLICK_W = {"low": 0.5, "mid": 0.5, "high": 0.0}


def onset_score(envs_db: dict[str, np.ndarray], band: str) -> np.ndarray:
    s = step_contrast(envs_db[band], STEP_K[band])
    w = CLICK_W.get(band, 0.0)
    if w and "click" in envs_db:
        s = s + w * step_contrast(envs_db["click"], STEP_K["click"])
    return s


def refine_onset(score: np.ndarray, edb: np.ndarray, t_lo: float, t_hi: float, *, rate: int = ENV_RATE,
                 peak_after_s: float = 0.06, gate: np.ndarray | None = None,
                 gate_frac: float = 0.5) -> tuple[float, float, float] | None:
    """Onset in [t_lo, t_hi]: the maximum of the onset score (a dB step between two 400 Hz samples; the onset is the
    midpoint of that step). Returns (t, t_peak, score_db); t_peak = the band envelope maximum within peak_after_s.
    ``gate`` (the band's own step, without the broadband click term): only steps where the band itself rises by at
    least ``gate_frac`` of its largest step in the window can be the onset, so a hat or click that merely precedes the
    band's attack does not take the timing."""
    j0 = max(0, int(math.floor(t_lo * rate)))
    j1 = min(score.size - 2, int(math.ceil(t_hi * rate)))
    if j1 < j0:
        return None
    seg = score[j0 : j1 + 1]
    if gate is not None:
        g = gate[j0 : j1 + 1]
        gm = float(g.max())
        if gm > 0:
            seg = np.where(g >= gate_frac * gm, seg, -np.inf)
    j = j0 + int(np.argmax(seg))
    s = float(score[j])
    if s <= 0:
        return None
    kp = max(1, int(round(peak_after_s * rate)))
    jp = j + 1 + int(np.argmax(edb[j + 1 : j + 1 + kp]))
    return (j + 0.5) / rate, jp / rate, s


@dataclass
class HitEvent:
    t: float
    t_peak: float
    x: float  # attack / typical attack (event strength, "1 ~ a typical hit")
    v: float  # envelope value of the hit (0..1)
    rise_db: float  # onset score (dB step) at the refined onset
    i_peak: int  # 100 Hz frame of the attack peak
    viz_hit: bool


def select_hit_events(hr: HitResult, score: np.ndarray, edb: np.ndarray, *, x_min: float = 0.3,
                      viz_rise_db: float = 3.0, weak_rise_db: float = 6.0, search_before_s: float = 0.075,
                      search_after_s: float = 0.005, dedupe_s: float = 0.04,
                      accept_weak=None, gate: np.ndarray | None = None) -> list[HitEvent]:
    """Offline hit events: every attack episode the viz envelope registers (v > 0.3, re-arm ignored) or a weaker one
    (gated attack >= x_min of the typical attack), verified and timed on the 400 Hz onset score: the onset is the
    largest dB step within [peak - 75 ms, peak + 5 ms]; viz-strength attacks need a >= 3 dB step, weaker ones >= 6 dB.
    ``accept_weak(t)`` can veto the weaker ones (the kick band keeps only drum-like weak hits). Events closer than
    ``dedupe_s`` keep the stronger one. (The kick band uses :func:`select_kick_events`, which looks at the low band's own
    attack.) Envelope-less events (v == 0) are dropped."""
    out: list[HitEvent] = []
    for ep in hr.episodes:
        if ep.x < x_min:
            continue
        tp = ep.i_peak / RATE
        r = refine_onset(score, edb, tp - search_before_s, tp + search_after_s, gate=gate)
        if r is None:
            continue
        t, t_peak, rise = r
        strong = ep.v_free > 0.3
        if rise < (viz_rise_db if strong else weak_rise_db):
            continue
        if not strong and accept_weak is not None and not accept_weak(t):
            continue
        v_ev = max(ep.v_free, ep.v_armed)
        if v_ev <= 1e-4:
            continue
        out.append(HitEvent(t, t_peak, ep.x, v_ev, rise, ep.i_peak, ep.viz_hit))
    out.sort(key=lambda h: h.t)
    kept: list[HitEvent] = []
    for h in out:
        if kept and h.t - kept[-1].t < dedupe_s:
            if h.x > kept[-1].x:
                kept[-1] = h
            continue
        kept.append(h)
    return kept


def _window_max(a: np.ndarray, k: int, start: int) -> np.ndarray:
    """out[j] = max(a[j + start .. j + start + k - 1]) (indices clipped to the array; edges repeat)."""
    from scipy.ndimage import maximum_filter1d

    n = a.size
    f = maximum_filter1d(a, size=k, mode="nearest")
    idx = np.clip(np.arange(n) + start + k // 2, 0, n - 1)
    return f[idx]


def max_step(edb: np.ndarray, k_post: int, k_pre: int) -> np.ndarray:
    """Ripple-robust onset function: s[j] = mean(edb[j+1 .. j+k_post]) - max(edb[j-k_pre+1 .. j]).

    Against the *maximum* of the level before (not its mean, as :func:`step_contrast`), the dips of beating partials (a
    held bass note's harmonics, a kick tail against the bass) cannot make a step: only a level above every recent ripple
    peak counts (the SuperFlux idea, along time)."""
    n = edb.size
    c = np.concatenate([[0.0], np.cumsum(edb)])
    j = np.arange(n)
    a, b = np.clip(j + 1, 0, n), np.clip(j + 1 + k_post, 0, n)
    post = np.where(b > a, (c[b] - c[a]) / np.maximum(b - a, 1), edb)
    return post - _window_max(edb, k_pre, -k_pre + 1)


# ------------------------------------------------------------------------------------------------ kick events
#: sample rate (Hz) of the decimated signal the narrow low-band kick envelopes are computed from
KICK_LOW_FS = 3200
#: kick evidence bands (Hz): the start of a kick's pitch sweep (its attack), the same a little higher, its body
KICK_BANDS = {"attack": (90.0, 200.0), "attack_hi": (125.0, 250.0), "body": (30.0, 150.0)}
#: beater click band (Hz): above the bass and guitar body, below the hats
KICK_CLICK_BAND = (1500.0, 5000.0)
#: band (Hz) of the pitch-drop meter (excludes snare tones and sung notes above 160 Hz)
KICK_GLIDE_BAND = (30.0, 160.0)
GLIDE_RATE = 2000


def low_band_envelopes(mono: np.ndarray, sr: int, bands: dict[str, tuple[float, float]], *, rate: int = ENV_RATE,
                       fs: int = KICK_LOW_FS) -> dict[str, np.ndarray]:
    """Zero-phase envelopes (dB) at ``rate`` Hz of narrow low bands: one polyphase decimation to ``fs`` Hz, a 4th-order
    Butterworth band-pass applied forwards and backwards, the Hilbert magnitude, RMS over each 1 / rate window centred on
    j / rate. (:func:`band_envelope` decimates per band to 4x the top edge, too coarse for a 400 Hz envelope below
    ~150 Hz.)"""
    from scipy import signal

    x = np.asarray(mono, dtype=np.float64)
    g = math.gcd(int(fs), int(sr))
    y0 = signal.resample_poly(x, int(fs) // g, int(sr) // g) if fs != sr else x
    n_out = int(math.ceil(x.size * rate / sr))
    q = fs / rate
    c = np.round(np.arange(n_out) * q).astype(np.int64)
    h = int(round(q / 2))
    out: dict[str, np.ndarray] = {}
    for name, (lo, hi) in bands.items():
        sos = signal.butter(4, [lo, hi], btype="bandpass", fs=fs, output="sos")
        y = signal.sosfiltfilt(sos, y0)
        m = signal.hilbert(y, N=_fast_len(y.size))[: y.size]
        a2 = m.real**2 + m.imag**2
        cs = np.concatenate([[0.0], np.cumsum(a2)])
        a = np.clip(c - h, 0, a2.size)
        b = np.clip(c + h, 0, a2.size)
        out[name] = env_db(np.sqrt(np.maximum((cs[b] - cs[a]) / np.maximum(b - a, 1), 0.0)))
    return out


class GlideMeter:
    """Pitch drop of the energy an onset adds to the low band (KICK_GLIDE_BAND).

    The RMS frequency of a window is sqrt(P(y') / P(y)) / 2 pi (derivative power over power; for a sum of partials it is
    their power-weighted RMS frequency). The meter subtracts the power that was already there before the onset (at most
    ``share`` of each window's power, so a decaying background cannot be over-subtracted) and compares the RMS frequency
    of the added energy 2-25 ms after the onset with that 40-75 ms after it: a kick drum's body sweeps down (ratio
    ~1.5-2.5), a bass note holds its pitch (~1), whatever else (a held note, a kick tail) sounds underneath."""

    def __init__(self, mono: np.ndarray, sr: int, band: tuple[float, float] = KICK_GLIDE_BAND, rate: int = GLIDE_RATE):
        from scipy import signal

        g = math.gcd(int(rate), int(sr))
        y = signal.resample_poly(np.asarray(mono, dtype=np.float64), int(rate) // g, int(sr) // g)
        y = signal.sosfiltfilt(signal.butter(4, list(band), "bandpass", fs=rate, output="sos"), y)
        dy = np.gradient(y) * rate if y.size > 1 else np.zeros_like(y)
        self._cy = np.concatenate([[0.0], np.cumsum(y * y)])
        self._cd = np.concatenate([[0.0], np.cumsum(dy * dy)])
        self.rate = int(rate)
        self.n = y.size

    def power(self, a: float, b: float) -> tuple[float, float]:
        """Mean power of the band and of its derivative over [a, b) seconds (clipped to the signal)."""
        i = max(0, min(self.n - 1, int(round(a * self.rate))))
        j = max(i + 1, min(self.n, int(round(b * self.rate))))
        if self.n == 0:
            return 0.0, 0.0
        return (self._cy[j] - self._cy[i]) / (j - i), (self._cd[j] - self._cd[i]) / (j - i)

    def added_hz(self, t: float, w: tuple[float, float], pre: tuple[float, float], share: float = 0.5) -> float:
        py0, pd0 = self.power(t + pre[0], t + pre[1])
        py, pd = self.power(t + w[0], t + w[1])
        lam = min(1.0, share * py / py0) if py0 > 0 else 0.0
        ay, ad = py - lam * py0, pd - lam * pd0
        return math.sqrt(ad / ay) / (2.0 * math.pi) if ay > 0 and ad > 0 else float("nan")

    def glide(self, t: float, early: tuple[float, float] = (0.002, 0.025), late: tuple[float, float] = (0.040, 0.075),
              pre: tuple[float, float] = (-0.030, -0.008), share: float = 0.5) -> tuple[float, float]:
        """(ratio, f_early): RMS frequency of the added energy early over late (NaN when unmeasurable), and early (Hz).
        ``share=0`` measures the whole band (no subtraction): under a sidechain duck the bass the kick replaces is gone,
        so subtracting it would remove more than was there."""
        f1 = self.added_hz(t, early, pre, share)
        f2 = self.added_hz(t, late, pre, share)
        return (f1 / f2 if f1 == f1 and f2 == f2 and f2 > 0 else float("nan")), f1

    def added_db(self, t: float, post: tuple[float, float] = (0.0, 0.08), pre: tuple[float, float] = (-0.04, -0.003)) -> tuple[float, float]:
        """(dB the band's power rises from before the onset to the 80 ms after it, that power in dBFS)."""
        p0, _ = self.power(t + pre[0], t + pre[1])
        p1, _ = self.power(t + post[0], t + post[1])
        return 10.0 * math.log10(max(p1, 1e-20) / max(p0, 1e-20)), 10.0 * math.log10(max(p1, 1e-20))


@dataclass
class KickEvidence:
    """What the kick detector measured at one onset (dB unless noted)."""

    attack: float  # sweep start: burst of the 90-200 / 125-250 Hz band above its level before and 55-85 ms after
    glide: float  # pitch drop of the added low-band energy (ratio; NaN when unmeasurable)
    f_early: float  # RMS frequency (Hz) of the added low-band energy 2-25 ms after the onset
    click: float  # 1.5-5 kHz beater click above its level 50-10 ms before
    low_ex: float  # <= 400 Hz level after the onset above its maximum 60-7 ms before
    body_ex: float  # 30-150 Hz level (40 ms after) above its maximum 50-5 ms before
    body_add: float  # 30-160 Hz power rise over the 80 ms after the onset
    body_db: float  # that power, dBFS
    decay: float  # 30-150 Hz peak (40 ms) minus its mean 60-90 ms after the onset
    gate: float  # viz kick gate (0..1) over the 80 ms after the onset
    glide_raw: float = float("nan")  # the same pitch drop measured on the whole 30-160 Hz band (nothing subtracted)
    route: str = ""  # see KICK_ROUTES; "" = no kick
    low_over_mid: float = float("inf")  # 30-150 Hz peak minus the 300-3000 Hz (voice formant) peak, 0-40 ms after the onset

    def conf(self) -> float:
        """kick_conf (0..1): the strongest of the evidence combinations the routes use: sweep (attack, pitch drop,
        click), body (body onset, fast decay), clicky body (beater click on a low-band onset); a bass-note onset, a snare
        or a vocal reads low."""
        def c01(v: float) -> float:
            return float(np.clip(v, 0.0, 1.0))

        g = self.glide if self.glide == self.glide else 1.0
        gr = self.glide_raw if self.glide_raw == self.glide_raw else 1.0
        s_att = c01((self.attack - 3.0) / 7.0)
        s_gl = c01((g - 1.0) / 0.6)
        s_glr = c01((max(g, gr) - 1.0) / 0.6)
        s_cl = c01((self.click - 2.0) / 10.0)
        s_body = c01((self.body_ex - 2.0) / 8.0)
        s_dec = c01((self.decay - 2.0) / 10.0)
        s_beater = c01((self.click - 6.0) / 20.0)
        s_add = c01((self.body_add - 2.0) / 8.0)
        sweep = 0.45 * s_att + 0.4 * s_gl + 0.15 * s_cl
        duck = 0.45 * s_att + 0.4 * s_glr + 0.15 * s_cl
        body = 0.35 * s_body + 0.35 * s_dec + 0.15 * s_att + 0.15 * s_gl
        clicky = 0.35 * s_beater + 0.3 * s_body + 0.2 * s_att + 0.15 * s_add
        return round(float(min(1.0, max(sweep, duck, body, clicky))), 3)


#: kick routes (KickEvidence.route): which evidence made the onset a kick
KICK_ROUTES = ("sweep", "duck", "body", "click", "808", "roll")


#: default kick-selection parameters (the stage passes its params; see spectral/__init__.py)
KICK_DEFAULTS: dict[str, float] = {
    "gate": 0.5,  # the viz kick band must be above its gate within 80 ms of the onset
    "body_min_db": 1.0,  # every kick adds low-band energy: max(low_ex, body_ex, body_add) >= this
    "attack_db": 6.0,  # sweep route: attack >= this ...
    "glide": 1.25,  # ... with a pitch drop >= this
    "click_db": 6.0,  # ... or a beater click >= this with attack >= click_attack_db
    "click_attack_db": 12.0,  # UD2 precision: 10 -> 12 (a pluck bass with a hat on each note reads 10.1-10.6)
    "glide_strong": 1.6,  # ... or a strong pitch drop with attack >= attack_low_db (long 808-style kicks)
    "attack_low_db": 4.5,
    "body_ex_db": 6.5,  # body route (acoustic kicks: no sweep, click masked): body_ex >= this,
    "body_add_db": 4.5,  # body_add >= this,
    "body_decay_db": 8.0,  # decay >= this (a bass note sustains),
    "body_low_ex_db": 1.5,  # low_ex >= this,
    "body_f_hz": 68.0,  # and the added energy centred at >= this (a bass note's sub sits lower)
    "duck_click_db": 15.0,  # duck route (sidechain-ducked bass: the low band does not rise): attack >= attack_low_db, this
    #                         beater click and glide_strong on the added or the whole band
    "click_route": 0.0,  # UD2 precision: the clicky-body route is OFF by default (1 = on): its evidence (a click on a
    #                      low-band onset) is also what a pluck bass + hat, a low piano chord or a snare on a new bass note
    #                      show; on the real songs it fired <= 3 times per song
    "cb_click_db": 15.0,  # clicky-body route (acoustic kick over a held bass note): beater click >= this,
    "cb_attack_db": 3.5,  # attack >= this,
    "cb_low_ex_db": 3.0,  # <= 400 Hz excess >= this,
    "cb_body_ex_db": 4.5,  # 30-150 Hz onset >= this
    "cb_body_add_db": 3.0,  # and 30-160 Hz power rise >= this
    "s808_glide": 1.2,  # 808 route (long sine kick, little sweep, no click, over a bass): pitch drop >= this,
    "s808_attack_db": 3.0,  # attack >= this,
    "s808_body_ex_db": 5.5,  # 30-150 Hz onset >= this,
    "s808_body_add_db": 5.0,  # 30-160 Hz power rise >= this
    "s808_low_ex_db": 2.5,  # and <= 400 Hz excess >= this
    "roll_attack_db": 12.0,  # roll route: a kick on the previous kick's tail (40-150 ms after an accepted kick) with this
    "roll_glide": 1.1,  # burst and this pitch drop (the tail dilutes both the low-band rise and the pitch drop)
    "roll_gap_min_s": 0.04,
    "roll_gap_max_s": 0.15,
    "rel_db": 12.0,  # body power relative to the local mix level >= the median kick's - rel_db (faint thumps: plosives)
    "quiet_conf": 0.7,  # ... and an event > rel_db below the song's median kick body needs this kick_conf
    "level_win_s": 1.5,  # local mix level: the quieter of the RMS levels 1.5 s before and after the onset
    "nms_low_step_db": 2.0,  # onset priority: an own <= 400 Hz or 90-200 Hz step >= this first, then the onset score
    "nms_s": 0.02,  # one onset per 20 ms (the highest priority)
    "dedupe_s": 0.04,  # events closer than this keep the higher onset score
    "fine_s": 0.005,  # the reported time: the steepest <= 400 Hz (+ click) step within +-5 ms of the onset
    "pad_s": 0.1,  # silence prepended for the analysis, so a kick on the first sample has an onset
    "weak_strength": 0.5,  # UD2 precision: an event both weak (attack below this x the typical attack) ...
    "weak_conf": 0.8,  # ... and ambiguous (kick_conf below this) is dropped (Jeremy's snares: precision 0.90 -> 0.97)
    "low_over_mid_db": -1.0,  # W4A-ACAP: a kick's 30-150 Hz peak is not more than 1 dB below the 300-3000 Hz (voice formant)
    #                          peak in the 40 ms after its onset; a sung plosive / syllable onset is formant-dominated.
    #                          a cappella (contract synth vocals stem): 13 -> 2 'kicks'; real songs: 30 events removed, none
    #                          a drum-stem kick (Jeremy's one true kick below 0 dB sits at -0.7 dB); synth F1 0.982 -> 0.988
}


class KickAnalysis:
    """Envelopes and onset functions for kick detection on the mono mix."""

    def __init__(self, mono: np.ndarray, sr: int):
        self.low = env_db(band_envelope(mono, sr, None, 400.0))
        self.click = env_db(band_envelope(mono, sr, *KICK_CLICK_BAND))
        n = self.low.size
        lb = low_band_envelopes(mono, sr, KICK_BANDS)
        for k, v in lb.items():
            setattr(self, k, np.pad(v, (0, max(0, n - v.size)), mode="edge")[:n] if v.size else np.full(n, DB_FLOOR))
        self.n = n
        self.ls = step_contrast(self.low, STEP_K["low"])
        self.cs = step_contrast(self.click, STEP_K["click"])
        self.as_ = step_contrast(self.attack, STEP_K["low"])
        self.ax = max_step(self.attack, STEP_K["low"], 2 * STEP_K["low"])
        #: onset score: the ripple-robust sweep-start step plus half the click step (dB)
        self.score = self.ax + 0.5 * self.cs
        self.glide = GlideMeter(mono, sr)
        # body vs voice-formant level (W4A-ACAP): the same band-envelope method for both bands
        self.body_be = env_db(band_envelope(mono, sr, 30.0, 150.0))
        self.formant = env_db(band_envelope(mono, sr, 300.0, 3000.0))

    def candidates(self, thr_ls: float = 2.5, thr_as: float = 3.0, thr_cs: float = 6.0) -> list[int]:
        """Every 400 Hz sample where the low band, the sweep-start band or the click band steps up (a superset)."""
        from scipy.signal import find_peaks

        c: set[int] = set()
        for s, th in ((self.ls, thr_ls), (self.as_, thr_as), (self.cs, thr_cs)):
            pk, _ = find_peaks(s, height=th, distance=4)
            c.update(int(j) for j in pk)
        return sorted(c)

    def refine(self, j: int, before: float = 0.02, after: float = 0.015) -> float:
        t = (j + 0.5) / ENV_RATE
        r = refine_onset(self.score, self.low, t - before, t + after)
        return r[0] if r is not None else t

    def j_of(self, t: float) -> int:
        return int(np.clip(int(round(t * ENV_RATE - 0.5)), 0, max(self.n - 1, 0)))

    def evidence(self, t: float, gate: float = 1.0) -> KickEvidence:
        j = self.j_of(t)

        def ms(x: float) -> int:
            return int(round(x * ENV_RATE / 1000.0))

        def wmax(a: np.ndarray, j0: int, j1: int) -> float:
            j0, j1 = max(0, j0), min(a.size, j1)
            return float(a[j0:j1].max()) if j1 > j0 else DB_FLOOR

        def wmean(a: np.ndarray, j0: int, j1: int) -> float:
            j0, j1 = max(0, j0), min(a.size, j1)
            return float(a[j0:j1].mean()) if j1 > j0 else DB_FLOOR

        att = []
        for e in (self.attack, self.attack_hi):
            pk = wmax(e, j + 1, j + ms(25) + 1)
            att.append(pk - max(wmax(e, j - ms(50), j - ms(5) + 1), wmean(e, j + ms(55), j + ms(85))))
        g, f1 = self.glide.glide(t)
        g_raw, _ = self.glide.glide(t, share=0.0)
        body_add, body_db = self.glide.added_db(t)
        bpk = wmax(self.body, j, j + ms(40))
        lvm = wmax(self.body_be, j, j + ms(40)) - wmax(self.formant, j, j + ms(40))
        return KickEvidence(
            low_over_mid=lvm,
            glide_raw=g_raw,
            attack=max(att),
            glide=g,
            f_early=f1,
            click=wmax(self.click, j - 1, j + ms(15) + 1) - wmax(self.click, j - ms(50), j - ms(10) + 1),
            low_ex=wmax(self.low, j + 1, j + ms(30) + 1) - wmax(self.low, j - ms(60), j - ms(7) + 1),
            body_ex=wmax(self.body, j + 1, j + ms(40) + 1) - wmax(self.body, j - ms(50), j - ms(5) + 1),
            body_add=body_add,
            body_db=body_db,
            decay=bpk - wmean(self.body, j + ms(60), j + ms(90)),
            gate=gate,
        )


def kick_route(ev: KickEvidence, p: dict[str, float]) -> str:
    """Which kind of kick the evidence shows, or "" (none). Each route is one physical signature; a bass-note onset
    (no pitch drop, no beater click, no burst that dies within 85 ms) matches none of them.

    * "sweep": the sweep-start burst with a pitch drop (or a click and a big burst), adding low-band energy: electronic
      and most modern kicks.
    * "duck": the same burst, a beater click and a strong pitch drop on the added or the whole band, while the low band
      does not rise: a sidechain-ducked bass gives way to the kick (EDM).
    * "body": a strong 30-150 Hz onset centred >= 68 Hz that decays >= 8 dB within 90 ms: an acoustic kick alone.
    * "click": a beater click on a low-band onset with a burst: an acoustic kick over a held bass note (the bass keeps
      the band from decaying, the click is what a bass note lacks). OFF by default (``click_route`` = 0, UD2): a pluck
      bass with a hat, a low piano chord and a snare on a new bass note show the same evidence.
    * "808": a long sine kick (little sweep, no click): a moderate pitch drop of the added energy on a clear low-band
      onset with a burst.
    ("roll" is assigned by :func:`select_kick_events`.)"""
    if ev.gate < p["gate"]:
        return ""
    if ev.low_over_mid < p.get("low_over_mid_db", -math.inf):
        return ""   # formant-dominated onset: a sung plosive / syllable, not a kick (W4A-ACAP)
    g = ev.glide if ev.glide == ev.glide else 0.0
    gr = ev.glide_raw if ev.glide_raw == ev.glide_raw else 0.0
    adds = max(ev.low_ex, ev.body_ex, ev.body_add) >= p["body_min_db"]
    if adds and ((ev.attack >= p["attack_db"] and (g >= p["glide"] or (ev.click >= p["click_db"] and ev.attack >= p["click_attack_db"])))
                 or (ev.attack >= p["attack_low_db"] and g >= p["glide_strong"])):
        return "sweep"
    if ev.attack >= p["attack_low_db"] and ev.click >= p["duck_click_db"] and max(g, gr) >= p["glide_strong"]:
        return "duck"
    f1 = ev.f_early if ev.f_early == ev.f_early else 0.0
    if (ev.body_ex >= p["body_ex_db"] and ev.body_add >= p["body_add_db"] and ev.decay >= p["body_decay_db"]
            and ev.low_ex >= p["body_low_ex_db"] and f1 >= p["body_f_hz"]):
        return "body"
    if (p.get("click_route", 0.0) >= 0.5
            and ev.click >= p["cb_click_db"] and ev.attack >= p["cb_attack_db"] and ev.low_ex >= p["cb_low_ex_db"]
            and ev.body_ex >= p["cb_body_ex_db"] and ev.body_add >= p["cb_body_add_db"]):
        return "click"
    if (g >= p["s808_glide"] and ev.attack >= p["s808_attack_db"] and ev.body_ex >= p["s808_body_ex_db"]
            and ev.body_add >= p["s808_body_add_db"] and ev.low_ex >= p["s808_low_ex_db"]):
        return "808"
    return ""


def _local_level_db(x: np.ndarray, sr: int, ts: np.ndarray, win_s: float) -> np.ndarray:
    """dB RMS level of the mix around each time: the quieter of the ``win_s`` before and the ``win_s`` after (so a kick at
    the edge of a quiet intro is measured against the intro, not against the loud part that follows)."""
    c2 = np.concatenate([[0.0], np.cumsum(np.asarray(x, dtype=np.float64) ** 2)])
    w = max(1, int(round(win_s * sr)))
    out = np.empty(ts.size)
    for k, t in enumerate(ts):
        i = int(np.clip(round(t * sr), 0, x.size))
        lv = []
        if i > 0:
            a = max(0, i - w)
            lv.append((c2[i] - c2[a]) / (i - a))
        if i < x.size:
            b = min(x.size, i + w)
            lv.append((c2[b] - c2[i]) / (b - i))
        out[k] = 10.0 * math.log10(max(min(lv) if lv else 0.0, 1e-12))
    return out


def select_kick_events(hr: HitResult, mono: np.ndarray, sr: int, params: dict[str, float] | None = None,
                       ka: KickAnalysis | None = None) -> list[tuple[HitEvent, KickEvidence]]:
    """Kick-drum events, judged on physical evidence rather than on the viz kick-band envelope alone.

    1. Candidates: every step of the <= 400 Hz band, of the 90-200 Hz band (where a kick's pitch sweep starts) and of
       the 1.5-5 kHz click band, on the mix with ``pad_s`` of silence prepended (a kick on the first sample is an onset
       too); each is timed on the onset score (the ripple-robust 90-200 Hz step plus half the click step) and only the
       onset with the highest priority within ``nms_s`` is kept: first an onset with a low-band step of its own (<= 400 Hz
       or 90-200 Hz step >= ``nms_low_step_db``; a hat click just before the kick cannot take its slot), then the score.
    2. Evidence at each onset (:class:`KickEvidence`): the sweep-start burst, the pitch drop of the added low-band energy
       and of the whole band (:class:`GlideMeter`), the beater click, the body onset and its decay, the viz kick gate.
    3. A kick matches one physical signature (:func:`kick_route`): swept attack, sidechain duck, acoustic body, clicky
       body over a bass, 808; then, repeatedly, "roll": a strong burst with some pitch drop 40-150 ms after an accepted
       kick (the previous kick's tail dilutes its evidence). No refractory: a bass-note onset cannot suppress the kick
       after it, and double kicks / 16th rolls need none.
    4. Faint thumps are dropped: body power relative to the local mix level (:func:`_local_level_db`) more than
       ``rel_db`` below the median kick's. Relative to the mix, not to the other kicks, so the kicks of a quiet intro, a
       breakdown or a fade-out stay while a plosive that is faint against its surroundings goes. An event more than
       ``rel_db`` below the song's median kick body must also show clear kick evidence (kick_conf >= ``quiet_conf``).
    5. Reported time: the steepest <= 400 Hz (+ click) step within +-``fine_s`` of the onset. Events closer than
       ``dedupe_s`` keep the higher onset score.
    6. Precision over recall (user decision UD2: agents read the drum-stem kick, hits.kick is the fallback): an event whose
       attack is weaker than ``weak_strength`` x the typical one AND whose kick_conf is below ``weak_conf`` is dropped
       (except the roll and duck routes and any event <= ``roll_gap_max_s`` after the previous kept kick, whose attack
       is diluted by that kick's tail / the ducked bass by design), and the clicky-body route is off unless
       ``click_route`` >= 0.5.
    The event's x / envelope value come from the viz kick-band attack episode that peaks within -30..+120 ms of it (or are
    estimated from its body step when viz saw none); ``viz`` is true when the viz attack episode its onset falls in
    registered a hit (viz arms once per attack). ``rise_db`` is the onset score.
    ``ka`` (optional) must have been built on the padded mix (``pad_s`` of zeros, then ``mono``)."""
    p = {**KICK_DEFAULTS, **(params or {})}
    mono = np.asarray(mono, dtype=np.float64)
    npad = max(0, int(round(p["pad_s"] * sr)))
    off = npad / sr
    xm = np.concatenate([np.zeros(npad), mono]) if npad else mono
    ka = ka or KickAnalysis(xm, sr)
    ts = sorted({round(ka.refine(j), 6) for j in ka.candidates()})
    sc = {t: float(ka.score[ka.j_of(t)]) for t in ts}
    arr = np.asarray(ts)
    kf = max(1, int(round(p["fine_s"] * ENV_RATE)))
    # priority: an onset with a low-band step of its own first (a hat click just before the kick cannot take its slot),
    # then the onset score
    prio = {t: (max(float(ka.ls[ka.j_of(t)]), float(ka.ax[ka.j_of(t)])) >= p["nms_low_step_db"], sc[t]) for t in ts}
    keep = []
    for t in ts:
        near = arr[np.abs(arr - t) <= p["nms_s"]]
        if all(prio[t] >= prio[float(u)] for u in near):
            keep.append(t)
    evs: list[tuple[float, KickEvidence]] = []
    for t in keep:
        i0 = int(round((t - off) * RATE))
        lo, hi = max(0, min(hr.gate.size - 1, i0)), max(0, min(hr.gate.size, i0 + 9))
        g = float(hr.gate[lo:hi].max()) if hi > lo and i0 + 9 > 0 and i0 < hr.gate.size else 0.0
        ev = ka.evidence(t, g)
        ev.route = kick_route(ev, p)
        evs.append((t, ev))
    # rolls: each accepted kick may admit the next one on its tail
    changed = True
    while changed:
        changed = False
        acc_t = np.asarray([t for t, e in evs if e.route])
        if not acc_t.size:
            break
        for t, ev in evs:
            if ev.route or ev.gate < p["gate"] or ev.low_over_mid < p.get("low_over_mid_db", -math.inf):
                continue
            g = ev.glide if ev.glide == ev.glide else 0.0
            gap = t - acc_t
            if (ev.attack >= p["roll_attack_db"] and g >= p["roll_glide"]
                    and max(ev.low_ex, ev.body_ex, ev.body_add) >= p["body_min_db"]
                    and bool(np.any((gap >= p["roll_gap_min_s"]) & (gap <= p["roll_gap_max_s"])))):
                ev.route = "roll"
                changed = True
    acc = [(t, e) for t, e in evs if e.route]
    if not acc:
        return []
    ta = np.asarray([t for t, _ in acc])
    rel = np.asarray([e.body_db for _, e in acc]) - _local_level_db(xm, sr, ta, p["level_win_s"])
    ref = float(np.median(rel))
    gref = float(np.median([e.body_db for _, e in acc]))
    sel = [(t, ev) for k, (t, ev) in enumerate(acc)
           if rel[k] >= ref - p["rel_db"] and (ev.body_db >= gref - p["rel_db"] or ev.conf() >= p["quiet_conf"])]
    fine = ka.ls + 0.5 * ka.cs
    timed: list[tuple[float, float, KickEvidence]] = []
    for t0, ev in sel:
        # the reported onset: the steepest <= 400 Hz (+ click) step within +-fine_s of the sweep-start onset (the max-step
        # onset function reads up to ~4 ms early on a smeared attack)
        j0 = ka.j_of(t0)
        a = max(0, j0 - kf)
        j = a + int(np.argmax(fine[a : j0 + kf + 1]))
        timed.append(((j + 0.5) / ENV_RATE, sc[t0], ev))
    timed.sort(key=lambda z: z[0])
    ded: list[tuple[float, float, KickEvidence]] = []
    for z in timed:
        if ded and z[0] - ded[-1][0] < p["dedupe_s"]:
            if z[1] > ded[-1][1]:
                ded[-1] = z
            continue
        ded.append(z)
    eps_t = np.asarray([e.i_peak / RATE for e in hr.episodes])
    viz_a = np.asarray([e.i_start / RATE for e in hr.episodes if e.viz_hit])
    viz_b = np.asarray([e.i_end / RATE for e in hr.episodes if e.viz_hit])
    typical = max(float(np.median([e.body_ex for _, _, e in ded])), 3.0)
    kp = max(1, int(round(0.06 * ENV_RATE)))
    out: list[tuple[HitEvent, KickEvidence]] = []
    for tpad, rise, ev in ded:
        j = ka.j_of(tpad)
        jp = min(ka.n - 1, j + 1 + int(np.argmax(ka.low[j + 1 : j + 1 + kp]))) if j + 1 < ka.n else j
        t = max(0.0, tpad - off)
        t_peak = max(t, jp / ENV_RATE - off)
        m = np.where((eps_t >= t - 0.03) & (eps_t <= t + 0.12))[0] if eps_t.size else np.array([], int)
        if m.size:
            ep = hr.episodes[int(m[np.argmax([hr.episodes[i].x for i in m])])]
            x, v, ip = ep.x, max(ep.v_free, ep.v_armed), ep.i_peak
        else:
            x, v, ip = float(np.clip(ev.body_ex / typical, 0.3, 2.0)), 0.0, int(round(t_peak * RATE))
        # viz registers this kick when the viz attack episode its onset falls in (-30 ms .. +60 ms) registered a hit
        # (viz arms once per attack: a bass note that starts the attack 100 ms earlier takes the same hit)
        viz = bool(np.any((viz_a <= t + 0.06) & (viz_b >= t - 0.03))) if viz_a.size else False
        on_tail = bool(out) and t - out[-1][0].t <= p["roll_gap_max_s"]
        if x < p["weak_strength"] and ev.conf() < p["weak_conf"] and ev.route not in ("roll", "duck") and not on_tail:
            # UD2 precision over recall: a weak attack with ambiguous evidence is more often a snare / tom over a bass
            # onset than a kick (agents read the drum-stem kick; hits.kick is the fallback and must not invent kicks).
            # roll / duck kicks and kicks on the previous kick's tail (<= roll_gap_max_s) are exempt: their attack is
            # diluted by design (16th double kicks), and their own routes demand a strong burst
            continue
        if v <= 1e-4:
            v = float(smoothstep01((x - HIT_THRESHOLD) / (1.15 - HIT_THRESHOLD)))
        out.append((HitEvent(t, t_peak, x, max(v, 0.05), rise, ip, viz), ev))
    return out


def aligned_envelopes(hr: HitResult, events: list[HitEvent], release_s: float = HIT_RELEASE,
                      max_shift: int = 8) -> tuple[np.ndarray, np.ndarray, int]:
    """(raw, released, shift): the viz raw envelope moved earlier by the median detection lag (frames from the
    refined onset to the attack peak) so each flash sits on its onset, with the contract flash rule applied at every
    event (value = the event's envelope value), and the released curve recomputed from it."""
    lags = [h.i_peak - h.t * RATE for h in events]
    shift = int(np.clip(round(float(np.median(lags))), 0, max_shift)) if lags else 0
    raw = shift_earlier(hr.raw, shift)
    for h in events:
        flash(raw, h.t, h.v)
    return raw, release(raw, release_s), shift


# ------------------------------------------------------------------------------------------------ flux onsets
@dataclass
class OnsetResult:
    flux: np.ndarray
    threshold: np.ndarray
    items: list[dict[str, Any]]


def band_flux(norm: np.ndarray, rng: tuple[int, int]) -> np.ndarray:
    """viz ``_flux``: mean positive change of the normalised bands over the range (first frame 0)."""
    a, b = rng
    d = np.diff(norm[:, a : b + 1], axis=0, prepend=norm[:1, a : b + 1])
    return np.maximum(d, 0.0).sum(axis=1) / (b - a + 1)


def flux_onsets(flux: np.ndarray, energy_smooth: np.ndarray, band: str, *, window_s: float = 0.8,
                rate: int = RATE) -> OnsetResult:
    """Centred version of the viz onset rule: threshold = mean(flux over the centred window, current frame excluded)
    * mult + 0.012; an onset is the local maximum of an above-threshold run, after the refractory gap, while the
    smoothed band energy exceeds the viz gate. Strength s in 0..1 maps onto viz's [base, 1] range."""
    from scipy import ndimage

    w = max(3, int(round(window_s * rate)) | 1)
    mean = (ndimage.uniform_filter1d(flux, size=w, mode="nearest") * w - flux) / (w - 1)
    thr = mean * FLUX_MULT[band] + FLUX_FLOOR
    above = (flux > thr) & (energy_smooth > ONSET_ENERGY_GATE[band])
    gap = ONSET_GAP_S[band]
    base = ONSET_STRENGTH_BASE[band]
    items: list[dict[str, Any]] = []
    last = -1e9
    i = 0
    n = flux.size
    while i < n:
        if not above[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and above[j + 1]:
            j += 1
        k = i + int(np.argmax(flux[i : j + 1]))
        if (k - last) / rate >= gap:
            viz = float(np.clip(base + (flux[k] - thr[k]) / (thr[k] + 1e-4) * 0.3, base, 1.0))
            items.append({"i": k, "strength": (viz - base) / (1.0 - base), "flux": float(flux[k])})
            last = k
        i = j + 1
    return OnsetResult(flux, thr, items)


# ------------------------------------------------------------------------------------------------ helpers
def pnorm(v: np.ndarray, lo_p: float = 2.0, hi_p: float = 99.5, floor: float | None = None) -> tuple[np.ndarray, float, float]:
    """Per-song p02-p99.5 normalisation (clipped). Frames at the floor (silence) are excluded from the percentiles
    when at least 1 % of the frames are above it."""
    v = np.asarray(v, dtype=np.float64)
    pool = v
    if floor is not None:
        live = v > floor + 1e-6
        if live.sum() >= max(10, 0.01 * v.size):
            pool = v[live]
    if pool.size == 0:
        return np.zeros_like(v), 0.0, 0.0
    lo, hi = float(np.percentile(pool, lo_p)), float(np.percentile(pool, hi_p))
    if hi - lo < 1e-9:
        return np.zeros_like(v), lo, hi
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0), lo, hi


def flash(env: np.ndarray, t: float, value: float, rate: int = RATE) -> None:
    """Contract flash rule: hold ``value`` at floor(t * rate) and ceil(t * rate)."""
    from mvh.contract.conventions import flash_samples

    a, b = flash_samples(t, rate)
    for i in (a, b):
        if 0 <= i < env.size and env[i] < value:
            env[i] = value


def shift_earlier(x: np.ndarray, k: int) -> np.ndarray:
    if k <= 0:
        return x.copy()
    return np.concatenate([x[k:], np.zeros(k, x.dtype)])
