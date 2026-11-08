# ruff: noqa: E501  (long formulas, tables and docstrings)
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
* hit events are the viz hits (an attack whose envelope exceeded 0.3 while armed) refined on a 400 Hz zero-phase band
  envelope (onset = the 50 % rise point); the hit envelopes are shifted earlier by the median detection lag so their
  flash lands on the onset frame (contract flash rule);
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


def low_excess_db(low_db: np.ndarray, post_s: float = 0.06, pre_from_s: float = 0.0075, pre_to_s: float = 0.06,
                  rate: int = ENV_RATE) -> np.ndarray:
    """ex[j] = max(low[j+1 .. j+post]) - max(low[j-pre_to .. j-pre_from]): how far the low band's level after a step
    exceeds the level it had in the 60..7 ms before. A kick's attack stands well above the previous level (its own
    decaying tail or a held bass note); the recovery from a beating null of a bass note against a kick tail only
    returns to the level it had before the null (excess ~ 0 or negative)."""
    kp = max(1, int(round(post_s * rate)))
    a, b = int(round(pre_from_s * rate)), int(round(pre_to_s * rate))
    post = _window_max(low_db, kp, 1)
    pre = _window_max(low_db, max(1, b - a + 1), -b)
    return post - pre


GLIDE_RATE = 2000


def glide_signal(mono: np.ndarray, sr: int, rate: int = GLIDE_RATE, cutoff_hz: float = 250.0) -> np.ndarray:
    """The mono mix low-passed at ``cutoff_hz`` (zero phase) and decimated to ``rate`` Hz: the input of ``kick_glide``."""
    from math import gcd

    from scipy import signal

    g = gcd(int(rate), int(sr))
    y = signal.resample_poly(np.asarray(mono, dtype=np.float64), int(rate) // g, int(sr) // g)
    return signal.sosfiltfilt(signal.butter(4, cutoff_hz, "lowpass", fs=rate, output="sos"), y)


def _zero_cross_hz(y: np.ndarray, rate: int, a: float, b: float) -> float:
    seg = y[max(0, int(round(a * rate))) : max(0, int(round(b * rate)))]
    if seg.size < 8:
        return float("nan")
    s = np.signbit(seg)
    return float(np.sum(s[1:] != s[:-1])) / 2.0 / (b - a)


def _finite_ge(v: float, lim: float) -> bool:
    return v == v and v >= lim


def kick_glide(y: np.ndarray, t: float, rate: int = GLIDE_RATE) -> float:
    """Pitch drop of the low band after an onset at ``t``: the zero-crossing frequency (Hz) of the 2..30 ms after it over
    that of the 45..90 ms after it. A kick drum's body sweeps down (ratio ~ 1.5-2.5); a bass note holds its pitch (~ 1).
    NaN when there is no signal to measure."""
    f1 = _zero_cross_hz(y, rate, t + 0.002, t + 0.030)
    f2 = _zero_cross_hz(y, rate, t + 0.045, t + 0.090)
    if not (f1 > 0 and f2 > 0):
        return float("nan")
    return f1 / f2


def select_kick_events(hr: HitResult, low_db: np.ndarray, click_db: np.ndarray, *, x_min: float = 0.3,
                       ls_viz_min: float = 3.0, ls_min: float = 5.0, own_ls: float = 6.5, own_excess: float = 3.5,
                       click_min_db: float = 15.0, refractory_s: float = 0.20, roll_s: float = 0.15,
                       glide=None, glide_min: float = 1.4, glide_hi: float = 1.7, sweep_cs: float = 12.0, sweep_ls: float = 4.0,
                       accept_weak=None,
                       search_before_s: float = 0.075, search_after_s: float = 0.005, dedupe_s: float = 0.04,
                       rate: int = ENV_RATE) -> list[HitEvent]:
    """Kick events from the viz kick-band attacks, timed and vetted on the low (<= 400 Hz) band's own attack.

    ``ls`` is the low band's step (``step_contrast`` over 10 ms boxes) and ``ex`` its excess (``low_excess_db``): how far
    the level after the step stands above the level before it. A kick has both; the beating of a bass note against a kick
    tail, a hat or a cymbal in a kick's tail does not, and the click (>= 1 kHz) is not needed (it can be masked).

    * every attack episode of the viz kick band (gated attack >= x_min) is timed on the low band's step: the broadband
      click step only breaks ties among the steps that are at least half the largest low step in the window, so a hat
      that precedes a kick cannot take its timing. Viz-strength attacks (v > 0.3) need ``ls >= ls_viz_min``, weaker ones
      ``ls >= ls_min`` and ``accept_weak(t)`` (drum-kick likeness);
    * a candidate within ``refractory_s`` after the previous event (a tail of that kick, where bass beating, hats and
      cymbals live) must show the low band's own attack (``ls >= own_ls`` and ``ex >= own_excess``): it is a new kick,
      not the ripple of the old one (8th-note kicks 200-230 ms apart each have it, whatever the cymbal wash does);
    * pitch drop (``glide(t)`` = :func:`kick_glide`): a drum kick's body sweeps down, a bass note holds its pitch. A weak
      hit without it is no kick; a click-less hit within the refractory is a kick when it has it; and in a song whose
      events mostly show it (``glide_song``) every hit needs it. Songs whose mix hides the sweep are not judged by it;
    * a low-band step with a drum click (>= ``sweep_cs``) and a strong pitch drop (``glide_hi``) is a kick wherever it sits;
    * low-band steps without a viz attack (fast double-bass: the 46 ms kick band barely dips between kicks, so its attacks
      fall under the viz floor) are kicks when the kick band is above its gate, they sit within ``roll_s`` of another kick,
      and have the own attack and a coincident >= 1 kHz click step of >= ``click_min_db``.
    The event's x / envelope value come from the matching episode, or are estimated from ``ls`` when there is none."""
    from scipy.signal import find_peaks

    ls = step_contrast(low_db, STEP_K["low"])
    cs = step_contrast(click_db, STEP_K["click"])
    score = ls + cs
    ex = low_excess_db(low_db, rate=rate)
    n = ls.size
    kp = max(1, int(round(0.06 * rate)))

    def jof(t: float) -> int:
        return int(np.clip(int(round(t * rate - 0.5)), 0, n - 1))

    cands: list[HitEvent] = []
    for ep in hr.episodes:
        if ep.x < x_min:
            continue
        tp = ep.i_peak / RATE
        r = refine_onset(score, low_db, tp - search_before_s, tp + search_after_s, gate=ls)
        if r is None:
            continue
        t, t_peak, rise = r
        j = jof(t)
        strong = ep.v_free > 0.3
        if ls[j] < (ls_viz_min if strong else ls_min):
            continue
        if not strong and accept_weak is not None and not accept_weak(t):
            continue
        v_ev = max(ep.v_free, ep.v_armed)
        if v_ev <= 1e-4:
            continue
        cands.append(HitEvent(t, t_peak, ep.x, v_ev, rise, ep.i_peak, ep.viz_hit))

    # low-band steps outside viz attacks
    typical = max(float(np.median([h.rise_db for h in cands])) if cands else 10.0, 6.0)
    eps_t = np.asarray([e.i_peak / RATE for e in hr.episodes])
    pk, _ = find_peaks(ls, height=min(own_ls, sweep_ls), distance=max(1, int(round(0.02 * rate))))
    have = np.asarray([h.t for h in cands])
    for j in pk:
        t = (j + 0.5) / rate
        cs_j = cs[max(0, j - 4) : j + 5].max()
        # a drum click and the pitch sweep of a kick body on a low-band step: a kick wherever it sits
        sweep = glide is not None and cs_j >= sweep_cs and ls[j] >= sweep_ls and _finite_ge(glide(t), glide_hi)
        if have.size and np.min(np.abs(have - t)) < dedupe_s:
            continue
        if not sweep:
            if ls[j] < own_ls or ex[j] < own_excess or cs_j < click_min_db:
                continue
            if not (have.size and np.any(np.abs(have - t) < roll_s)):
                continue  # a roll: only a step next to another kick (a lone step is a bass note with a hat on it)
        if hr.gate.size and hr.gate[min(hr.gate.size - 1, int(round(t * RATE)))] < 0.5:
            continue  # the viz kick band (35-100 Hz) is not above its gate: a piano note or a snare is no kick
        jp = min(n - 1, j + 1 + int(np.argmax(low_db[j + 1 : j + 1 + kp]))) if j + 1 < n else j
        m = np.where((eps_t >= t - 0.03) & (eps_t <= t + 0.12))[0] if eps_t.size else np.array([], int)
        if m.size:
            ep = hr.episodes[int(m[np.argmax([hr.episodes[i].x for i in m])])]
            x, v, ip, viz = ep.x, max(ep.v_free, ep.v_armed), ep.i_peak, ep.viz_hit
        else:
            x, ip, viz = float(np.clip(ls[j] / typical, 0.3, 2.0)), int(round(jp / rate * RATE)), False
            v = 0.0
        if v <= 1e-4:
            v = float(smoothstep01((x - HIT_THRESHOLD) / (1.15 - HIT_THRESHOLD)))
        cands.append(HitEvent(t, jp / rate, x, max(v, 0.05), float(score[j]), ip, viz))
        have = np.append(have, t)
    cands.sort(key=lambda h: h.t)
    kept: list[HitEvent] = []
    for h in cands:
        j = jof(h.t)
        if kept and h.t - kept[-1].t < dedupe_s:
            if h.x > kept[-1].x:
                kept[-1] = h
            continue
        gv = glide(h.t) if glide is not None else float("nan")
        if gv == gv and h.v <= 0.3 and gv < glide_min:
            continue  # a weak hit without the pitch drop of a kick body is a bass note
        if kept and h.t - kept[-1].t < refractory_s and (ls[j] < own_ls or ex[j] < own_excess):
            continue
        kept.append(h)
    return kept


def click_peak_db(t: float, click_db: np.ndarray, rate: int = ENV_RATE) -> float:
    """Peak of the >= 1 kHz envelope (dB) within -5 ms .. +20 ms of the onset ``t``."""
    j = int(round(t * rate))
    if j < 4 or j + 6 >= click_db.size:
        return -200.0
    return float(click_db[max(0, j - 2) : j + 8].max())


def click_rise_db(t: float, click_db: np.ndarray, rate: int = ENV_RATE, ref_db: float | None = None,
                  rel_db: float = 15.0) -> float:
    """Broadband-click evidence at ``t`` (dB): the peak of the >= 1 kHz envelope around the onset minus its maximum over
    the 50-10 ms before it (a hat or cymbal ringing on is not a new click). A drum attack stands out of that floor by tens of dB; bass beating, which leaves the
    >= 1 kHz band as it was, by ~0. With ``ref_db`` (the song's typical kick-click peak) a click more than ``rel_db``
    below it counts as none: stray ripple of the band is not a drum click even when the floor between hits is quieter."""
    j = int(round(t * rate))
    if j < 4 or j + 6 >= click_db.size:
        return 0.0
    pk = click_peak_db(t, click_db, rate)
    if ref_db is not None and pk < ref_db - rel_db:
        return 0.0
    a = max(0, j - int(round(0.05 * rate)))
    b = max(a + 1, j - int(round(0.01 * rate)))
    return pk - float(np.max(click_db[a:b]))


def kick_confidence(t: float, low_db: np.ndarray, click_db: np.ndarray, rate: int = ENV_RATE,
                    click_ref_db: float | None = None) -> float:
    """How drum-kick-like a kick-band hit is (0..1): half for a broadband click (the >= 1 kHz envelope stands >= 6 dB
    above its level just before the onset, and not far below the song's typical kick click), half for a decaying low
    band (the level 150-250 ms after the attack peak is >= 6 dB below it); a sustained bass note scores low on both.
    808s decay slowly and may read ~0.5."""
    j = int(round(t * rate))
    if j < 4 or j + 6 >= low_db.size:
        return 0.5
    click = click_rise_db(t, click_db, rate, click_ref_db)
    a = int(round(0.06 * rate))
    pk = float(low_db[j : j + a].max())
    t0, t1 = j + int(round(0.15 * rate)), j + int(round(0.25 * rate))
    tail = float(low_db[t0:t1].mean()) if t1 <= low_db.size and t1 > t0 else pk - 12.0
    c = 0.5 * float(np.clip((click - 2.0) / 4.0, 0.0, 1.0)) + 0.5 * float(np.clip((pk - tail - 2.0) / 4.0, 0.0, 1.0))
    return round(c, 3)


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
