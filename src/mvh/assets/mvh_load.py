"""mvh_load.py - loader and helpers for an mv-harness song folder (contract v1.0.0-rc.2). numpy only.

The same API as ``lib/mvh.js`` in snake_case (options become keyword arguments); the semantics are
defined by ``mvh.contract.conventions`` (the reference) and docs/CONTRACT.md section 9. This file is
copied into every song folder (``lib/mvh_load.py``), so it must not import mvh::

    from mvh_load import load, frame_of, time_of
    song = load("out/my-song")
    song.curve("bands.bass").frame(n, {"fps": 24})
    song.events("cues").next(t, min_tier=2)
    song.viz_state(t, {"fps": 30})          # the viz/js/audio.js fields, from offline data

Every time is in seconds from the first sample of audio/mix.flac. A frame rule ``fr`` is
``{"fps", "frame0": 0, "early": False}``, a number, or ``[num, den]`` (e.g. ``[24000, 1001]``).
Helpers never return NaN.
"""

from __future__ import annotations

import bisect
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

VERSION = "1.0.0-rc.2"
CONTRACT_VERSION = "1.0.0-rc.2"
EPS = 1e-9
POLICIES = ("linear", "mean", "max", "hold")
CURVE_RATE_HZ = 100
SUB_NAMES = ("", "e", "&", "a")

__all__ = [
    "VERSION",
    "CONTRACT_VERSION",
    "EPS",
    "POLICIES",
    "CURVE_RATE_HZ",
    "SUB_NAMES",
    "VIZ",
    "HELPER_NEEDS",
    "FrameRule",
    "frame_rule",
    "time_of",
    "frame_centre",
    "frame_window",
    "frame_of",
    "frame_count",
    "samples_in_frame",
    "lerp_at",
    "hold_at",
    "nan_aware_at",
    "curve_at",
    "curve_frame",
    "flash_samples",
    "beat_pos",
    "beat_phase",
    "bar_phase",
    "count_at",
    "event_at",
    "event_all_at",
    "event_next",
    "event_prev",
    "event_between",
    "event_in_frame",
    "singer_at",
    "vocal_at",
    "texture_layout",
    "pack_texture",
    "texture_sample",
    "pulse",
    "osc",
    "spectrum_rows",
    "Curve",
    "Events",
    "Song",
    "load",
]

_LN100 = math.log(100.0)
_DEFAULT_IBI = 0.5


def _num(t: Any, what: str = "t") -> float:
    if (
        isinstance(t, bool)
        or not isinstance(t, (int, float, np.integer, np.floating))
        or not math.isfinite(float(t))
    ):
        raise TypeError(f"mvh: {what} must be a finite number, got {t!r}")
    return float(t)


def _frac(x: float) -> float:
    return x - math.floor(x)


def _clamp(v: float, a: float, b: float) -> float:
    return a if v < a else (b if v > b else v)


def _js_round(x: float) -> int:
    """JavaScript Math.round (half up), used where the JS side rounds."""
    return math.floor(x + 0.5)


def _finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))


class _Times:
    """Sorted item times and the longest duration (cached per items list by Events)."""

    __slots__ = ("times", "max_d")

    def __init__(self, items: Sequence[Mapping[str, Any]]):
        self.times = [float(it["t"]) for it in items]
        md = 0.0
        for it in items:
            d = it.get("d")
            if d is not None and d > md:
                md = float(d)
        self.max_d = md


def _times(items, cache: _Times | None) -> _Times:
    return cache if cache is not None else _Times(items)


# ============================================================================================ frames
class FrameRule:
    """``{fps, frame0 = 0, early = False}``; fps is a number (literal) or ``[num, den]``."""

    __slots__ = ("num", "den", "frame0", "early")

    def __init__(self, fps: float | Sequence[float], frame0: int = 0, early: bool = False):
        if isinstance(fps, (list, tuple)):
            num, den = float(fps[0]), float(fps[1])
        else:
            num, den = float(fps), 1.0
        if not (num > 0 and den > 0) or not (math.isfinite(num) and math.isfinite(den)):
            raise ValueError(f"mvh: fps must be positive: {fps!r}")
        if frame0 is None:
            frame0 = 0
        if int(frame0) != frame0:
            raise ValueError("mvh: frame0 must be an integer")
        self.num, self.den, self.frame0, self.early = num, den, int(frame0), bool(early)

    @property
    def fps(self) -> float:
        return self.num / self.den

    @property
    def half(self) -> float:
        return 0.5 * self.den / self.num

    def __repr__(self) -> str:
        return f"FrameRule({self.num:g}/{self.den:g}, frame0={self.frame0}, early={self.early})"


def frame_rule(fr: Any) -> FrameRule:
    """Accept a FrameRule, a ``{fps, frame0, early}`` mapping, a number, or ``[num, den]``."""
    if isinstance(fr, FrameRule):
        return fr
    if fr is None:
        raise TypeError("mvh: a frame rule {fps, frame0, early} is required")
    if isinstance(fr, Mapping):
        return FrameRule(fr["fps"], fr.get("frame0", 0), fr.get("early", False))
    return FrameRule(fr)


def time_of(n: int, fr) -> float:
    """t_n = (n - frame0) * den / num: the nominal time of video frame n."""
    r = frame_rule(fr)
    return (n - r.frame0) * r.den / r.num


def frame_centre(n: int, fr) -> float:
    """Sampling instant of frame n: t_n (centred) or t_n + 1/(2F) (early)."""
    r = frame_rule(fr)
    return time_of(n, r) + (r.half if r.early else 0.0)


def frame_window(n: int, fr) -> tuple[float, float]:
    r = frame_rule(fr)
    c = frame_centre(n, r)
    return c - r.half, c + r.half


def frame_of(t: float, fr) -> int:
    """The frame whose window contains t."""
    r = frame_rule(fr)
    return math.floor(_num(t) * r.num / r.den + (0.0 if r.early else 0.5) + EPS) + r.frame0


def frame_count(duration_s: float, fr) -> int:
    """Frames n = frame0 .. frame0+count-1 with time_of(n) < duration."""
    r = frame_rule(fr)
    return max(0, math.ceil(_num(duration_s, "duration") * r.num / r.den - EPS))


# ============================================================================================ curves
def samples_in_frame(n: int, fr, rate: float, n_samples: int) -> range:
    r = frame_rule(fr)
    a, b = frame_window(n, r)
    lo = max(0, math.floor(a * rate) - 1)
    hi = min(n_samples, math.ceil(b * rate) + 2)
    first = last = None
    for i in range(lo, hi):
        if frame_of(i / rate, r) == n:
            if first is None:
                first = i
            last = i
    if first is None:
        return range(0, 0)
    return range(first, last + 1)


def lerp_at(v: Sequence[float], x: float) -> float:
    n = len(v)
    if n == 0:
        return 0.0
    if x <= 0:
        return float(v[0])
    if x >= n - 1:
        return float(v[n - 1])
    i = math.floor(x)
    f = x - i
    a, b = float(v[i]), float(v[i + 1])
    return a + (b - a) * f


def _nearest(n: int, x: float) -> int:
    k = math.floor(x + 0.5 + EPS)
    return 0 if k < 0 else (n - 1 if k > n - 1 else k)


def hold_at(v: Sequence[float], x: float) -> float:
    if len(v) == 0:
        return 0.0
    return float(v[_nearest(len(v), x)])


def nan_aware_at(v: Sequence[float], x: float) -> float:
    """NaN-aware pitch sampling (NaN = unvoiced); NaN only when no sample is voiced."""
    n = len(v)
    if n == 0:
        return math.nan
    xc = 0.0 if x < 0 else (float(n - 1) if x > n - 1 else x)
    i = math.floor(xc)
    j = min(i + 1, n - 1)
    a, b = float(v[i]), float(v[j])
    if _finite(a) and _finite(b):
        return a + (b - a) * (xc - i)
    k = _nearest(n, x)
    if _finite(float(v[k])):
        return float(v[k])
    for m in range(k - 1, -1, -1):
        if _finite(float(v[m])):
            return float(v[m])
    for m in range(k + 1, n):
        if _finite(float(v[m])):
            return float(v[m])
    return math.nan


def _check_policy(policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(f"mvh: unknown resample policy {policy!r}")


def curve_at(
    v: Sequence[float], t: float, rate: float = CURVE_RATE_HZ, policy: str = "linear", nan_aware: bool = False
) -> float:
    """Point value at t: lerp (linear/mean/max), nearest (hold), NaN-aware for pitch. Never NaN."""
    _check_policy(policy)
    x = _num(t) * rate
    if nan_aware:
        y = nan_aware_at(v, x)
    elif policy == "hold":
        y = hold_at(v, x)
    else:
        y = lerp_at(v, x)
    return 0.0 if math.isnan(y) else y


def curve_frame(
    v: Sequence[float],
    n: int,
    fr,
    rate: float = CURVE_RATE_HZ,
    policy: str = "linear",
    nan_aware: bool = False,
) -> float:
    """Value of video frame n under the resample policy. Never NaN."""
    _check_policy(policy)
    r = frame_rule(fr)
    c = frame_centre(n, r)
    x = c * rate
    if policy in ("mean", "max"):
        idx = samples_in_frame(n, r, rate, len(v))
        vals = [float(v[i]) for i in idx]
        if nan_aware:
            vals = [a for a in vals if _finite(a)]
        if vals:
            return (math.fsum(vals) / len(vals)) if policy == "mean" else max(vals)
        return curve_at(v, c, rate, "linear", nan_aware)
    if nan_aware:
        y = nan_aware_at(v, x)
        return 0.0 if math.isnan(y) else y
    return hold_at(v, x) if policy == "hold" else lerp_at(v, x)


def flash_samples(t_event: float, rate: float = CURVE_RATE_HZ) -> tuple[int, int]:
    x = t_event * rate
    k = round(x)
    if abs(x - k) < EPS:
        return k, k
    return math.floor(x), math.ceil(x)


# ============================================================================================ beats
def _ibi(beats, i: int) -> float:
    if len(beats) < 2:
        return _DEFAULT_IBI
    i = max(0, min(i, len(beats) - 2))
    return float(beats[i + 1]["t"]) - float(beats[i]["t"])


def _in_pulse(b) -> bool:
    v = b.get("in_pulse")
    return True if v is None else bool(v)


def beat_pos(t: float, beats: Sequence[Mapping[str, Any]], _cache: _Times | None = None) -> dict[str, Any]:
    """Fractional beat index at t: {value, in_pulse}; extended at the first / last interval outside."""
    t = _num(t)
    n = len(beats)
    if n == 0:
        return {"value": t / _DEFAULT_IBI, "in_pulse": False}
    times = _times(beats, _cache).times
    if t < times[0]:
        return {"value": (t - times[0]) / _ibi(beats, 0), "in_pulse": False}
    if t >= times[-1]:
        return {"value": (n - 1) + (t - times[-1]) / _ibi(beats, n - 2), "in_pulse": False}
    i = bisect.bisect_right(times, t) - 1
    val = i + (t - times[i]) / (times[i + 1] - times[i])
    return {"value": val, "in_pulse": _in_pulse(beats[i]) and _in_pulse(beats[i + 1])}


def beat_phase(t: float, beats, _cache: _Times | None = None) -> dict[str, Any]:
    p = beat_pos(t, beats, _cache)
    return {"value": _frac(p["value"]), "in_pulse": p["in_pulse"]}


def _beat_meta(k: int, beats) -> tuple[int, int]:
    n = len(beats)
    if n == 0:
        return (k % 4) + 1, 4
    if 0 <= k < n:
        return int(beats[k]["beat_in_bar"]), int(beats[k]["beats_in_bar"])
    ref = beats[0] if k < 0 else beats[n - 1]
    kref = 0 if k < 0 else n - 1
    nb = int(ref["beats_in_bar"])
    return ((int(ref["beat_in_bar"]) - 1 + (k - kref)) % nb) + 1, nb


def bar_phase(t: float, beats, _cache: _Times | None = None) -> dict[str, Any]:
    p = beat_pos(t, beats, _cache)
    k = math.floor(p["value"])
    bib, nb = _beat_meta(k, beats)
    return {"value": ((bib - 1) + _frac(p["value"])) / nb, "in_pulse": p["in_pulse"]}


def count_at(
    t: float, beats, counts: Sequence[Mapping[str, Any]], _cache: _Times | None = None
) -> dict[str, Any]:
    """count(t) -> {eight_id, count, sub, phase, accent, partial, lead_in, in_pulse}."""
    p = beat_pos(t, beats, _cache)
    pv = p["value"]
    sub = min(3, math.floor(4 * _frac(pv)))
    hit = None
    for c in counts:
        s = float(c["start_beat"])
        if s <= pv < s + float(c["len"]) and (hit is None or s >= float(hit["start_beat"])):
            hit = c
    if hit is None:
        return {
            "eight_id": None,
            "count": None,
            "sub": sub,
            "phase": None,
            "accent": 0.0,
            "partial": False,
            "lead_in": False,
            "in_pulse": p["in_pulse"],
        }
    k = math.floor(pv - float(hit["start_beat"]))
    acc = hit.get("accents") or []
    fc = hit.get("first_count")
    return {
        "eight_id": hit["id"],
        "count": int(1 if fc is None else fc) + k,
        "sub": sub,
        "phase": (pv - float(hit["start_beat"])) / float(hit["len"]),
        "accent": float(acc[k]) if k < len(acc) else 0.0,
        "partial": bool(hit.get("partial", False)),
        "lead_in": bool(hit.get("lead_in", False)),
        "in_pulse": p["in_pulse"],
    }


# ============================================================================================ events
def event_at(
    items: Sequence[Mapping[str, Any]], t: float, _cache: _Times | None = None
) -> dict[str, Any] | None:
    """{item, progress, t_in, t_left} for the latest-starting item with d > 0 containing t, or None."""
    t = _num(t)
    c = _times(items, _cache)
    times, reach = c.times, c.max_d + 1e-9 * (1 + abs(t))
    best = None
    i = bisect.bisect_right(times, t) - 1
    while i >= 0 and t - times[i] <= reach:
        it = items[i]
        d = it.get("d")
        if d is not None and d > 0 and times[i] <= t < times[i] + float(d):
            best = it
            break
        i -= 1
    if best is None:
        return None
    t0, d = float(best["t"]), float(best["d"])
    return {"item": best, "progress": (t - t0) / d, "t_in": t - t0, "t_left": t0 + d - t}


def event_all_at(items: Sequence[Mapping[str, Any]], t: float, _cache: _Times | None = None) -> list:
    """Every item with d > 0 whose [t, t + d) contains t, sorted by t (ties: file order)."""
    t = _num(t)
    c = _times(items, _cache)
    times, reach = c.times, c.max_d + 1e-9 * (1 + abs(t))
    out = []
    i = bisect.bisect_right(times, t) - 1
    while i >= 0 and t - times[i] <= reach:
        it = items[i]
        d = it.get("d")
        if d is not None and d > 0 and times[i] <= t < times[i] + float(d):
            out.append(it)
        i -= 1
    out.reverse()
    return out


def _tier_ok(it, min_tier) -> bool:
    return min_tier is None or (it.get("tier") is not None and int(it["tier"]) <= int(min_tier))


def event_next(items, t: float, min_tier: int | None = None, _cache: _Times | None = None):
    """First item with item.t > t (strictly after); min_tier keeps tiers 1..min_tier."""
    t = _num(t)
    times = _times(items, _cache).times
    for i in range(bisect.bisect_right(times, t), len(items)):
        if _tier_ok(items[i], min_tier):
            return items[i]
    return None


def event_prev(items, t: float, min_tier: int | None = None, _cache: _Times | None = None):
    """Last item with item.t <= t (at or before)."""
    t = _num(t)
    times = _times(items, _cache).times
    for i in range(bisect.bisect_right(times, t) - 1, -1, -1):
        if _tier_ok(items[i], min_tier):
            return items[i]
    return None


def event_between(
    items, t0: float, t1: float, min_tier: int | None = None, _cache: _Times | None = None
) -> list:
    """Items with t0 <= item.t < t1."""
    t0, t1 = _num(t0, "t0"), _num(t1, "t1")
    times = _times(items, _cache).times
    a, b = bisect.bisect_left(times, t0), bisect.bisect_left(times, t1)
    return [items[i] for i in range(a, b) if _tier_ok(items[i], min_tier)]


def _first_true(n: int, pred: Callable[[int], bool]) -> int:
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if pred(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


def event_in_frame(items, n: int, fr, min_tier: int | None = None, _cache: _Times | None = None) -> list:
    """Items whose t falls in frame n: frame_of(item.t) == n."""
    r = frame_rule(fr)
    times = _times(items, _cache).times
    out = []
    i = _first_true(len(times), lambda k: frame_of(times[k], r) >= n)
    while i < len(times) and frame_of(times[i], r) == n:
        if _tier_ok(items[i], min_tier):
            out.append(items[i])
        i += 1
    return out


def _id_number(s: str | None) -> int:
    if not s:
        return 1 << 30
    k = len(s)
    while k > 0 and s[k - 1].isdigit():
        k -= 1
    return int(s[k:]) if k < len(s) else 1 << 30


def _contains(it: Mapping[str, Any], t: float) -> bool:
    d = it.get("d")
    return d is not None and d > 0 and float(it["t"]) <= t < float(it["t"]) + float(d)


def singer_at(
    t: float, singing: Sequence[Mapping[str, Any]], mouth_open: Callable[[str | None, float], float]
) -> list[dict[str, Any]]:
    """Singing items containing t, lead before backing, then voice number, then line_id; one entry per
    (character, voice) (the first in that order; W3C-5)."""
    t = _num(t)
    hits = [it for it in singing if _contains(it, t)]
    hits.sort(
        key=lambda it: (
            0 if it.get("lead_backing") == "lead" else 1,
            _id_number(it.get("voice_id")) if it.get("voice_id") else 1 << 30,
            it.get("line_id") or "",
        )
    )
    seen: set[tuple[Any, Any]] = set()
    uniq = []
    for it in hits:
        k = (it.get("character_id"), it.get("voice_id"))
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    hits = uniq
    return [
        {
            "character_id": it.get("character_id"),
            "voice_id": it.get("voice_id"),
            "lead_backing": it.get("lead_backing"),
            "line_id": it.get("line_id"),
            "mouth_open": float(mouth_open(it.get("voice_id"), t)),
        }
        for it in hits
    ]


def vocal_at(
    t: float,
    ch: Mapping[str, Sequence[float]],
    rate: float = CURVE_RATE_HZ,
    phrases: Sequence[Mapping[str, Any]] = (),
    notes: Sequence[Mapping[str, Any]] = (),
    _phrase_cache: _Times | None = None,
    _note_cache: _Times | None = None,
) -> dict[str, Any]:
    """{voiced, midi, hz, conf, pitch01, phrase_id, note}; never NaN."""
    x = _num(t) * rate
    empty: list[float] = []
    voiced = hold_at(ch.get("vocal.voiced", empty), x) >= 0.5
    midi = nan_aware_at(ch.get("vocal.midi", empty), x)
    hz = nan_aware_at(ch.get("vocal.f0_hz", empty), x)
    ph = event_at(phrases, t, _phrase_cache)
    nt = event_at(notes, t, _note_cache)
    return {
        "voiced": voiced,
        "midi": 0.0 if math.isnan(midi) else midi,
        "hz": 0.0 if math.isnan(hz) else hz,
        "conf": lerp_at(ch.get("vocal.conf", empty), x),
        "pitch01": lerp_at(ch.get("vocal.pitch01", empty), x),
        "phrase_id": ph["item"].get("id") if ph else None,
        "note": nt["item"] if nt else None,
    }


# ============================================================================================ textures
def texture_layout(lengths: Sequence[int], width: int = 1024) -> list[dict[str, int]]:
    out, row = [], 0
    for n in lengths:
        rows = max(1, -(-int(n) // width))
        out.append({"row0": row, "rows": rows, "n": int(n), "width": width})
        row += rows
    return out


def pack_texture(
    channels: Sequence[Sequence[float]], width: int = 1024
) -> tuple[np.ndarray, int, list[dict]]:
    """(data float32 row-major [height x width] flattened, height, layout); padding repeats the last value."""
    lay = texture_layout([len(v) for v in channels], width)
    height = sum(lo["rows"] for lo in lay)
    data = np.zeros(height * width, dtype=np.float32)
    for v, lo in zip(channels, lay):
        a = np.asarray(v, dtype=np.float32).reshape(-1)
        n = a.size
        block = data[lo["row0"] * width : (lo["row0"] + lo["rows"]) * width]
        block[:n] = a
        block[n:] = a[-1] if n else 0.0
    return data, height, lay


def texture_sample(
    data: Sequence[float],
    lay: Mapping[str, int],
    t: float,
    rate: float = CURVE_RATE_HZ,
    policy: str = "linear",
) -> float:
    """What mvhCurve (lib/mvh.glsl) computes: manual lerp over the wrapped texels (nearest for hold)."""
    n, w, row0 = lay["n"], lay["width"], lay["row0"]

    def texel(i: int) -> float:
        return float(data[(row0 + i // w) * w + i % w])

    x = _num(t) * rate
    if policy == "hold":
        return texel(_nearest(n, x))
    x = 0.0 if x < 0 else (float(n - 1) if x > n - 1 else x)
    i = math.floor(x)
    a, b = texel(i), texel(min(i + 1, n - 1))
    return a + (b - a) * (x - i)


# ============================================================================================ pulse / osc
def _shape(d: float, shape: str) -> float:
    if d < 0:
        return 0.0
    if shape == "exp":
        return math.exp(-_LN100 * d)
    if shape == "linear":
        return max(0.0, 1.0 - d)
    if shape == "smooth":
        return 0.0 if d >= 1 else 1.0 - d * d * (3.0 - 2.0 * d)
    raise ValueError(f"mvh: unknown pulse shape {shape!r}")


def _weight(it) -> float:
    for k in ("strength", "vel"):
        if it.get(k) is not None:
            return float(it[k])
    return 1.0


def pulse(
    t: float,
    items: Sequence[Mapping[str, Any]],
    beats=None,
    attack: float = 0.0,
    decay: float = 0.25,
    unit: str = "s",
    shape: str = "exp",
    _cache: _Times | None = None,
    _beat_cache: _Times | None = None,
) -> float:
    """A 0..1 flash per item: w * g(dist / decay) after it, w * g(dist / attack) before it (attack > 0)."""
    t = _num(t)
    if unit not in ("s", "beats"):
        raise ValueError(f"mvh: unknown pulse unit {unit!r}")
    bs = beats or []

    def dist(a: float, b: float) -> float:
        if unit == "s":
            return b - a
        return beat_pos(b, bs, _beat_cache)["value"] - beat_pos(a, bs, _beat_cache)["value"]

    out = 0.0
    p = event_prev(items, t, None, _cache)
    if p is not None and decay > 0:
        out = max(out, _weight(p) * _shape(dist(float(p["t"]), t) / decay, shape))
    elif p is not None and float(p["t"]) == t:
        out = max(out, _weight(p))
    q = event_next(items, t, None, _cache)
    if q is not None and attack > 0:
        out = max(out, _weight(q) * _shape(dist(t, float(q["t"])) / attack, shape))
    return min(1.0, max(0.0, out))


def osc(
    t: float,
    beats,
    shape: str = "sine",
    period_beats: float = 1.0,
    phase: float = 0.0,
    _cache: _Times | None = None,
) -> float:
    """Beat-locked oscillator in [0, 1], 1 on the beat when phase = 0."""
    x = _frac(beat_pos(t, beats, _cache)["value"] / period_beats + phase)
    if shape == "sine":
        return 0.5 + 0.5 * math.cos(2 * math.pi * x)
    if shape == "saw":
        return 1.0 - x
    if shape == "square":
        return 1.0 if x < 0.5 else 0.0
    if shape == "triangle":
        return 1.0 - 2.0 * min(x, 1.0 - x)
    raise ValueError(f"mvh: unknown osc shape {shape!r}")


def spectrum_rows(t: float, s: float, n_frames: int, rate: float = CURVE_RATE_HZ) -> list[int | None]:
    """Rows of spectrum_window(t, s): k = round(s * rate) + 1 rows, oldest first; None outside [0, n)."""
    end = math.floor(_num(t) * rate + 0.5 + EPS)
    k = int(round(_num(s, "s") * rate)) + 1
    return [i if 0 <= i < n_frames else None for i in range(end - k + 1, end + 1)]


# ==================================================================================== vizState constants
VIZ: dict[str, Any] = {
    "NUM_BANDS": 128,
    "WAVE_LEN": 512,
    "F_MIN": 32,
    "F_MAX": 16000,
    "BEAT_DECAY_S": 0.3,
    "PULSE_DECAY_S": 0.11,
    "PEAK_FALL_PER_S": 0.45,
    "BEAT_STRENGTH_MIN": 0.55,
    "PULSE_STRENGTH_MIN": 0.6,
    "RECENT_BEATS": 8,
    "RECENT_BEAT_EMPTY": -100,
    "HIT_RELEASE": 0.18,
    "HIT_THRESHOLD": 0.35,
    "KICK_GATE_DB": -46,
    "HIT_FLOOR": 0.05,
    "REF_FLOOR": 0.075,
    "REARM_DB": 4,
    "RANGE_T": {"bass": (0.0, 0.25), "mid": (0.25, 0.68), "high": (0.68, 1.0)},
    "BEAT_WINDOW_S": 10,
    "PEAK_WINDOW_S": 2.25,
    "DEFAULT_FPS": 60,
}


def _viz_ranges() -> dict[str, list[int]]:
    ratio = VIZ["F_MAX"] / VIZ["F_MIN"]

    def idx(f: float) -> int:
        return int(
            _clamp(
                _js_round(math.log(f / VIZ["F_MIN"]) / math.log(ratio) * VIZ["NUM_BANDS"]),
                0,
                VIZ["NUM_BANDS"] - 1,
            )
        )

    return {
        "bass": [idx(32), idx(150)],
        "kick": [idx(35), idx(100)],
        "mid": [idx(150), idx(2200)],
        "high": [idx(2200), idx(16000)],
        "flux": [idx(32), idx(260)],
        "fluxMid": [idx(300), idx(2200)],
        "fluxHigh": [idx(2500), idx(14000)],
    }


HELPER_NEEDS: dict[str, list[str]] = {
    "beat_pos": ["events:beats"],
    "beat_phase": ["events:beats"],
    "bar_phase": ["events:beats"],
    "osc": ["events:beats"],
    "pulse": ["events:beats"],
    "count": ["events:beats", "events:counts"],
    "lyric_at": ["lyrics", "events:singing"],
    "vocal_at": ["curves:vocal", "events:vocal_phrases", "events:notes.vocals"],
    "singer_at": ["events:singing", "curves:vocal"],
    "meaning_at": ["events:sections", "meaning"],
    "spectrum_at": ["curves:spectrum128"],
    "spectrum_window": ["curves:spectrum128"],
    "viz_state": [
        "curves:core",
        "curves:spectrum128",
        "events:onsets.bass",
        "events:onsets.mid",
        "events:onsets.high",
    ],
}
_CAMEL = {
    "beatPos": "beat_pos",
    "beatPhase": "beat_phase",
    "barPhase": "bar_phase",
    "lyricAt": "lyric_at",
    "vocalAt": "vocal_at",
    "singerAt": "singer_at",
    "meaningAt": "meaning_at",
    "spectrumAt": "spectrum_at",
    "spectrumWindow": "spectrum_window",
    "vizState": "viz_state",
}
_JSON_FILES = {"lyrics": "lyrics/lyrics.json", "meaning": "meaning/meaning.json"}


def _sorted_by_t(items: list) -> list:
    for i in range(1, len(items)):
        if float(items[i]["t"]) < float(items[i - 1]["t"]):
            return sorted(items, key=lambda it: float(it["t"]))  # stable
    return items


def _read_json(path: Path) -> Any:
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


# ============================================================================================ Curve / Events
class Curve:
    """One curve channel: ``values`` (float32 view), ``rate`` (Hz), ``meta`` (curves/index.json entry)."""

    def __init__(self, cid: str, values: np.ndarray, meta: Mapping[str, Any]):
        self.id = cid
        self.values = values
        self.meta = dict(meta)
        self.rate = float(meta.get("rate_hz") or CURVE_RATE_HZ)
        self.policy = meta.get("resample") or "linear"
        sp = meta.get("special") or {}
        self.nan_aware = sp.get("nan") == "unvoiced"
        self._list = values.astype(np.float64).tolist()  # plain floats: fast scalar indexing

    @property
    def n(self) -> int:
        return len(self._list)

    def at(self, t: float) -> float:
        return curve_at(self._list, t, self.rate, self.policy, self.nan_aware)

    def frame(self, n: int, fr) -> float:
        return curve_frame(self._list, n, fr, self.rate, self.policy, self.nan_aware)

    def __repr__(self) -> str:
        return f"Curve({self.id!r}, n={self.n}, rate={self.rate:g}, policy={self.policy})"


class Events:
    """One events file: ``items`` sorted by t; ``exists`` is False when the file is not in the song folder."""

    def __init__(self, name: str, env: Mapping[str, Any], exists: bool = True):
        self.name = name
        self.exists = exists
        self.kind = env.get("kind")
        self.fields = env.get("fields") or {}
        self.provenance = env.get("provenance") or {}
        self.schema = env.get("schema")
        items = env.get("items")
        self.items: list[dict[str, Any]] = _sorted_by_t(list(items) if isinstance(items, list) else [])
        self._c = _Times(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def at(self, t: float):
        return event_at(self.items, t, self._c)

    def all_at(self, t: float) -> list:
        """Every item whose [t, t + d) contains t (overlapping segments), sorted by t then file order."""
        return event_all_at(self.items, t, self._c)

    def next(self, t: float, min_tier: int | None = None):
        return event_next(self.items, t, min_tier, self._c)

    def prev(self, t: float, min_tier: int | None = None):
        return event_prev(self.items, t, min_tier, self._c)

    def between(self, t0: float, t1: float, min_tier: int | None = None) -> list:
        return event_between(self.items, t0, t1, min_tier, self._c)

    def in_frame(self, n: int, fr, min_tier: int | None = None) -> list:
        return event_in_frame(self.items, n, fr, min_tier, self._c)

    def by_id(self, iid: str):
        return next((it for it in self.items if it.get("id") == iid), None)

    def __repr__(self) -> str:
        return f"Events({self.name!r}, {len(self.items)} items{'' if self.exists else ', missing'})"


# ============================================================================================ Song
class Song:
    """An mv-harness song folder. Everything is read lazily and synchronously; ``ensure`` preloads."""

    def __init__(self, base: Path | str):
        self.base = Path(base)
        if not self.base.is_dir():
            raise FileNotFoundError(f"mvh: not a song folder: {self.base}")
        mp, ip = self.base / "manifest.json", self.base / "curves" / "index.json"
        self.manifest: dict[str, Any] = _read_json(mp) if mp.exists() else {}
        self.index: dict[str, Any] = _read_json(ip) if ip.exists() else {}
        self.index.setdefault("files", {})
        self.index.setdefault("channels", [])
        self._chan = {c["id"]: c for c in self.index["channels"]}
        self._raw: dict[str, Any] = {}
        self._curves: dict[str, Curve] = {}
        self._events: dict[str, Events] = {}
        self._lyr: dict[str, Any] | None = None
        self.default_fr = None  # set by load(..., fr=...): the frame rule viz_state uses when called without one
        m = self.manifest
        dur = (m.get("source") or {}).get("duration_s")
        if dur is None:
            dur = (m.get("summary") or {}).get("duration_s")
        if dur is None:
            dur = 0.0
            for f in self.index["files"].values():
                if f.get("rate_hz"):
                    dur = max(dur, f["n_frames"] / f["rate_hz"])
        self.duration = float(dur)

    def __repr__(self) -> str:
        return f"Song({str(self.base)!r}, duration={self.duration:.3f}s)"

    # ------------------------------------------------------------------ resources
    @property
    def event_names(self) -> list[str]:
        out = []
        for f in self.manifest.get("files") or []:
            if f.get("kind") == "events":
                out.append(f.get("events") or f["path"].rsplit("/", 1)[-1].removesuffix(".json"))
        return out

    @property
    def channel_ids(self) -> list[str]:
        return [c["id"] for c in self.index["channels"]]

    def has_curve(self, cid: str) -> bool:
        return cid in self._chan

    def _events_path(self, name: str) -> str:
        for f in self.manifest.get("files") or []:
            if f.get("kind") == "events" and (
                f.get("events") == name or f.get("path") == f"events/{name}.json"
            ):
                return f["path"]
        if name in ("visemes", "phonemes"):
            return f"lipsync/{name}.json"
        return f"events/{name}.json"

    def _key_info(self, key: str) -> tuple[str | None, str]:
        if key.startswith("curves:"):
            f = self.index["files"].get(key[7:])
            return (f["path"] if f else None), "bytes"
        if key.startswith("events:"):
            return self._events_path(key[7:]), "json"
        if key in _JSON_FILES:
            return _JSON_FILES[key], "json"
        raise ValueError(f"mvh: unknown resource {key!r}")

    def resolve(self, spec: str | Iterable[str]) -> list[str]:
        if not isinstance(spec, str):
            out: list[str] = []
            for s in spec:
                for k in self.resolve(s):
                    if k not in out:
                        out.append(k)
            return out
        s = spec
        if s == "all":
            return self.resolve("curves:*") + self.resolve("events:*") + ["lyrics", "meaning"]
        if s == "curves:*":
            return [f"curves:{f}" for f in self.index["files"]]
        if s == "events:*":
            return [f"events:{n}" for n in self.event_names]
        if s == "spectrum":
            return ["curves:spectrum128"]
        if s.startswith("helper:"):
            h = _CAMEL.get(s[7:], s[7:])
            if h not in HELPER_NEEDS:
                raise ValueError(f"mvh: unknown helper {h!r}")
            return list(HELPER_NEEDS[h])
        if s.startswith(("curves:", "events:")) or s in _JSON_FILES:
            return [s]
        if s in self.index["files"]:
            return [f"curves:{s}"]
        if s in self._chan:
            return [f"curves:{self._chan[s]['file']}"]
        return [f"events:{s}"]

    def _get(self, key: str) -> Any:
        if key in self._raw:
            return self._raw[key]
        rel, kind = self._key_info(key)
        val = None
        if rel is not None:
            p = self.base.joinpath(*rel.split("/"))
            if p.is_file():
                val = _read_json(p) if kind == "json" else p.read_bytes()
        self._raw[key] = val
        return val

    def ensure(self, spec: str | Iterable[str]) -> None:
        """Preload resources (reads are lazy and synchronous anyway; this only moves the I/O earlier)."""
        for k in self.resolve(spec):
            self._get(k)

    def is_loaded(self, spec) -> bool:
        return all(k in self._raw for k in self.resolve(spec))

    # ------------------------------------------------------------------ curves
    def curve(self, cid: str) -> Curve:
        c = self._curves.get(cid)
        if c is not None:
            return c
        meta = self._chan.get(cid)
        if meta is None:
            raise KeyError(f"mvh: unknown curve channel {cid!r} (see curves/index.json)")
        f = self.index["files"].get(meta["file"])
        if not f or f.get("dtype") != "f32le":
            raise ValueError(f"mvh: {cid!r} is not a float curve (use spectrum_at / spectrum_window)")
        buf = self._get(f"curves:{meta['file']}")
        if buf is None:
            raise FileNotFoundError(f"mvh: curve file {f['path']} is missing")
        v = np.frombuffer(buf, dtype="<f4", count=int(meta["n"]), offset=int(meta["offset_bytes"]))
        c = Curve(cid, v, meta)
        self._curves[cid] = c
        return c

    def _curve_or_none(self, cid: str) -> Curve | None:
        return self.curve(cid) if cid in self._chan else None

    # ------------------------------------------------------------------ events
    def events(self, name: str) -> Events:
        e = self._events.get(name)
        if e is not None:
            return e
        env = self._get(f"events:{name}")
        e = Events(name, {"items": []}, False) if env is None else Events(name, env, True)
        self._events[name] = e
        return e

    @property
    def beats(self) -> list[dict[str, Any]]:
        return self.events("beats").items

    # ------------------------------------------------------------------ frames
    def frame_count(self, fr) -> int:
        return frame_count(self.duration, fr)

    # ------------------------------------------------------------------ rhythm
    def beat_pos(self, t: float) -> dict[str, Any]:
        b = self.events("beats")
        return beat_pos(t, b.items, b._c)

    def beat_phase(self, t: float) -> dict[str, Any]:
        b = self.events("beats")
        return beat_phase(t, b.items, b._c)

    def bar_phase(self, t: float) -> dict[str, Any]:
        b = self.events("beats")
        return bar_phase(t, b.items, b._c)

    def count(self, t: float) -> dict[str, Any]:
        b = self.events("beats")
        return count_at(t, b.items, self.events("counts").items, b._c)

    def pulse(
        self,
        src: str,
        t: float,
        attack: float = 0.0,
        decay: float = 0.25,
        unit: str = "s",
        shape: str = "exp",
    ) -> float:
        e = self.events(src)
        b = self.events("beats") if unit == "beats" else None
        return pulse(
            t, e.items, b.items if b else None, attack, decay, unit, shape, e._c, b._c if b else None
        )

    def osc(self, t: float, shape: str = "sine", period_beats: float = 1.0, phase: float = 0.0) -> float:
        b = self.events("beats")
        return osc(t, b.items, shape, period_beats, phase, b._c)

    # ------------------------------------------------------------------ words / voices / meaning
    def _lyrics(self) -> dict[str, Any]:
        if self._lyr is not None:
            return self._lyr
        doc = self._get("lyrics")
        lines = _sorted_by_t(list(doc.get("lines") or [])) if isinstance(doc, dict) else []
        words: dict[str, list] = {}
        for w in (doc.get("words") or []) if isinstance(doc, dict) else []:
            words.setdefault(w.get("line_id"), []).append(w)
        words = {k: _sorted_by_t(v) for k, v in words.items()}
        self._lyr = {
            "doc": doc,
            "lines": lines,
            "lines_c": _Times(lines),
            "words": words,
            "words_c": {k: _Times(v) for k, v in words.items()},
        }
        return self._lyr

    def lyric_at(self, t: float) -> dict[str, Any]:
        """{line, word, progress, word_progress}; line joined with singer (character ids) and voice_ids."""
        L = self._lyrics()
        r = event_at(L["lines"], t, L["lines_c"])
        if r is None:
            return {"line": None, "word": None, "progress": None, "word_progress": None}
        lid = r["item"].get("id")
        sung = [s for s in self.events("singing").items if s.get("line_id") == lid]
        sung.sort(key=lambda s: 0 if s.get("lead_backing") == "lead" else 1)  # stable

        def uniq(xs):
            out = []
            for x in xs:
                if x is not None and x not in out:
                    out.append(x)
            return out

        line = dict(r["item"])
        line["singer"] = uniq(s.get("character_id") for s in sung)
        line["voice_ids"] = uniq(s.get("voice_id") for s in sung)
        wr = event_at(L["words"].get(lid, []), t, L["words_c"].get(lid))
        return {
            "line": line,
            "word": wr["item"] if wr else None,
            "progress": r["progress"],
            "word_progress": wr["progress"] if wr else None,
        }

    def vocal_at(self, t: float) -> dict[str, Any]:
        ch = {}
        for cid in ("vocal.voiced", "vocal.midi", "vocal.f0_hz", "vocal.conf", "vocal.pitch01"):
            c = self._curve_or_none(cid)
            if c is not None:
                ch[cid] = c._list
        rate = (
            float(self._chan["vocal.midi"].get("rate_hz") or CURVE_RATE_HZ)
            if "vocal.midi" in self._chan
            else CURVE_RATE_HZ
        )
        ph, nt = self.events("vocal_phrases"), self.events("notes.vocals")
        return vocal_at(t, ch, rate, ph.items, nt.items, ph._c, nt._c)

    def _mouth_open(self, voice: str | None, t: float) -> float:
        cid = (
            f"vocal.mouth_open.{voice}"
            if voice and f"vocal.mouth_open.{voice}" in self._chan
            else "vocal.mouth_open"
        )
        c = self._curve_or_none(cid)
        return curve_at(c._list, t, c.rate, "max") if c is not None else 0.0

    def singer_at(self, t: float) -> list[dict[str, Any]]:
        return singer_at(t, self.events("singing").items, self._mouth_open)

    def meaning_at(self, t: float) -> dict[str, Any]:
        sec = self.events("sections").at(t)
        M = self._get("meaning")
        M = M if isinstance(M, dict) else None
        gdn = list(M.get("do_not") or []) if M else []

        def dedupe(xs):
            out = []
            for x in xs:
                if x not in out:
                    out.append(x)
            return out

        out: dict[str, Any] = {
            "section_id": None,
            "meaning": None,
            "feel": None,
            "emotion": None,
            "palette_hint": [],
            "movement_hint": None,
            "camera_hint": None,
            "characters_present": [],
            "do_not": dedupe(gdn),
            "provenance": None,
            "status": M.get("status") if M else None,
            "field_sources": {},
        }
        if sec is None:
            return out
        out["section_id"] = sec["item"].get("id")
        secs = list(M.get("sections") or []) if M else []
        e = next((s for s in secs if s.get("section_id") == out["section_id"]), None)
        if e is None:
            e = next(
                (
                    s
                    for s in secs
                    if s.get("t0") is not None
                    and s.get("t1") is not None
                    and float(s["t0"]) <= t < float(s["t1"])
                ),
                None,
            )
        if e is None:
            return out
        out.update(
            {
                "meaning": e.get("meaning"),
                "feel": e.get("feel"),
                "emotion": e.get("emotion"),
                "palette_hint": list(e.get("palette_hint") or []),
                "movement_hint": e.get("movement_hint"),
                "camera_hint": e.get("camera_hint"),
                "characters_present": list(e.get("characters_present") or []),
                "do_not": dedupe(gdn + list(e.get("do_not") or [])),
                "provenance": e.get("provenance"),
                # D54: user / draft per field (meaning.json sections[].field_sources)
                "field_sources": dict(e.get("field_sources") or {}) if isinstance(e.get("field_sources"), dict) else {},
            }
        )
        return out

    # ------------------------------------------------------------------ spectrum
    def _spectrum(self) -> dict[str, Any] | None:
        f = self.index["files"].get("spectrum128")
        if not f:
            return None
        buf = self._get("curves:spectrum128")
        if buf is None:
            return None
        n, k = int(f["n_frames"]), int(f.get("n_channels") or 128)
        data = np.frombuffer(buf, dtype=np.uint8, count=n * k).reshape(n, k)
        return {"data": data, "n": n, "k": k, "rate": float(f.get("rate_hz") or CURVE_RATE_HZ)}

    def spectrum_at(self, t: float) -> np.ndarray:
        """uint8[128]: the nearest spectrum row (clamped); u8/255 = viz band value."""
        t = _num(t)
        S = self._spectrum()
        if S is None or S["n"] == 0:
            return np.zeros(S["k"] if S else 128, dtype=np.uint8)
        return S["data"][_nearest(S["n"], t * S["rate"])].copy()

    def spectrum_window(self, t: float, s: float) -> np.ndarray:
        """uint8[k * 128]: k = round(100 s) + 1 rows ending at the nearest row of t, oldest first."""
        S = self._spectrum()
        K = S["k"] if S else 128
        rows = spectrum_rows(t, s, S["n"] if S else 0, S["rate"] if S else CURVE_RATE_HZ)
        out = np.zeros((len(rows), K), dtype=np.uint8)
        for j, r in enumerate(rows):
            if r is not None:
                out[j] = S["data"][r]
        return out.reshape(-1)

    # ------------------------------------------------------------------ textures
    def texture_data(
        self, ids: str | Sequence[str], width: int = 1024, format: str = "r32f", layout: str = "wrap"
    ) -> dict[str, Any]:
        """Whole-song curves wrapped into rows of ``width`` texels: {data, width, height, format, layout}."""
        if layout != "wrap":
            raise ValueError(f"mvh: unknown texture layout {layout!r}")
        if format not in ("r32f", "r8"):
            raise ValueError(f"mvh: unknown texture format {format!r}")
        if int(width) != width or width < 1:
            raise ValueError("mvh: width must be a positive integer")
        lst = [ids] if isinstance(ids, str) else list(ids)
        chans = []
        for cid in lst:
            c = self.curve(cid)
            if not c.nan_aware:
                chans.append(c.values)
            else:
                v = [nan_aware_at(c._list, i) for i in range(c.n)]
                chans.append(np.asarray([0.0 if math.isnan(y) else y for y in v], dtype=np.float32))
        data, height, lay = pack_texture(chans, int(width))
        out_lay = []
        for cid, lo in zip(lst, lay):
            rate = self.curve(cid).rate
            out_lay.append(
                {
                    "id": cid,
                    "row0": lo["row0"],
                    "rows": lo["rows"],
                    "n": lo["n"],
                    "rate": rate,
                    "width": int(width),
                    "info": [rate, lo["n"], int(width), lo["row0"]],
                }
            )
        if format == "r8":
            y = data.astype(np.float64) * 255.0
            y = np.where(np.isnan(y), 0.0, np.clip(y, 0.0, 255.0))
            data = np.floor(y + 0.5).astype(np.uint8)
        return {"data": data, "width": int(width), "height": height, "format": format, "layout": out_lay}

    # ------------------------------------------------------------------ viz_state
    def viz_state(self, t: float, fr=None) -> dict[str, Any]:
        """The viz/js/audio.js AudioEngine fields at the frame containing t.

        The frame rule is mandatory (``fr``, or the song-wide ``load(path, fr=...)``): onset flags, the beat pulse
        and the frame-pooled hit values are computed for ONE video frame, so a renderer at 24/30 fps that were
        silently given 60 fps frames would lose onsets. Use ``fr={"fps": 60}`` for the viz scenes' 60 fps."""
        t = _num(t)
        if fr is None:
            fr = self.default_fr
        if fr is None:
            raise TypeError(
                "viz_state(t, fr) needs a frame rule fr, e.g. {'fps': 30} (or pass fr to load()): onsets and "
                "pulses are computed per video frame"
            )
        r = frame_rule(fr)
        n = frame_of(t, r)
        tc = frame_centre(n, r)

        def fv(cid: str) -> float:
            c = self._curve_or_none(cid)
            return c.frame(n, r) if c is not None else 0.0

        NB = VIZ["NUM_BANDS"]
        st: dict[str, Any] = {"t": tc, "frame": n}
        row = self.spectrum_at(tc)
        bands = (row[:NB].astype(np.float64) / 255.0).astype(np.float32)
        st["bands"] = bands
        st["bandsRaw"] = bands.copy()
        peaks = np.zeros(NB, dtype=np.float32)
        S = self._spectrum()
        if S is not None and S["n"] > 0:
            rows = [j for j in spectrum_rows(tc, VIZ["PEAK_WINDOW_S"], S["n"], S["rate"]) if j is not None]
            pk = bands.astype(np.float64)
            if rows:
                block = S["data"][rows, :NB].astype(np.float64) / 255.0
                fall = np.array([VIZ["PEAK_FALL_PER_S"] * max(0.0, tc - j / S["rate"]) for j in rows])
                pk = np.maximum(pk, (block - fall[:, None]).max(axis=0))
            peaks = np.clip(pk, 0.0, 1.0).astype(np.float32)
        st["peaks"] = peaks
        bb = np.empty(NB * 4, dtype=np.uint8)
        bb[0::4] = row[:NB]
        bb[1::4] = row[:NB]
        bb[2::4] = row[:NB]
        bb[3::4] = 255
        st["bandBytes"] = bb
        st["wave"] = np.zeros(VIZ["WAVE_LEN"], dtype=np.float32)
        st["waveBytes"] = np.full(VIZ["WAVE_LEN"], 128, dtype=np.uint8)

        st["bass"], st["mid"], st["high"] = fv("bands.bass_viz"), fv("bands.mid_viz"), fv("bands.high_viz")
        st["level"] = fv("bands.level")
        st["kick"] = _clamp(fv("hits.kick"), 0.0, 1.0)
        st["kickRaw"] = _clamp(fv("hits.kick_raw"), 0.0, 1.0)
        st["midHit"] = _clamp(fv("hits.mid"), 0.0, 1.0)
        st["highHit"] = _clamp(fv("hits.high"), 0.0, 1.0)
        st["bpm"] = fv("tempo.bpm")

        def fired(items) -> int:
            return _first_true(len(items), lambda i: frame_of(float(items[i]["t"]), r) > n) - 1

        def strength(it) -> float:
            s = it.get("strength")
            return _clamp(1.0 if s is None else float(s), 0.0, 1.0)

        bmin, pmin = VIZ["BEAT_STRENGTH_MIN"], VIZ["PULSE_STRENGTH_MIN"]
        bass = self.events("onsets.bass").items
        kb = fired(bass)
        st["beatCount"] = kb + 1
        st["onset"] = kb >= 0 and frame_of(float(bass[kb]["t"]), r) == n
        st["beatPulse"] = (
            math.exp(-max(0.0, tc - float(bass[kb]["t"])) / VIZ["PULSE_DECAY_S"]) if kb >= 0 else 0.0
        )
        beat = 0.0
        i = kb
        while i >= 0:
            age = max(0.0, tc - float(bass[i]["t"]))
            if age > VIZ["BEAT_WINDOW_S"]:
                break
            amp = bmin + (1 - bmin) * strength(bass[i])
            beat = max(beat, amp * math.exp(-age / VIZ["BEAT_DECAY_S"]))
            i -= 1
        st["beat"] = beat
        nr = VIZ["RECENT_BEATS"]
        rb = np.full(nr, VIZ["RECENT_BEAT_EMPTY"], dtype=np.float32)
        ra = np.zeros(nr, dtype=np.float32)
        kick, kick_raw = self._curve_or_none("hits.kick"), self._curve_or_none("hits.kick_raw")
        for j in range(nr):
            if kb - j < 0:
                break
            it = bass[kb - j]
            tb = float(it["t"])
            amp = bmin + (1 - bmin) * strength(it)
            a = max(kick_raw.at(tb) if kick_raw else 0.0, kick.at(tb) if kick else 0.0, amp * 0.6)
            rb[nr - 1 - j] = tb
            ra[nr - 1 - j] = _clamp(a, 0.0, 1.0)
        st["recentBeats"], st["recentBeatAmp"] = rb, ra
        for band, pkey, okey in (("mid", "midPulse", "midOnset"), ("high", "highPulse", "highOnset")):
            items = self.events(f"onsets.{band}").items
            k = fired(items)
            st[okey] = k >= 0 and frame_of(float(items[k]["t"]), r) == n
            if k < 0:
                st[pkey] = 0.0
                continue
            amp = pmin + (1 - pmin) * strength(items[k])
            st[pkey] = amp * math.exp(-max(0.0, tc - float(items[k]["t"])) / VIZ["PULSE_DECAY_S"])

        st.update(
            {
                "hitRelease": VIZ["HIT_RELEASE"],
                "hitThreshold": VIZ["HIT_THRESHOLD"],
                "kickGateDb": VIZ["KICK_GATE_DB"],
                "hitFloor": VIZ["HIT_FLOOR"],
                "refFloor": VIZ["REF_FLOOR"],
                "rearmDb": VIZ["REARM_DB"],
                "gain": 1.0,
                "sensitivity": 1.0,
                "drive": {"bass": 1.0, "mid": 1.0, "high": 1.0},
                "monitorVolume": 0.6,
                "silentFor": 0.0,
                "active": True,
                "sourceType": "offline",
                "sourceLabel": "mv-harness",
                "ranges": _viz_ranges(),
            }
        )
        return st


def load(base: Path | str, include: str | Iterable[str] | None = None, fr=None) -> Song:
    """Open a song folder; ``include`` preloads resources (everything else is read lazily on first use);
    ``fr`` is the song-wide default frame rule for viz_state."""
    song = Song(base)
    song.default_fr = fr
    if include:
        song.ensure(include)
    return song
