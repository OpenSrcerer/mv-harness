"""frames/<fps>fps.csv (CONTRACT §7 tables, §2 frame rules, D19): one row per video frame.

Columns: ``frame`` (n, frame0 included), ``t`` (= time_of(n)), then one column per curve channel sampled with the
channel's resample policy (``conventions.curve_frame`` semantics, vectorised here and parity-tested against it),
then optional event columns (``section_id``, ``beat``, ``count``, ``singer``, ...). Never NaN: pitch channels use
the NaN-aware rule, and a song with no voiced frame reads 0.

Frame rule ``{fps, frame0, early}``; fps is a number (taken literally: 23.976 != 24000/1001) or ``[num, den]``.
"""
from __future__ import annotations

import fnmatch
import math
from typing import Any, Mapping, Sequence

import numpy as np

from mvh.contract import conventions as cv
from mvh.contract import registry

__all__ = ["sample_frames", "frame_times", "file_tag", "parse_rules", "DEFAULT_CURVES", "DEFAULT_EVENTS",
           "EVENT_COLUMNS", "select_channels", "event_columns"]

EPS = cv.EPS
DEFAULT_CURVES = (
    "bands.bass", "bands.mid", "bands.high", "bands.level", "hits.kick", "hits.mid", "hits.high", "flux.bass",
    "drums.kick", "drums.snare", "drums.hat", "drums.cymbal", "loud.short_term", "dyn.intensity", "choreo.accent",
    "choreo.movement", "tempo.bpm", "rhythm.in_pulse", "vocal.pitch01", "vocal.voiced", "vocal.mouth_open",
    "vocal.mouth_open.*", "mood.valence", "mood.arousal",
)
EVENT_COLUMNS = ("section_id", "beat", "downbeat", "bar", "beat_phase", "count", "sub", "eight_id", "line_id", "singer",
                 "cue_tier", "cue_id", "hit", "kick")
DEFAULT_EVENTS = EVENT_COLUMNS


# ============================================================================================ frame rules
def parse_rules(fps: Any, frame0: int = 0, early: bool = False) -> list[cv.FrameRule]:
    """fps: 24 | 23.976 | [24000, 1001] | "24000/1001" | {"fps":..,"frame0":..,"early":..} | a list of those."""
    def one(x: Any) -> cv.FrameRule:
        if isinstance(x, Mapping):
            return cv.FrameRule(_fps(x["fps"]), int(x.get("frame0", frame0)), bool(x.get("early", early)))
        return cv.FrameRule(_fps(x), int(frame0), bool(early))

    if isinstance(fps, (list, tuple)) and _is_rational(fps):
        out = [one(list(fps))]  # [24000, 1001]
    elif isinstance(fps, (list, tuple)):
        out = [one(x) for x in fps]  # [24, 30] or ["24000/1001", 60]: several exports
    else:
        out = [one(fps)]
    seen, uniq = set(), []
    for r in out:
        k = (r.num, r.den, r.frame0, r.early)
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def _is_rational(x: Sequence[Any]) -> bool:
    """[num, den] (two plain numbers whose ratio is a plausible frame rate) vs a list of rates ([24, 30])."""
    if len(x) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in x):
        return False
    a, b = float(x[0]), float(x[1])
    return b >= 1 and 1.0 <= a / b <= 1000.0


def _fps(x: Any) -> float | list[float]:
    if isinstance(x, str):
        s = x.strip().replace("-", "/")
        if "/" in s:
            a, b = s.split("/", 1)
            return [float(a), float(b)]
        return float(s)
    if isinstance(x, (list, tuple)):
        return [float(x[0]), float(x[1])]
    return float(x)


def file_tag(r: cv.FrameRule) -> str:
    """CONTRACT §7 naming: 24 | 23.976 | 24000-1001, then _f<frame0>, then _early (file = <tag>fps.csv)."""
    if r.den == 1.0:
        v = r.num
        s = str(int(v)) if float(v).is_integer() else f"{v:.3f}".rstrip("0").rstrip(".")
    else:
        s = f"{_g(r.num)}-{_g(r.den)}"
    if r.frame0 != 0:
        s += f"_f{r.frame0}"
    if r.early:
        s += "_early"
    return s


def _g(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.3f}".rstrip("0").rstrip(".")


def frame_times(r: cv.FrameRule, duration_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """-> (frame numbers n, nominal times t_n = time_of(n), sampling instants)."""
    count = cv.frame_count(duration_s, r)
    n = np.arange(r.frame0, r.frame0 + count, dtype=np.int64)
    t = (n - r.frame0).astype(np.float64) * r.den / r.num
    c = t + (r.half if r.early else 0.0)
    return n, t, c


# ============================================================================================ curves
def _lerp(v: np.ndarray, x: np.ndarray) -> np.ndarray:
    n = v.size
    if n == 0:
        return np.zeros_like(x)
    i = np.floor(np.clip(x, 0, max(0, n - 1))).astype(np.int64)
    i = np.minimum(i, max(0, n - 2)) if n > 1 else np.zeros_like(i)
    f = x - i
    a = v[i]
    b = v[np.minimum(i + 1, n - 1)]
    y = a + (b - a) * f
    y = np.where(x <= 0, v[0], y)
    y = np.where(x >= n - 1, v[n - 1], y)
    return y


def _nearest(n: int, x: np.ndarray) -> np.ndarray:
    k = np.floor(x + 0.5 + EPS).astype(np.int64)
    return np.clip(k, 0, n - 1)


def _nan_aware(v: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Vectorised conventions.nan_aware_at."""
    n = v.size
    if n == 0:
        return np.full_like(x, np.nan)
    fin = np.isfinite(v)
    xc = np.clip(x, 0.0, float(n - 1))
    i = np.floor(xc).astype(np.int64)
    j = np.minimum(i + 1, n - 1)
    a, b = v[i], v[j]
    both = fin[i] & fin[j]
    lin = a + (b - a) * (xc - i)
    k = _nearest(n, x)
    idx = np.arange(n)
    last = np.maximum.accumulate(np.where(fin, idx, -1))         # last finite index <= m
    nxt = np.minimum.accumulate(np.where(fin, idx, n)[::-1])[::-1]  # first finite index >= m
    prev_k = np.where(k > 0, last[np.maximum(k - 1, 0)], -1)
    next_k = np.where(k < n - 1, nxt[np.minimum(k + 1, n - 1)], n)
    out = np.where(fin[k], v[k], np.nan)
    use_prev = ~fin[k] & (prev_k >= 0)
    out = np.where(use_prev, v[np.clip(prev_k, 0, n - 1)], out)
    use_next = ~fin[k] & ~use_prev & (next_k < n)
    out = np.where(use_next, v[np.clip(next_k, 0, n - 1)], out)
    return np.where(both, lin, out)


def sample_frames(values: Any, rate: float, r: cv.FrameRule, n_frames: int, policy: str,
                  nan_aware: bool = False) -> np.ndarray:
    """conventions.curve_frame for frames frame0 .. frame0 + n_frames - 1 (float64, never NaN)."""
    if policy not in cv.POLICIES:
        raise ValueError(policy)
    v = np.asarray(values, dtype=np.float64).reshape(-1)
    n_idx = np.arange(r.frame0, r.frame0 + n_frames, dtype=np.int64)
    c = (n_idx - r.frame0).astype(np.float64) * r.den / r.num + (r.half if r.early else 0.0)
    x = c * rate
    if v.size == 0:
        return np.zeros(n_frames)
    if policy in ("mean", "max"):
        i = np.arange(v.size, dtype=np.float64)
        fo = np.floor((i / rate) * r.num / r.den + (0.0 if r.early else 0.5) + EPS).astype(np.int64) + r.frame0
        lo = np.searchsorted(fo, n_idx, "left")
        hi = np.searchsorted(fo, n_idx, "right")
        fin = np.isfinite(v) if nan_aware else np.ones(v.size, dtype=bool)
        vz = np.where(fin, v, 0.0)
        cs = np.concatenate([[0.0], np.cumsum(vz)])
        cn = np.concatenate([[0], np.cumsum(fin.astype(np.int64))])
        cnt = cn[hi] - cn[lo]
        out = np.empty(n_frames)
        has = cnt > 0
        if policy == "mean":
            # exact per-frame sums (cumsum differences drift by ~1e-12; fsum-equivalent within 1e-9 here)
            out[has] = (cs[hi] - cs[lo])[has] / cnt[has]
            for k in np.flatnonzero(has & (hi - lo > 64)):
                seg = v[lo[k]:hi[k]]
                seg = seg[np.isfinite(seg)] if nan_aware else seg
                out[k] = math.fsum(seg.tolist()) / seg.size
        else:
            vm = np.where(fin, v, -np.inf)
            starts = lo[has]
            ends = hi[has]
            if starts.size:
                # contiguous, increasing ranges: reduceat over the starts, then cut each at its end
                mx = np.maximum.reduceat(vm, starts)
                # reduceat runs to the next start; ranges are adjacent so this equals the range max
                # except when samples between ranges belong to frames outside n_idx (none: fo is contiguous)
                out[has] = mx
                bad = ends - starts != np.diff(np.append(starts, vm.size))
                for k, (a, b) in zip(np.flatnonzero(has)[bad], zip(starts[bad], ends[bad])):
                    out[k] = float(np.max(vm[a:b]))
        fb = ~has
        if fb.any():
            out[fb] = _nan_aware(v, x[fb]) if nan_aware else _lerp(v, x[fb])
    elif nan_aware:
        out = _nan_aware(v, x)
    elif policy == "hold":
        out = v[_nearest(v.size, x)]
    else:
        out = _lerp(v, x)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def select_channels(available: Sequence[str], wanted: Sequence[str] | None) -> list[str]:
    """wanted: None/[] -> DEFAULT_CURVES that exist; ['*'] -> all; patterns allowed ('drums.*'). Registry order."""
    pats = list(wanted) if wanted else list(DEFAULT_CURVES)
    order = {cid: k for k, cid in enumerate(registry.CHANNELS)}
    files = list(registry.CURVE_FILES)

    def key(cid: str):
        c = registry.match_channel(cid)
        return (files.index(c.file) if c else 99, order.get(c.id, 10**6) if c else 10**6, cid)

    out = [cid for cid in available if any(fnmatch.fnmatchcase(cid, p) for p in pats)]
    return sorted(dict.fromkeys(out), key=key)


# ============================================================================================ events
def event_columns(names: Sequence[str], r: cv.FrameRule, n: np.ndarray, centres: np.ndarray,
                  ev: Mapping[str, Sequence[Mapping[str, Any]] | None]) -> dict[str, list[Any]]:
    """Event-derived columns (strings or numbers; empty cell = none). Uses the contract helpers' rules:
    point events belong to frame_of(t); segments are sampled at the frame's sampling instant."""
    out: dict[str, list[Any]] = {}
    beats = sorted(ev.get("beats") or [], key=lambda b: b["t"])
    counts = ev.get("counts") or []

    def in_frame(items: Sequence[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
        m: dict[int, list[Mapping[str, Any]]] = {}
        for it in items:
            m.setdefault(cv.frame_of(float(it["t"]), r), []).append(it)
        return m

    def seg_at(items: Sequence[Mapping[str, Any]] | None):
        items = sorted(items or [], key=lambda i: float(i["t"]))
        return [cv.event_at(items, float(c)) for c in centres]

    if "section_id" in names:
        out["section_id"] = [(e["item"].get("id") if e else None) for e in seg_at(ev.get("sections"))]
    if beats and any(k in names for k in ("beat", "downbeat")):
        bf = in_frame(beats)
        if "beat" in names:
            out["beat"] = [len(bf.get(int(k), [])) for k in n]
        if "downbeat" in names:
            out["downbeat"] = [int(any(int(b.get("beat_in_bar", 0)) == 1 for b in bf.get(int(k), []))) for k in n]
    if beats and "bar" in names:
        ts = [float(b["t"]) for b in beats]
        import bisect

        col = []
        for c in centres:
            i = bisect.bisect_right(ts, float(c)) - 1
            col.append(int(beats[i]["bar"]) if i >= 0 else None)
        out["bar"] = col
    if beats and "beat_phase" in names:
        out["beat_phase"] = [round(cv.beat_phase(float(c), beats)["value"], 6) for c in centres]
    if beats and counts and any(k in names for k in ("count", "sub", "eight_id")):
        cs = [cv.count_at(float(c), beats, counts) for c in centres]
        if "count" in names:
            out["count"] = [x.get("count") for x in cs]
        if "sub" in names:
            out["sub"] = [x.get("sub") if x.get("count") is not None else None for x in cs]
        if "eight_id" in names:
            out["eight_id"] = [x.get("eight_id") for x in cs]
    if "line_id" in names and ev.get("lines") is not None:
        out["line_id"] = [(e["item"].get("id") if e else None) for e in seg_at(ev.get("lines"))]
    if "singer" in names and ev.get("singing") is not None:
        sing = sorted(ev.get("singing") or [], key=lambda i: float(i["t"]))
        col = []
        for c in centres:
            ss = cv.singer_at(float(c), sing, lambda _v, _t: 0.0)
            col.append("+".join(dict.fromkeys(x["character_id"] for x in ss)) or None)
        out["singer"] = col
    if any(k in names for k in ("cue_tier", "cue_id")) and ev.get("cues") is not None:
        cf = in_frame(ev.get("cues") or [])
        best = {k: min(v, key=lambda c: (int(c.get("tier", 9)), float(c["t"]))) for k, v in cf.items()}
        if "cue_tier" in names:
            out["cue_tier"] = [(int(best[int(k)]["tier"]) if int(k) in best else None) for k in n]
        if "cue_id" in names:
            out["cue_id"] = [(best[int(k)]["id"] if int(k) in best else None) for k in n]
    if "hit" in names and ev.get("hit_points") is not None:
        hf = in_frame(ev.get("hit_points") or [])
        out["hit"] = [len(hf.get(int(k), [])) for k in n]
    if "kick" in names and ev.get("kick") is not None:
        # D79 (UD2): the agent-facing kick (meta/drums.json kick_source): the loudest kick vel in the frame, 0 without one
        kf = in_frame(ev.get("kick") or [])
        out["kick"] = [round(max((float(x["vel"]) for x in kf.get(int(k), [])), default=0.0), 4) for k in n]
    return out
