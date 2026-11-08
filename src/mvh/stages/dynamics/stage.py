# ruff: noqa: E501  (long formulas, tables and docstrings)
"""dynamics stage: run(ctx). Detectors in ``detect.py``, segmentation and intensity in ``segment.py``."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from mvh.runner.spec import StageResult, UndeclaredDependency

from . import detect as D
from . import segment as G


def _r(x: float, nd: int = 6) -> float:
    return float(round(float(x), nd))


# ------------------------------------------------------------------------------------------------ inputs
def read_inputs(ctx) -> D.Inputs:
    def curve(cid: str) -> np.ndarray:
        return np.asarray(ctx.curve(cid).values, dtype=np.float64)

    st = curve("loud.short_term_lufs")
    n = st.size
    loud_doc = ctx.upstream("loudness").json("meta/loudness.json")
    audio = ctx.audio("mix")
    x = np.asarray(audio.samples, dtype=np.float64)
    if x.ndim == 1:
        x = x[None, :]
    kicks = [(float(it["t"]), float(it.get("strength", 1.0))) for it in ctx.events("hits.kick").items]
    om = [float(it["t"]) for it in ctx.events("onsets.mid").items]
    oh = [float(it["t"]) for it in ctx.events("onsets.high").items]
    try:
        bars = [dict(b) for b in ctx.events("bars").items]
    except Exception:  # noqa: BLE001 - no beat grid: boundaries are not snapped
        bars = []

    def fit(v: np.ndarray) -> np.ndarray:
        if v.size == n:
            return v
        return np.resize(v, n) if v.size else np.zeros(n)

    return D.Inputs(
        st=st,
        mom=fit(curve("loud.momentary_lufs")),
        integrated=float(loud_doc["integrated_lufs"]),
        bass_db=fit(curve("bands.bass_db")),
        kick_db=fit(curve("bands.kick_db")),
        centroid_hz=fit(curve("timbre.centroid_hz")),
        slope=fit(curve("timbre.slope_db_oct")),
        width=fit(curve("stereo.width")),
        kicks=kicks,
        onsets_mid=om,
        onsets_high=oh,
        bars=bars,
        fine_db=D.fine_envelope(x, int(audio.sr)),
        duration=x.shape[1] / float(audio.sr),
    )


def allin1_boundaries(ctx) -> list[float] | None:
    """allin1 section boundaries when this stage may read them (dynamics does not declare allin1 as a dep in contract
    v1; see the M1 change request). None when unavailable."""
    try:
        doc = ctx.upstream("allin1").json("allin1.json")
    except (UndeclaredDependency, Exception):  # noqa: BLE001
        return None
    segs = doc.get("segments") or []
    out = sorted({float(s.get("start", s.get("t", 0.0))) for s in segs})
    return [t for t in out if t > 0.0] or None


# ------------------------------------------------------------------------------------------------ segmentation
def level_thresholds(inp: D.Inputs, p: dict[str, Any]) -> tuple[tuple[float, ...], float]:
    """The level thresholds (LU vs integrated), scaled down for songs with a small loudness range so a limited master
    still shows its own louder and quieter parts: factor = clip(range / 8 LU, 0.5, 1), range = P95 - P10 of the
    short-term loudness above the -20 LU relative gate (an LRA estimate from the curve)."""
    base = tuple(float(v) for v in p["level_thresholds_lu"])
    st = inp.st[inp.st > inp.integrated - 20.0]
    rng = float(np.percentile(st, 95) - np.percentile(st, 10)) if st.size > 10 else 8.0
    f = float(np.clip(rng / float(p["level_scale_range_lu"]), float(p["level_scale_min"]), 1.0))
    return tuple(round(v * f, 3) for v in base), f


def segment_song(inp: D.Inputs, det: D.Detections, ser: dict[str, np.ndarray], feat: G.Features,
                 nov10: np.ndarray, intensity: np.ndarray, p: dict[str, Any],
                 allin1: list[float] | None) -> tuple[list[G.Segment], str, dict[str, Any]]:
    dur = inp.duration
    dbs = G.downbeats(inp.bars)
    th, scale = level_thresholds(inp, p)
    info: dict[str, Any] = {"level_thresholds_lu": list(th), "level_scale": round(scale, 3)}

    # hard boundaries: silences, stops and strong impacts
    hard: list[G.Boundary] = []
    for s in det.silences:
        if s.t > 0.0:
            hard.append(G.Boundary(s.t, "silence", 1.0, True))
        if s.t + s.d < dur:
            hard.append(G.Boundary(s.t + s.d, "silence", 1.0, True))
    for x in det.stops:
        hard.append(G.Boundary(x.t, "stop", x.strength, True))
    for y in det.decay_tails:  # a hit ringing out is its own (quiet) part
        if y.strength >= 0.5 and y.d >= float(p["decay_part_min_s"]):
            hard.append(G.Boundary(y.t, "decay", y.strength, True))
    for im in det.impacts:
        if im.major:
            hard.append(G.Boundary(im.t, "major-impact", im.strength, True))
        elif im.strength >= float(p["impact_boundary_strength"]):
            hard.append(G.Boundary(im.t, "impact", im.strength, True))

    # soft boundaries: novelty peaks (prominence relative to the song's strongest peaks)
    peaks = G.pick_peaks(nov10, min_dist_s=float(p["min_segment_s"]), rel_prom=float(p["novelty_rel_prom"]))
    soft = [G.Boundary(t, "novelty", pr) for t, pr in peaks]
    method = "novelty"
    min_gap = min_part_s(inp, p)
    info["min_part_s"] = round(min_gap, 3)

    def assemble_k(bset: list[G.Boundary]) -> tuple[list[float], list[G.Boundary]]:
        ts: list[tuple[float, G.Boundary]] = []
        for b in bset:
            tol = (float(p["snap_hard_s"]) if b.hard and b.kind in ("silence", "stop")
                   else 0.5 * G.bar_len(inp.bars, b.t))
            t, _ = G.snap(b.t, dbs, tol)
            ts.append((t, b))
        ts.sort(key=lambda z: z[0])
        out: list[float] = []
        kinds: list[G.Boundary] = []
        for t, b in ts:
            edge = float(p["silence_min_s"]) if b.kind in ("silence", "stop") else min_gap * 0.5
            if t <= edge or t >= dur - edge:
                continue
            if out and kinds[-1].hard and b.hard and t - out[-1] >= float(p["silence_min_s"]):
                out.append(t)
                kinds.append(b)
                continue
            if out and t - out[-1] < min_gap:
                # keep the hard one, else the stronger one
                if (b.hard and not kinds[-1].hard) or (b.hard == kinds[-1].hard and b.strength > kinds[-1].strength):
                    out[-1], kinds[-1] = t, b
                continue
            out.append(t)
            kinds.append(b)
        return out, kinds

    def assemble(bset: list[G.Boundary]) -> list[float]:
        return assemble_k(bset)[0]

    bset = hard + soft
    bounds = assemble(bset)
    info["novelty_boundaries"] = len(peaks)

    # local adaptivity: split long parts at their own strongest novelty peak when the feature contrast across it is
    # high enough (limited masters: the intro/outro dominate the song-wide novelty scale)
    max_part = float(p["max_part_s"])
    added = 0
    for _ in range(64):
        edges = [0.0] + bounds + [dur]
        best: tuple[float, float] | None = None
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a <= max_part:
                continue
            edge = float(p["split_min_side_s"])
            for t, pr in G.pick_peaks_in(nov10, a + edge, b - edge, min_dist_s=float(p["min_segment_s"])):
                c = G.contrast(feat.z, t, float(p["contrast_span_s"]))
                # longer parts accept a lower contrast (down to 0.6 x for parts of >= 100 s)
                need = float(p["split_min_contrast"]) * float(np.clip(60.0 / (b - a), 0.6, 1.0))
                if c >= need and (best is None or c > best[1]):
                    best = (t, c)
        if best is None:
            break
        bset.append(G.Boundary(best[0], "novelty-local", best[1]))
        nb = assemble(bset)
        if len(nb) == len(bounds):
            break
        bounds = nb
        added += 1
    info["local_splits"] = added

    want = max(2, int(dur / float(p["min_parts_per_s"])))
    if len(bounds) + 1 < want:
        # fallback: allin1 sections, else a 4-bar grid, kept where the feature contrast is high for this song
        cand = allin1 if allin1 else G.grid_candidates(inp.bars, 4, dur)
        method = "allin1" if allin1 else "bar-grid"
        span = float(p["contrast_span_s"])
        scored = [(t, G.contrast(feat.z, t, span)) for t in cand if 2.0 < t < dur - 2.0]
        if scored:
            vals = np.array([c for _, c in scored])
            thr = max(float(p["fallback_min_contrast"]), float(np.percentile(vals, float(p["fallback_keep_pct"]))))
            bset = bset + [G.Boundary(t, method, c) for t, c in scored if c >= thr]
            bounds = assemble(bset)
            info["fallback_candidates"] = len(scored)
            info["fallback_threshold"] = round(thr, 3)

    bounds, bkinds = assemble_k(bset)
    edges = [0.0] + bounds + [dur]
    ekinds = ["start"] + [b.kind for b in bkinds]
    evts: list[float | None] = [None] + [b.t if b.kind in ("major-impact", "impact") else None for b in bkinds]
    segs: list[G.Segment] = []
    sil_spans = [(s.t, s.t + s.d) for s in det.silences]
    for a, b, kd, ev in zip(edges[:-1], edges[1:], ekinds, evts):
        if b - a <= 1e-6:
            continue
        sg = G.Segment(a, b, kd, t_event=ev)
        cov = sum(max(0.0, min(b, z1) - max(a, z0)) for z0, z1 in sil_spans)
        sg.silence = cov >= 0.8 * (b - a) or any(z0 - 0.05 <= a and b <= z1 + 0.05 for z0, z1 in sil_spans)
        sg.stats = G.seg_stats(inp, ser, intensity, a, b)
        segs.append(sg)
    segs = _merge(inp, ser, intensity, feat, segs, th, p, dur, min_gap)
    for sg in segs:
        _classify(sg, th, inp)
    info["parts"] = len(segs)
    return segs, method, info


def _classify(sg: G.Segment, th: tuple[float, ...], inp: D.Inputs) -> None:
    if sg.silence:
        sg.level = "silence"
        sg.stats["rel_lu"] = sg.stats["mom_power_lufs"] - inp.integrated
        sg.stats["mean_lufs"] = sg.stats["mom_power_lufs"]
        sg.conf = 0.95
        return
    r = sg.stats["rel_lu"]
    sg.level = G.level_of(r, th)
    sg.conf = G.level_conf(r, th, sg.stats["spread_lu"])


def min_part_s(inp: D.Inputs, p: dict[str, Any]) -> float:
    """Shortest part: min_part_bars bars (at the song's median bar length), clamped to [3 s, min_part_s]."""
    bl = float(np.median([float(b.get("d") or 0.0) for b in inp.bars])) if inp.bars else 2.0
    return float(np.clip(float(p["min_part_bars"]) * bl, 3.0, float(p["min_part_s"])))


def _merge(inp: D.Inputs, ser, intensity, feat: G.Features, segs: list[G.Segment], th, p, dur: float,
           min_part: float) -> list[G.Segment]:
    """1. Parts shorter than min_part_s join their most similar neighbour (silences excepted).
    2. Agglomerative: while there are more parts than duration / target_part_s, the most similar adjacent pair of the
       same level whose boundary is not a silence, a stop or a major impact is merged, as long as their median feature
       vectors (standardised novelty features) are closer than merge_max; pairs closer than merge_similarity always
       merge."""
    hard_kinds = ("silence", "stop", "major-impact", "decay")

    def dist(a: G.Segment, b: G.Segment) -> float:
        za = feat.z[int(a.t * feat.rate) : max(int(a.t * feat.rate) + 1, int(a.t1 * feat.rate))]
        zb = feat.z[int(b.t * feat.rate) : max(int(b.t * feat.rate) + 1, int(b.t1 * feat.rate))]
        if za.size == 0 or zb.size == 0:
            return 0.0
        return float(np.linalg.norm(np.median(za, axis=0) - np.median(zb, axis=0)))

    def join(i: int) -> None:
        a, b = segs[i], segs[i + 1]
        m = G.Segment(a.t, b.t1, a.kind_in, silence=a.silence and b.silence, t_event=a.t_event)
        m.stats = G.seg_stats(inp, ser, intensity, m.t, m.t1)
        segs[i : i + 2] = [m]

    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i, s in enumerate(segs):
            if s.silence or s.d >= min_part:
                continue
            cands = []
            if i > 0 and not segs[i - 1].silence:
                cands.append((dist(segs[i - 1], s), i - 1))
            if i + 1 < len(segs) and not segs[i + 1].silence:
                cands.append((dist(s, segs[i + 1]), i))
            if cands:
                join(min(cands)[1])
                changed = True
                break
    target = max(2, int(math.ceil(dur / float(p["target_part_s"]))))
    while len(segs) > 1:
        best = None
        for i in range(len(segs) - 1):
            a, b = segs[i], segs[i + 1]
            if a.silence or b.silence or b.kind_in in hard_kinds:
                continue
            if G.level_of(a.stats["rel_lu"], th) != G.level_of(b.stats["rel_lu"], th):
                continue
            d = dist(a, b)
            if best is None or d < best[0]:
                best = (d, i)
        if best is None:
            break
        if best[0] >= float(p["merge_similarity"]) and (len(segs) <= target or best[0] >= float(p["merge_max"])):
            break
        join(best[1])
    return segs


def role_hints(segs: list[G.Segment], det: D.Detections, inp: D.Inputs) -> None:
    """Evidence for the structure stage (which alone defines EDM roles): drop / build / breakdown hints per part."""
    live = [s for s in segs if not s.silence]
    if not live:
        return
    med_bass = float(np.median([s.stats["bass_db"] for s in live]))
    med_kick = float(np.median([s.stats["kick_rate"] for s in live]))
    for i, s in enumerate(segs):
        s.stats["role_hint"] = None
        s.stats["role_score"] = 0.0
        if s.silence:
            continue
        prev = segs[i - 1] if i > 0 else None
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        hints: list[tuple[float, str]] = []
        # drop: an impact at the start, more bass than before, at least medium loud
        imp = [im for im in det.impacts
               if abs(im.t - s.t) <= 0.6 or (s.t_event is not None and abs(im.t - s.t_event) <= 0.6)]
        if prev is not None and imp:
            pb = prev.stats["bass_db"] if not prev.silence else -120.0
            gain = s.stats["bass_db"] - pb
            sc = 0.5 * max(im.strength for im in imp) + 0.5 * float(np.clip(gain / 10.0, 0.0, 1.0))
            setup = prev.silence or prev.stats.get("role_hint") in ("build", "breakdown")
            full = s.stats["bass_db"] >= med_bass - 2.0 and s.stats["rel_lu"] >= -1.0
            if gain >= 3.0 and s.stats["rel_lu"] > -6.0 and (setup or (full and gain >= 8.0)):
                hints.append((min(1.0, sc + (0.2 if setup else 0.0)), "drop"))
        # build: rising loudness/brightness/density, followed by a louder part, an impact or a stop
        if nxt is not None and s.d >= 4.0 and (i > 0 or s.d >= 8.0):
            ev = [float(np.clip(s.stats["trend_lu_per_s"] / 0.3, 0.0, 1.0)),
                  float(np.clip(s.stats["onset_trend"] / 0.4, 0.0, 1.0)),
                  float(np.clip(s.stats["bright_trend"] / 0.04, 0.0, 1.0))]
            after = (nxt.silence or nxt.stats["rel_lu"] >= s.stats["rel_lu"] + 2.0 or
                     any(abs(im.t - s.t1) <= 1.0 and im.strength >= 0.75 for im in det.impacts) or
                     any(abs(x.t - s.t1) <= 1.0 for x in det.stops))
            if max(ev) >= 0.5 and after:
                hints.append((0.4 * ev[0] + 0.3 * ev[1] + 0.3 * ev[2] + 0.2, "build"))
        # breakdown: much less bass / kick than the song's typical part, after a part that had them
        if prev is not None and not prev.silence and i > 0:
            low_bass = med_bass - s.stats["bass_db"]
            low_kick = med_kick - s.stats["kick_rate"]
            if low_bass >= 6.0 and prev.stats["bass_db"] - s.stats["bass_db"] >= 6.0:
                hints.append((float(np.clip(low_bass / 15.0 + max(0.0, low_kick) / 3.0, 0.0, 1.0)), "breakdown"))
        if hints:
            sc, role = max(hints)
            if sc >= 0.3:
                s.stats["role_hint"], s.stats["role_score"] = role, round(sc, 3)


# ------------------------------------------------------------------------------------------------ run
def run(ctx) -> StageResult:
    p = dict(ctx.params)
    warnings: list[str] = []
    fallbacks: list[str] = []
    inp = read_inputs(ctx)
    if inp.duration <= 0 or inp.n == 0:
        raise ValueError("dynamics: empty song")
    det = D.Detections()
    det.silences = D.detect_silences(inp, rel_lu=float(p["silence_rel_lu"]), cap=float(p["silence_cap_lufs"]),
                                     min_s=float(p["silence_min_s"]))
    det.stops = D.detect_stops(inp, det.silences)
    det.impacts = D.detect_impacts(inp, det.silences, theta_lu=float(p["impact_lu"]),
                                   theta_bass_db=float(p["impact_bass_db"]))
    det.decay_tails = D.detect_decay_tails(inp, det.impacts)

    ser = G.series(inp)
    feat = G.features(inp, ser, [(z.t, z.t + z.d) for z in det.silences])
    nov10 = G.novelty(feat, tuple(float(h) for h in p["novelty_halves_s"]))
    intensity = G.intensity_curve(inp, ser)
    allin1 = allin1_boundaries(ctx)
    segs, method, info = segment_song(inp, det, ser, feat, nov10, intensity, p, allin1)
    role_hints(segs, det, inp)
    th = tuple(info["level_thresholds_lu"])
    if method != "novelty":
        fallbacks.append(f"dynamics:{method}")
        warnings.append(f"few novelty boundaries ({info.get('novelty_boundaries', 0)}): parts completed from the {method}")

    # ---------------------------------------------------------------- events
    bars = sorted(inp.bars, key=lambda b: b["t"])
    bar_t = np.array([float(b["t"]) for b in bars]) if bars else np.zeros(0)

    def bar_of(t: float) -> int | None:
        if bar_t.size == 0:
            return None
        i = int(np.searchsorted(bar_t, t + 1e-6) - 1)
        if i < 0:
            return None
        b = bars[i]
        if t >= float(b["t"]) + float(b.get("d") or 0.0) + 1e-6 and i == len(bars) - 1:
            return None
        return int(b["bar"])

    items = []
    for s in segs:
        st = s.stats
        items.append({
            "t": _r(s.t), "d": _r(s.d), "level": s.level, "rel_lu": _r(st["rel_lu"], 2), "mean_lufs": _r(st["mean_lufs"], 2),
            "conf": _r(s.conf, 3), "energy": _r(st["energy"], 3), "bass_db": _r(st["bass_db"], 2),
            "kick_rate": _r(st["kick_rate"], 2), "onset_rate": _r(st["onset_rate"], 2),
            "brightness_hz": _r(st["brightness_hz"], 1), "trend_lu_per_s": _r(st["trend_lu_per_s"], 3),
            "role_hint": st.get("role_hint"), "role_score": _r(st.get("role_score", 0.0), 3),
        })
    ctx.writer.events("dynamics", items, fields={
        "energy": {"unit": "0..1", "type": "number", "description": "mean dyn.intensity over the part"},
        "bass_db": {"unit": "dBFS", "type": "number", "description": "bass band (32-150 Hz) power mean"},
        "kick_rate": {"unit": "1/s", "type": "number", "description": "kick hits per second (strength-weighted)"},
        "onset_rate": {"unit": "1/s", "type": "number", "description": "mid + high onsets per second"},
        "brightness_hz": {"unit": "Hz", "type": "number", "description": "median spectral centroid"},
        "trend_lu_per_s": {"unit": "LU/s", "type": "number", "description": "short-term loudness slope (builds rise)"},
        "role_hint": {"unit": None, "type": "string|null",
                      "description": "evidence for structure's EDM roles: drop, build, breakdown (dynamics never defines roles)"},
        "role_score": {"unit": "0..1", "type": "number", "description": "strength of the role hint"},
    })
    ctx.writer.events("impacts", [
        {"id": f"I{k:03d}", "t": _r(im.t), "strength": _r(im.strength, 3), "delta_lu": _r(im.delta_lu, 2),
         "delta_bass_db": _r(im.delta_bass_db, 2), "bar": bar_of(im.t), "after_silence": bool(im.after_silence),
         "major": bool(im.major)}
        for k, im in enumerate(sorted(det.impacts, key=lambda z: z.t), 1)
    ], fields={"after_silence": {"unit": None, "type": "boolean", "description": "the impact ends a silence"},
               "major": {"unit": None, "type": "boolean",
                         "description": "one of the song's biggest energy increases (ends a silence, or scores >= half "
                                        "the largest); always a part boundary"}})
    ctx.writer.events("stops", [
        {"id": f"X{k:03d}", "t": _r(x.t), "strength": _r(x.strength, 3), "gap_s": _r(x.gap_s, 3),
         "drop_db": _r(x.drop_db, 2), "to_silence": bool(x.silence)}
        for k, x in enumerate(sorted(det.stops, key=lambda z: z.t), 1)
    ], fields={"drop_db": {"unit": "dB", "type": "number", "description": "fall of the 5 ms level within 150 ms"},
               "to_silence": {"unit": None, "type": "boolean", "description": "the stop opens a silence (Z)"}})
    ctx.writer.events("silences", [
        {"id": f"Z{k:03d}", "t": _r(s.t), "d": _r(s.d), "depth_db": _r(s.depth_db, 2), "edge": bool(s.edge),
         "digital": bool(s.digital)}
        for k, s in enumerate(sorted(det.silences, key=lambda z: z.t), 1)
    ], fields={"edge": {"unit": None, "type": "boolean", "description": "lead-in / run-out silence of the file"},
               "digital": {"unit": None, "type": "boolean", "description": "digital silence (all samples zero)"}})
    ctx.writer.events("decay_tails", [
        {"id": f"Y{k:03d}", "t": _r(y.t), "d": _r(y.d), "strength": _r(y.strength, 3), "rate_db_s": _r(y.rate_db_s, 2)}
        for k, y in enumerate(sorted(det.decay_tails, key=lambda z: z.t), 1)
    ], fields={"rate_db_s": {"unit": "dB/s", "type": "number", "description": "mean decay rate"}})

    # ---------------------------------------------------------------- curves
    nov = np.clip(G.upsample(nov10, inp.n), 0.0, 1.0)
    ctx.writer.curves("core", {"dyn.intensity": intensity.astype(np.float32), "dyn.novelty": nov.astype(np.float32)})

    # ---------------------------------------------------------------- readable summary (meta/dynamics.json, additive)
    live = [s for s in segs if not s.silence]
    order = sorted(live, key=lambda s: s.stats["rel_lu"])
    doc = {
        "integrated_lufs": _r(inp.integrated, 2),
        "level_thresholds_lu": {"quiet_below": th[0], "soft_below": th[1], "medium_below": th[2], "peak_above": th[3],
                                "scale": info["level_scale"]},
        "method": method,
        "parts": len(segs),
        "level_seconds": {lv: _r(sum(s.d for s in segs if s.level == lv), 2) for lv in G.LEVELS},
        "loudest_parts": [{"t": _r(s.t, 2), "d": _r(s.d, 2), "level": s.level, "rel_lu": _r(s.stats["rel_lu"], 2)}
                          for s in order[::-1][:3]],
        "quietest_parts": [{"t": _r(s.t, 2), "d": _r(s.d, 2), "level": s.level, "rel_lu": _r(s.stats["rel_lu"], 2)}
                           for s in order[:3]],
        "counts": {"impacts": len(det.impacts), "stops": len(det.stops), "silences": len(det.silences),
                   "decay_tails": len(det.decay_tails)},
        "role_hints": [{"t": _r(s.t, 2), "d": _r(s.d, 2), "role": s.stats["role_hint"], "score": s.stats["role_score"]}
                       for s in segs if s.stats.get("role_hint")],
    }
    ctx.writer.json("meta/dynamics.json", doc)

    summary = {
        "parts": len(segs),
        "method": method,
        "levels": {lv: n for lv in G.LEVELS if (n := sum(1 for s in segs if s.level == lv))},
        "impacts": len(det.impacts),
        "stops": len(det.stops),
        "silences": len(det.silences),
        "decay_tails": len(det.decay_tails),
        "drop_hints": [round(s.t, 2) for s in segs if s.stats.get("role_hint") == "drop"][:8],
    }
    conf = float(np.mean([s.conf for s in segs])) if segs else 0.5
    if method != "novelty":
        conf *= 0.85
    notes = [
        "levels by mean short-term LU vs integrated: quiet < %g <= soft < %g <= medium < %g <= loud <= %g < peak" % th,
        "boundaries: Foote novelty (+-4/8 s, 10 Hz multi-feature: LU, bass, kick dB, kick and onset density, brightness, "
        "slope, width; adaptive prominence), silences, stops, strong impacts; snapped to downbeats",
        f"segmentation method: {method}" + ("" if allin1 is None else " (allin1 sections readable)"),
        "role_hint is evidence only; drops/builds/breakdowns are defined by the structure stage",
    ]
    return StageResult(status="ok", summary=summary, warnings=warnings, fallbacks=fallbacks,
                       provenance={"notes": notes, "segmentation": info}, confidence=round(conf, 3))
