"""stem_activity core (numpy only; pure functions, unit-tested on synthetic signals).

Definitions (PLAN §5 stem_activity, CONTRACT ``stem.{stem}.*`` channels, docs/contract/decisions/M3a.md):

* ``rms_db``   RMS of the stem (power averaged over channels) in a 46 ms window centred at i / 100 s, dBFS,
               floored at -120 (the same window as ``loud.rms_db``).
* ``rel_db``   ``rms_db(stem) - rms_db(mix)`` per frame, clamped to [-120, 12]; -120 where the stem is digital
               silence.
* ``active``   1 inside an activity segment. The decision uses a 0.4 s centred RMS (so a sparse kick or a
               staccato part does not flicker between hits): a frame qualifies when the stem is above
               ``active_db`` (-45 dBFS) **and** within ``within_db`` (18 dB) of the mix. Runs of qualifying
               frames are joined across gaps shorter than ``release_ms`` (500 ms), then runs shorter than
               ``attack_ms`` (300 ms) are dropped. Offline and non-causal: a segment starts where the stem
               starts, not 300 ms later.
* ``level``    ``rms_db`` normalised to 0..1 by one p02-p99.5 range shared by every stem (so levels compare
               across stems); the range is recorded as norm lo/hi.

Cross-model agreement (SPIKE: "vocal presence must not come from stem energy alone"): for a stem that a second,
independent separator also produced (htdemucs from separate_fast, BS-RoFormer-SW's own vocals from separate_hq),
``agreement`` per frame is ``clip((alt_db - stem_db + 15) / 9, 0, 1)`` on the 0.4 s levels: 1 when the other
model hears the stem within 6 dB, 0 when it is 15 dB or more quieter. Segment and stem confidences are means of
it over the active frames.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np

__all__ = [
    "FLOOR_DB",
    "RATE_HZ",
    "n_frames",
    "frame_power",
    "power_db",
    "rel_db",
    "activity_mask",
    "segments_of",
    "agreement",
    "StemStats",
    "stem_stats",
    "shared_norm",
]

FLOOR_DB = -120.0
RATE_HZ = 100
RMS_WINDOW_S = 2048 / 44100  # 46.4 ms, as loud.rms_db
DECISION_WINDOW_S = 0.4


def n_frames(n_samples: int, sr: int, rate: int = RATE_HZ) -> int:
    """ceil(n_samples * rate / sr) in integer arithmetic (CONTRACT §2.2)."""
    return -(-int(n_samples) * int(rate) // int(sr))


def frame_power(x: np.ndarray, sr: int, window_s: float, n_out: int, rate: int = RATE_HZ) -> np.ndarray:
    """Mean power (averaged over channels) in a window of ``window_s`` centred at i / rate, for i < n_out.
    Windows are clipped at the signal edges (the mean is over the samples that exist). float64."""
    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 1:
        a = a[None, :]
    p = np.mean(np.square(a), axis=0)
    n = p.shape[0]
    cs = np.zeros(n + 1, dtype=np.float64)
    np.cumsum(p, out=cs[1:])
    half = max(1, int(round(window_s * sr / 2.0)))
    centres = (np.arange(n_out, dtype=np.int64) * int(sr) + int(rate) // 2) // int(rate)
    lo = np.clip(centres - half, 0, n)
    hi = np.clip(centres + half, 0, n)
    width = np.maximum(hi - lo, 1)
    out = (cs[hi] - cs[lo]) / width
    out[hi <= lo] = 0.0
    return np.maximum(out, 0.0)


def power_db(p: np.ndarray, floor: float = FLOOR_DB) -> np.ndarray:
    with np.errstate(divide="ignore"):
        d = 10.0 * np.log10(np.maximum(p, 0.0))
    d = np.where(np.isfinite(d), d, floor)
    return np.maximum(d, floor)


def rel_db(stem_db: np.ndarray, mix_db: np.ndarray, floor: float = FLOOR_DB, ceil: float = 12.0) -> np.ndarray:
    r = np.clip(stem_db - mix_db, floor, ceil)
    return np.where(stem_db <= floor, floor, r)


def activity_mask(
    dec_db: np.ndarray,
    dec_rel_db: np.ndarray,
    *,
    active_db: float = -45.0,
    within_db: float = 18.0,
    attack_ms: float = 300.0,
    release_ms: float = 500.0,
    rate: int = RATE_HZ,
) -> np.ndarray:
    """Boolean activity per frame (see module doc)."""
    q = (dec_db > active_db) & (dec_rel_db > -within_db)
    runs = _runs(q)
    if not runs:
        return np.zeros_like(q)
    # join across short gaps (release), then drop short runs (attack)
    gap = int(round(release_ms * rate / 1000.0))
    joined: list[list[int]] = [list(runs[0])]
    for a, b in runs[1:]:
        if a - joined[-1][1] < gap:
            joined[-1][1] = b
        else:
            joined.append([a, b])
    min_len = int(round(attack_ms * rate / 1000.0))
    out = np.zeros_like(q)
    for a, b in joined:
        if b - a >= min_len:
            out[a:b] = True
    return out


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of True runs."""
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        return []
    d = np.diff(np.concatenate(([0], m.astype(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts.tolist(), ends.tolist()))


def segments_of(mask: np.ndarray, duration_s: float, rate: int = RATE_HZ) -> list[tuple[float, float, int, int]]:
    """(t, d, i0, i1) per active run; frame i stands for [i/rate, (i+1)/rate) clipped to the duration."""
    out = []
    for a, b in _runs(mask):
        t = a / rate
        e = min(b / rate, duration_s)
        if e - t > 1e-9:
            out.append((t, e - t, a, b))
    return out


def agreement(stem_dec_db: np.ndarray, alt_dec_db: np.ndarray) -> np.ndarray:
    """Per-frame agreement of an independent model's level with this stem's level (0..1)."""
    return np.clip((alt_dec_db - stem_dec_db + 15.0) / 9.0, 0.0, 1.0)


@dataclass
class StemStats:
    present: bool
    active_ratio: float
    median_rms_db: float
    peak_db: float
    share_of_mix_db: float
    active_s: float
    n_segments: int
    conf: float
    evidence: list[str] = field(default_factory=list)
    present_energy: bool = False


def stem_stats(
    x: np.ndarray,
    rms_db: np.ndarray,
    mask: np.ndarray,
    mix_energy: float,
    *,
    duration_s: float,
    n_segments: int,
    conf: float,
    evidence: Sequence[str],
    min_present_s: float = 2.0,
    min_conf: float = 0.4,
    rate: int = RATE_HZ,
) -> StemStats:
    a = np.asarray(x, dtype=np.float64)
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    peak_db = max(FLOOR_DB, 20.0 * math.log10(peak)) if peak > 0 else FLOOR_DB
    e = float(np.sum(np.square(a))) / max(1, a.shape[0] if a.ndim == 2 else 1)
    share = 10.0 * math.log10(e / mix_energy) if e > 0 and mix_energy > 0 else FLOOR_DB
    share = max(FLOOR_DB, min(share, 60.0))
    n = mask.shape[0]
    act = int(mask.sum())
    ratio = act / n if n else 0.0
    if act:
        med = float(np.median(rms_db[mask]))
    else:
        nz = rms_db[rms_db > FLOOR_DB]
        med = float(np.median(nz)) if nz.size else FLOOR_DB
    active_s = act / rate
    present_energy = active_s >= min(min_present_s, 0.25 * duration_s) and act > 0
    present = present_energy and conf >= min_conf
    return StemStats(present, ratio, med, peak_db, share, active_s, n_segments, conf, list(evidence), present_energy)


def shared_norm(dbs: Mapping[str, np.ndarray], floor: float = FLOOR_DB) -> tuple[float, float]:
    """p02-p99.5 over the non-floor frames of every stem (one range for all stems)."""
    vals = [v[v > floor] for v in dbs.values()]
    vals = [v for v in vals if v.size]
    if not vals:
        return floor, 0.0
    allv = np.concatenate(vals)
    lo = float(np.percentile(allv, 2.0))
    hi = float(np.percentile(allv, 99.5))
    if hi - lo < 1e-6:
        hi = lo + 1.0
    return lo, hi
