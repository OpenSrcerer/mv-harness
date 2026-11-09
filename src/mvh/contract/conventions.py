"""Reference implementation of the time, frame and sampling rules (PLAN §4.2, §4.4, §4.5).

This module is the *specification in code*. ``lib/mvh.js`` and ``lib/mvh_load.py`` must reproduce
every function here within 1e-6 (integers and booleans exactly), and the golden vectors in
``docs/contract/golden-vectors.json`` are computed with it. Stdlib only (numpy arrays are accepted
wherever a sequence of floats is).

Floating-point recipe (follow the operation order exactly in other languages):

* A frame rate is a pair ``(num, den)``; a plain number ``x`` means ``(x, 1)``. Numbers are taken
  literally: 23.976 is *not* snapped to 24000/1001 (pass ``[24000, 1001]`` for NTSC).
* ``time_of(n) = (n - frame0) * den / num``           (multiply first, then divide)
* ``half    = 0.5 * den / num``                       (half a frame)
* ``centre(n) = time_of(n) + (half if early else 0)``  - the sampling instant of frame n
* ``frame_of(t) = floor(t * num / den + (0 if early else 0.5) + EPS) + frame0``
* ``frame_count(duration) = ceil(duration * num / den - EPS)``  (frames whose time_of(n) < duration)
* curve sample ``i`` of a curve at ``rate`` Hz is centred at ``i / rate`` seconds.
* A curve sample ``i`` belongs to frame ``frame_of(i / rate)`` and an event at ``t`` belongs to frame
  ``frame_of(t)``: one membership rule for curves and events, so a flash and its event share a frame.

EPS = 1e-9 everywhere (in frames for frame_of/frame_count, in samples for hold).
"""
from __future__ import annotations

import bisect
import math
from typing import Any, Callable, Iterable, Mapping, Sequence

EPS = 1e-9
POLICIES = ("linear", "mean", "max", "hold")
CURVE_RATE_HZ = 100

__all__ = [
    "EPS", "POLICIES", "CURVE_RATE_HZ", "FrameRule", "frame_rule", "time_of", "frame_centre", "frame_window",
    "frame_of", "frame_count", "n_curve_frames", "samples_in_frame", "lerp_at", "hold_at", "nan_aware_at",
    "curve_at", "curve_frame", "beat_pos", "beat_phase", "bar_phase", "count_at", "SUB_NAMES",
    "event_at", "event_all_at", "event_next", "event_prev", "merge_cues", "CUE_KIND_PRIORITY", "event_between", "event_in_frame", "singer_at",
    "texture_layout", "texture_data", "texture_sample", "pulse", "osc", "vocal_at", "flash_samples",
    "iter_frames", "spectrum_rows",
]


# --------------------------------------------------------------------------------------------- frames
class FrameRule:
    """``{fps, frame0 = 0, early = False}``; fps is a number or ``[num, den]``."""

    __slots__ = ("num", "den", "frame0", "early")

    def __init__(self, fps: float | Sequence[float], frame0: int = 0, early: bool = False):
        if isinstance(fps, (list, tuple)):
            num, den = float(fps[0]), float(fps[1])
        else:
            num, den = float(fps), 1.0
        if not (num > 0 and den > 0):
            raise ValueError(f"fps must be positive: {fps!r}")
        if int(frame0) != frame0:
            raise ValueError("frame0 must be an integer")
        self.num, self.den, self.frame0, self.early = num, den, int(frame0), bool(early)

    @property
    def fps(self) -> float:
        return self.num / self.den

    @property
    def half(self) -> float:
        return 0.5 * self.den / self.num

    def __repr__(self) -> str:  # pragma: no cover
        return f"FrameRule({self.num:g}/{self.den:g}, frame0={self.frame0}, early={self.early})"


def frame_rule(fr: FrameRule | Mapping[str, Any] | float | Sequence[float]) -> FrameRule:
    """Accept a FrameRule, a ``{fps, frame0, early}`` mapping, a number, or ``[num, den]``."""
    if isinstance(fr, FrameRule):
        return fr
    if isinstance(fr, Mapping):
        return FrameRule(fr["fps"], fr.get("frame0", 0), fr.get("early", False))
    return FrameRule(fr)


def time_of(n: int, fr) -> float:
    """t_n = (n - frame0) / F: the nominal time of video frame n."""
    r = frame_rule(fr)
    return (n - r.frame0) * r.den / r.num


def frame_centre(n: int, fr) -> float:
    """Sampling instant of frame n: t_n (centred rule) or t_n + 1/(2F) (early rule)."""
    r = frame_rule(fr)
    return time_of(n, r) + (r.half if r.early else 0.0)


def frame_window(n: int, fr) -> tuple[float, float]:
    """Half-open window [a, b) of frame n: [t_n - 1/2F, t_n + 1/2F) centred, [t_n, t_n + 1/F) early."""
    r = frame_rule(fr)
    c = frame_centre(n, r)
    return c - r.half, c + r.half


def frame_of(t: float, fr) -> int:
    """The frame whose window contains t (events, curve samples and the playhead all use this)."""
    r = frame_rule(fr)
    return math.floor(t * r.num / r.den + (0.0 if r.early else 0.5) + EPS) + r.frame0


def frame_count(duration_s: float, fr) -> int:
    """Number of frames n = frame0 .. frame0+count-1 with time_of(n) < duration."""
    r = frame_rule(fr)
    return max(0, math.ceil(duration_s * r.num / r.den - EPS))


# --------------------------------------------------------------------------------------------- curves
def n_curve_frames(n_samples: int, sample_rate: int, rate: int = CURVE_RATE_HZ) -> int:
    """Length of every curve at ``rate`` Hz: ceil(n_samples * rate / sample_rate) (integer arithmetic).
    Sample i is centred at i / rate, so samples cover [0, duration)."""
    return -(-int(n_samples) * int(rate) // int(sample_rate))


def samples_in_frame(n: int, fr, rate: float, n_samples: int) -> range:
    """Curve sample indices i in [0, n_samples) with frame_of(i / rate) == n (contiguous)."""
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
    """Linear interpolation at fractional sample position x, clamped to the ends."""
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
    """Step value at fractional position x: the nearest sample (samples are centred)."""
    if len(v) == 0:
        return 0.0
    return float(v[_nearest(len(v), x)])


def _finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))


def nan_aware_at(v: Sequence[float], x: float) -> float:
    """Pitch sampling (vocal.f0_hz, vocal.midi; NaN = unvoiced).

    1. both neighbours floor(x), floor(x)+1 voiced -> linear interpolation;
    2. else the nearest sample if voiced;
    3. else hold: the last voiced sample before the nearest one, else the first voiced one after it;
    4. else NaN (a song with no voiced frame). Helpers turn a final NaN into 0.
    """
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


def curve_at(v: Sequence[float], t: float, rate: float = CURVE_RATE_HZ, policy: str = "linear",
             nan_aware: bool = False) -> float:
    """``song.curve(id).at(t)``: point value at time t.

    linear/mean/max -> linear interpolation; hold -> nearest sample; nan_aware channels -> nan_aware_at.
    Never NaN: a NaN result (no voiced frame at all) becomes 0.0."""
    if policy not in POLICIES:
        raise ValueError(policy)
    x = t * rate
    if nan_aware:
        y = nan_aware_at(v, x)
    elif policy == "hold":
        y = hold_at(v, x)
    else:
        y = lerp_at(v, x)
    return 0.0 if math.isnan(y) else y


def curve_frame(v: Sequence[float], n: int, fr, rate: float = CURVE_RATE_HZ, policy: str = "linear",
                nan_aware: bool = False) -> float:
    """``song.curve(id).frame(n, fr)``: the value of video frame n under the channel's resample policy.

    linear -> lerp at the frame centre; hold -> nearest sample to the centre;
    mean / max -> mean / max of the samples that belong to the frame (``samples_in_frame``);
    when no sample belongs to it (fps > rate) -> lerp at the centre.
    nan_aware: mean/max use voiced (finite) samples only; with none, or for linear/hold, ``nan_aware_at``.
    Never NaN (see curve_at)."""
    if policy not in POLICIES:
        raise ValueError(policy)
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


# --------------------------------------------------------------------------------------------- beats
# A beat item is a mapping with at least: t, beat_index (== position), bar, beat_in_bar, beats_in_bar, in_pulse.
_DEFAULT_IBI = 0.5  # 120 BPM virtual grid when fewer than two beats exist


def _ibi(beats: Sequence[Mapping[str, Any]], i: int) -> float:
    if len(beats) < 2:
        return _DEFAULT_IBI
    i = max(0, min(i, len(beats) - 2))
    return float(beats[i + 1]["t"]) - float(beats[i]["t"])


def beat_pos(t: float, beats: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fractional beat index at t: ``{value, in_pulse}``.

    Inside the grid: i + (t - b_i) / (b_{i+1} - b_i) with b_i <= t < b_{i+1}; in_pulse = both beats in pulse.
    Before the first or from the last beat on, the grid is extended at the first / last inter-beat
    interval (virtual grid) and in_pulse is False. No beats: a 120 BPM grid from t = 0."""
    n = len(beats)
    if n == 0:
        return {"value": t / _DEFAULT_IBI, "in_pulse": False}
    times = [float(b["t"]) for b in beats]
    if t < times[0]:
        return {"value": (t - times[0]) / _ibi(beats, 0), "in_pulse": False}
    if t >= times[-1]:
        return {"value": (n - 1) + (t - times[-1]) / _ibi(beats, n - 2), "in_pulse": False}
    i = bisect.bisect_right(times, t) - 1
    val = i + (t - times[i]) / (times[i + 1] - times[i])
    return {"value": val, "in_pulse": bool(beats[i]["in_pulse"]) and bool(beats[i + 1]["in_pulse"])}


def _frac(x: float) -> float:
    return x - math.floor(x)


def beat_phase(t: float, beats) -> dict[str, Any]:
    """``{value: frac(beat_pos), in_pulse}``; 0 on the beat."""
    p = beat_pos(t, beats)
    return {"value": _frac(p["value"]), "in_pulse": p["in_pulse"]}


def _beat_meta(k: int, beats) -> tuple[int, int]:
    """(beat_in_bar, beats_in_bar) for beat index k, extrapolated modulo the meter outside the grid."""
    n = len(beats)
    if n == 0:
        return (k % 4) + 1, 4
    if 0 <= k < n:
        return int(beats[k]["beat_in_bar"]), int(beats[k]["beats_in_bar"])
    ref = beats[0] if k < 0 else beats[n - 1]
    kref = 0 if k < 0 else n - 1
    nb = int(ref["beats_in_bar"])
    return ((int(ref["beat_in_bar"]) - 1 + (k - kref)) % nb) + 1, nb


def bar_phase(t: float, beats) -> dict[str, Any]:
    """``{value, in_pulse}`` with value = ((beat_in_bar - 1) + frac(beat_pos)) / beats_in_bar, in [0, 1).
    A pickup beat numbered N-1 of N reads (N-2+f)/N: the pickup sits at the end of a virtual bar 0."""
    p = beat_pos(t, beats)
    k = math.floor(p["value"])
    bib, nb = _beat_meta(k, beats)
    return {"value": ((bib - 1) + _frac(p["value"])) / nb, "in_pulse": p["in_pulse"]}


SUB_NAMES = ("", "e", "&", "a")  # sub 0..3 = 16th positions within a count: "1 e & a"


def count_at(t: float, beats, counts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``count(t)`` -> {eight_id, count, sub, phase, accent, partial, lead_in, in_pulse}.

    counts items (events/counts.json): id, start_beat (beat index of count ``first_count``; may be < 0 for
    E000), len (beats), first_count (1, or 5 for the E000 lead-in), accents[len], partial, lead_in.
    The count containing beat_pos p satisfies start_beat <= p < start_beat + len (the latest-starting one wins).
    count = first_count + floor(p - start_beat); sub = floor(4 * frac(p)); phase = (p - start_beat) / len.
    Outside every count (e.g. pickup beats before the lead-in): eight_id/count/phase None, accent 0."""
    p = beat_pos(t, beats)
    pv = p["value"]
    sub = min(3, math.floor(4 * _frac(pv)))
    hit = None
    for c in counts:
        s = float(c["start_beat"])
        if s <= pv < s + float(c["len"]) and (hit is None or s >= float(hit["start_beat"])):
            hit = c
    if hit is None:
        return {"eight_id": None, "count": None, "sub": sub, "phase": None, "accent": 0.0,
                "partial": False, "lead_in": False, "in_pulse": p["in_pulse"]}
    k = math.floor(pv - float(hit["start_beat"]))
    acc = hit.get("accents") or []
    return {
        "eight_id": hit["id"], "count": int(hit.get("first_count", 1)) + k, "sub": sub,
        "phase": (pv - float(hit["start_beat"])) / float(hit["len"]),
        "accent": float(acc[k]) if k < len(acc) else 0.0,
        "partial": bool(hit.get("partial", False)), "lead_in": bool(hit.get("lead_in", False)),
        "in_pulse": p["in_pulse"],
    }


# --------------------------------------------------------------------------------------------- events
# Items are sorted by t (ties: file order). Segment membership is half-open [t, t + d).
def _contains(it: Mapping[str, Any], t: float) -> bool:
    d = it.get("d")
    return d is not None and d > 0 and float(it["t"]) <= t < float(it["t"]) + float(d)


def event_at(items: Sequence[Mapping[str, Any]], t: float) -> dict[str, Any] | None:
    """``events(name).at(t)`` -> {item, progress, t_in, t_left} or None.
    Only items with d > 0 can contain t. With overlaps, the item with the latest start wins
    (ties: the later item in file order)."""
    best = None
    for it in items:
        if _contains(it, t) and (best is None or float(it["t"]) >= float(best["t"])):
            best = it
    if best is None:
        return None
    t0, d = float(best["t"]), float(best["d"])
    return {"item": best, "progress": (t - t0) / d, "t_in": t - t0, "t_left": t0 + d - t}


def event_all_at(items: Sequence[Mapping[str, Any]], t: float) -> list[dict[str, Any]]:
    """``events(name).allAt(t)``: EVERY item with d > 0 whose [t, t + d) contains t, sorted by t (ties: file order).
    ``event_at`` returns only the latest start; overlapping files (duet visemes, voice_spans, chords,
    instruments, stem_activity) need this."""
    return [it for it in items if _contains(it, t)]


def _tier_ok(it, min_tier) -> bool:
    return min_tier is None or ("tier" in it and int(it["tier"]) <= int(min_tier))


def event_next(items, t: float, min_tier: int | None = None):
    """First item with item.t > t (strictly after). ``min_tier``: keep tiers 1..min_tier (1 = most important)."""
    for it in items:
        if float(it["t"]) > t and _tier_ok(it, min_tier):
            return it
    return None


def event_prev(items, t: float, min_tier: int | None = None):
    """Last item with item.t <= t (at or before)."""
    out = None
    for it in items:
        if float(it["t"]) <= t:
            if _tier_ok(it, min_tier):
                out = it
        else:
            break
    return out


def event_between(items, t0: float, t1: float, min_tier: int | None = None) -> list:
    """Items with t0 <= item.t < t1."""
    return [it for it in items if t0 <= float(it["t"]) < t1 and _tier_ok(it, min_tier)]


def event_in_frame(items, n: int, fr, min_tier: int | None = None) -> list:
    """Items whose t falls in frame n: frame_of(item.t) == n."""
    r = frame_rule(fr)
    return [it for it in items if frame_of(float(it["t"]), r) == n and _tier_ok(it, min_tier)]


def singer_at(t: float, singing: Sequence[Mapping[str, Any]],
              mouth_open: Callable[[str | None, float], float]) -> list[dict[str, Any]]:
    """``singerAt(t)``: every events/singing.json item containing t, ordered lead before backing, then by
    voice number, then line_id. ``mouth_open(voice_id, t)`` reads ``vocal.mouth_open.<voice_id>`` when that
    channel exists, else ``vocal.mouth_open``."""
    from .ids import id_number  # local: keep module import light
    hits = [it for it in singing if _contains(it, t)]
    hits.sort(key=lambda it: (0 if it.get("lead_backing") == "lead" else 1,
                              id_number(it["voice_id"]) if it.get("voice_id") else 1 << 30,
                              it.get("line_id") or ""))
    return [{"character_id": it.get("character_id"), "voice_id": it.get("voice_id"),
             "lead_backing": it.get("lead_backing"), "line_id": it.get("line_id"),
             "mouth_open": float(mouth_open(it.get("voice_id"), t))} for it in hits]


# --------------------------------------------------------------------------------------------- vocal
def vocal_at(t: float, ch: Mapping[str, Sequence[float]], rate: float = CURVE_RATE_HZ,
             phrases: Sequence[Mapping[str, Any]] = (), notes: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """``vocalAt(t)`` -> {voiced, midi, hz, conf, pitch01, phrase_id, note}; never NaN.
    ch: vocal.midi, vocal.f0_hz (NaN unvoiced), vocal.voiced (0/1), vocal.conf, vocal.pitch01.
    voiced = vocal.voiced at the nearest sample >= 0.5; midi/hz held through gaps (nan_aware_at);
    phrase_id / note from events vocal_phrases / notes.vocals (event_at)."""
    x = t * rate
    voiced = hold_at(ch["vocal.voiced"], x) >= 0.5
    midi = nan_aware_at(ch["vocal.midi"], x)
    hz = nan_aware_at(ch["vocal.f0_hz"], x)
    ph = event_at(phrases, t)
    nt = event_at(notes, t)
    return {"voiced": voiced, "midi": 0.0 if math.isnan(midi) else midi, "hz": 0.0 if math.isnan(hz) else hz,
            "conf": lerp_at(ch["vocal.conf"], x), "pitch01": lerp_at(ch["vocal.pitch01"], x),
            "phrase_id": ph["item"].get("id") if ph else None, "note": nt["item"] if nt else None}


# --------------------------------------------------------------------------------------------- textures
def texture_layout(lengths: Sequence[int], width: int = 1024) -> list[dict[str, int]]:
    """Wrap layout: channel c occupies rows [row0, row0 + rows) with rows = ceil(n / width), stacked in order."""
    out, row = [], 0
    for n in lengths:
        rows = max(1, -(-int(n) // width))
        out.append({"row0": row, "rows": rows, "n": int(n), "width": width})
        row += rows
    return out


def texture_data(channels: Sequence[Sequence[float]], width: int = 1024) -> tuple[list[float], int, list[dict]]:
    """``textureData(ids, {layout: 'wrap', width})`` -> (data row-major [height x width], height, layout).
    texel(c, i) = data[(row0_c + i // width) * width + i % width] = v_c[i]; padding repeats the last value."""
    lay = texture_layout([len(v) for v in channels], width)
    height = sum(ly["rows"] for ly in lay)
    data = [0.0] * (height * width)
    for v, ly in zip(channels, lay):
        n = len(v)
        last = float(v[n - 1]) if n else 0.0
        for k in range(ly["rows"] * width):
            data[ly["row0"] * width + k] = float(v[k]) if k < n else last
    return data, height, lay


def texture_sample(data: Sequence[float], lay: Mapping[str, int], t: float, rate: float = CURVE_RATE_HZ,
                   policy: str = "linear") -> float:
    """What ``mvhCurve(tex, t, info)`` in lib/mvh.glsl computes (manual interpolation, r32f):
    x = clamp(t * rate, 0, n - 1); i = floor(x); f = x - i; texel(i) + (texel(min(i+1, n-1)) - texel(i)) * f.
    For hold channels: texel(nearest). Equals curve_at for non-NaN channels."""
    n, w, row0 = lay["n"], lay["width"], lay["row0"]

    def texel(i: int) -> float:
        return float(data[(row0 + i // w) * w + i % w])

    x = t * rate
    if policy == "hold":
        return texel(_nearest(n, x))
    x = 0.0 if x < 0 else (float(n - 1) if x > n - 1 else x)
    i = math.floor(x)
    a, b = texel(i), texel(min(i + 1, n - 1))
    return a + (b - a) * (x - i)


# --------------------------------------------------------------------------------------------- pulse / osc
_LN100 = math.log(100.0)


def _shape(d: float, shape: str) -> float:
    """Decay curve g(d) for d >= 0 (d in units of the decay length); g(0) = 1."""
    if d < 0:
        return 0.0
    if shape == "exp":
        return math.exp(-_LN100 * d)           # 0.01 at d = 1, continues afterwards
    if shape == "linear":
        return max(0.0, 1.0 - d)
    if shape == "smooth":
        return 0.0 if d >= 1 else 1.0 - d * d * (3.0 - 2.0 * d)
    raise ValueError(shape)


def pulse(t: float, items: Sequence[Mapping[str, Any]], beats=None, attack: float = 0.0, decay: float = 0.25,
          unit: str = "s", shape: str = "exp") -> float:
    """``pulse(src, t, {attack, decay, unit, shape})``: a flash per event of ``src`` (an events name).

    Distances are seconds (unit 's') or beats (unit 'beats': differences of beat_pos values).
    Each item contributes w * g(dist / decay) after its time and w * g(dist / attack) before it (attack > 0),
    with w = item.strength, else item.vel, else 1. The result is the maximum over the last item at or
    before t and the first item after t, clamped to [0, 1]. Defaults: attack 0, decay 0.25, 's', 'exp'."""
    if unit not in ("s", "beats"):
        raise ValueError(unit)

    def dist(a: float, b: float) -> float:
        if unit == "s":
            return b - a
        return beat_pos(b, beats or [])["value"] - beat_pos(a, beats or [])["value"]

    def w(it) -> float:
        for k in ("strength", "vel"):
            if it.get(k) is not None:
                return float(it[k])
        return 1.0

    out = 0.0
    p = event_prev(items, t)
    if p is not None and decay > 0:
        out = max(out, w(p) * _shape(dist(float(p["t"]), t) / decay, shape))
    elif p is not None and float(p["t"]) == t:
        out = max(out, w(p))
    q = event_next(items, t)
    if q is not None and attack > 0:
        out = max(out, w(q) * _shape(dist(t, float(q["t"])) / attack, shape))
    return min(1.0, max(0.0, out))


def osc(t: float, beats, shape: str = "sine", period_beats: float = 1.0, phase: float = 0.0) -> float:
    """``osc(t, {shape, periodBeats, phase})`` in [0, 1], 1 on the beat when phase = 0.
    x = frac(beat_pos / period_beats + phase); sine 0.5 + 0.5 cos(2 pi x); saw 1 - x;
    square x < 0.5 ? 1 : 0; triangle 1 - 2 min(x, 1 - x)."""
    x = _frac(beat_pos(t, beats)["value"] / period_beats + phase)
    if shape == "sine":
        return 0.5 + 0.5 * math.cos(2 * math.pi * x)
    if shape == "saw":
        return 1.0 - x
    if shape == "square":
        return 1.0 if x < 0.5 else 0.0
    if shape == "triangle":
        return 1.0 - 2.0 * min(x, 1.0 - x)
    raise ValueError(shape)


def flash_samples(t_event: float, rate: float = CURVE_RATE_HZ) -> tuple[int, int]:
    """Writer rule for event-driven ``max`` channels (hit envelopes, drum envelopes, accents): the envelope
    holds its peak at both floor(t*rate) and ceil(t*rate), so the max-pooled value of the event's frame
    equals the peak at any fps <= rate."""
    x = t_event * rate
    k = round(x)
    if abs(x - k) < EPS:
        return k, k
    return math.floor(x), math.ceil(x)


def spectrum_rows(t: float, s: float, n_frames: int, rate: float = CURVE_RATE_HZ) -> list[int | None]:
    """Row indices of ``spectrumAt(t)`` (s = 0) / ``spectrumWindow(t, s)``: k = round(s * rate) + 1 rows,
    oldest first, ending at the nearest row of t (floor(t * rate + 0.5 + EPS)); rows outside [0, n) are None
    (the loaders return zero bytes for them). spectrumAt(t) clamps instead: it is hold_at on each band."""
    end = math.floor(t * rate + 0.5 + EPS)
    k = int(round(s * rate)) + 1
    return [i if 0 <= i < n_frames else None for i in range(end - k + 1, end + 1)]


def iter_frames(duration_s: float, fr) -> Iterable[int]:
    r = frame_rule(fr)
    return range(r.frame0, r.frame0 + frame_count(duration_s, r))


# --------------------------------------------------------------------------------------------- cues (D37)
#: kind priority of a merged cue (the first kind present becomes ``kind``; the rest stay in ``kinds``).
#: D49 (W3, CR M2-7): a user pin leads whatever it is merged with (amends D37, which ranked it last).
CUE_KIND_PRIORITY = ("pinned", "drop", "build_start", "breakdown", "section", "stop", "silence", "impact", "phrase",
                     "hit_point", "downbeat", "beat")


def merge_cues(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """D37: build ``events/cues.json`` from raw cue candidates ({t, kind, tier, strength, lead_in_s, source}).

    **At most one cue per time.** Candidates whose t rounds to the same microsecond are merged into one cue:
    ``tier`` = the best (lowest) tier, ``kind`` = the highest-priority kind (CUE_KIND_PRIORITY), ``kinds`` and
    ``sources`` list every merged candidate in priority order (``kinds[0] == kind``, ``sources[0] == source``),
    ``strength`` = the largest non-null strength, ``lead_in_s`` = that of the primary candidate that has one.
    So ``next(t, minTier)`` (strictly after t) reaches every cue by stepping t = cue.t, and ``prev`` and
    ``next`` are symmetric. ``next_major_in_s`` = time to the next tier-1 cue. Ids Q0001.. in time order."""
    groups: dict[float, list[Mapping[str, Any]]] = {}
    for i, c in enumerate(raw):
        groups.setdefault(round(float(c["t"]), 6), []).append(dict(c, _o=i))
    pr = {k: i for i, k in enumerate(CUE_KIND_PRIORITY)}
    t1 = sorted(k for k, g in groups.items() if any(int(c["tier"]) == 1 for c in g))
    out: list[dict[str, Any]] = []
    for n, key in enumerate(sorted(groups), start=1):
        g = sorted(groups[key], key=lambda c: (pr.get(c["kind"], len(pr)), int(c["tier"]), c["_o"]))
        p = g[0]
        st = [float(c["strength"]) for c in g if c.get("strength") is not None]
        li = next((c["lead_in_s"] for c in g if c.get("lead_in_s") is not None), None)
        nxt = next((x for x in t1 if x > key + 1e-9), None)
        out.append({
            "id": f"Q{n:04d}", "t": p["t"], "kind": p["kind"], "tier": min(int(c["tier"]) for c in g),
            "strength": max(st) if st else None, "lead_in_s": li,
            "next_major_in_s": None if nxt is None else round(nxt - float(p["t"]), 6),
            "source": p["source"], "kinds": [c["kind"] for c in g], "sources": [c["source"] for c in g],
        })
    return out
