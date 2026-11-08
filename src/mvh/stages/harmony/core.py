# ruff: noqa: E501  (long literals and docstrings)
"""Harmony analysis core: pure functions over arrays (no ctx), so tests drive it with synthetic input."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from . import chords as C
from . import keys as K
from . import theory as T
from .chroma import ChromaFrames, aggregate, compute_chroma, to_curve_100hz

SR = 22050


@dataclass
class HarmonyResult:
    chords: list[dict[str, Any]]
    key_regions: list[dict[str, Any]]
    key_meta: dict[str, Any]
    chroma_curve: np.ndarray            # [12, n] float32
    chord_source: str                   # 'lv-chordia' | 'template'
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fallbacks: list[str] = field(default_factory=list)


def _bars_downbeats(bars: Sequence[Mapping[str, Any]] | None) -> np.ndarray:
    if not bars:
        return np.zeros(0)
    return np.array(sorted(float(b["t"]) for b in bars), float)


def snap_time(t: float, grid: np.ndarray, max_dist: float) -> float:
    if grid.size == 0:
        return t
    j = int(np.argmin(np.abs(grid - t)))
    return float(grid[j]) if abs(grid[j] - t) <= max_dist else t


def analyse(y22: np.ndarray, duration: float, n_curve: int, beats: Sequence[Mapping[str, Any]], bars: Sequence[Mapping[str, Any]] | None,
            lv: Callable[[], list[dict[str, Any]]] | None, skey: "K.SKey | None", params: Mapping[str, Any],
            cf: ChromaFrames | None = None) -> HarmonyResult:
    """Chroma, chords (lv-chordia or template fallback) snapped to beats, and the key ensemble.

    ``lv`` returns lv-chordia segments ([{start_time, end_time, chord}]) or raises; ``skey`` may be None (the key is then
    scored by the profile/chord/bass evidence only and flagged)."""
    warnings: list[str] = []
    fallbacks: list[str] = []
    cf = cf or compute_chroma(y22, SR)
    curve = to_curve_100hz(cf, n_curve)

    # ---- chords
    windows = C.beat_windows(beats, duration)
    fb_segs = C.template_decode(cf, windows)
    chord_source = "lv-chordia"
    segs: list[C.Seg]
    lv_res = None
    if lv is not None:
        try:
            lv_res = lv()
        except Exception as e:  # noqa: BLE001  (any lv-chordia failure -> template fallback, recorded)
            warnings.append(f"lv-chordia failed ({type(e).__name__}); chords from template + Viterbi")
    if lv_res:
        segs = C.segs_from_lv(lv_res, duration)
    else:
        chord_source = "template"
        fallbacks.append("chords:template")
        segs = C._cover(fb_segs, duration)
    segs = C.snap_to_beats(segs, beats, duration, max_frac=float(params.get("snap_max_beat_frac", 0.5)))
    C.verify_segments(segs, cf, fb_segs, windows)
    C.assign_beat_index(segs, beats)
    items = C.to_items(segs)

    # ---- key
    key_regions, key_meta, kflags = analyse_key(y22, cf, items, duration, _bars_downbeats(bars), bars, skey, params)
    if skey is None:
        fallbacks.append("key:no_skey")
    nc = C.no_chord_share(segs, duration)
    hist = C.chord_histogram(segs)
    summary = {
        "key": key_meta["global"]["key"], "key_conf": round(key_meta["global"]["conf"], 3), "key_regions": len(key_regions),
        "chord_source": chord_source, "n_chords": sum(1 for s in segs if s.root is not None), "n_segments": len(segs),
        "no_chord_share": round(nc, 3), "distinct_chords": len([k for k in hist if k != "N"]),
        "top_chords": [k for k in list(hist)[:4]],
        "mean_chord_conf": round(float(np.mean([s.conf for s in segs if s.root is not None])) if any(s.root is not None for s in segs) else 0.0, 3),
    }
    if summary["mean_chord_conf"] < 0.55 and summary["n_chords"]:
        warnings.append(f"chords: mean confidence {summary['mean_chord_conf']:.2f} (dense mix, rap or ambiguous harmony): treat labels as hints")
    if nc > 0.35:
        warnings.append(f"no-chord share {nc:.0%} (speech, rap or noise sections)")
    return HarmonyResult(items, key_regions, key_meta, curve, chord_source, summary, warnings, fallbacks)


def _tonal_fraction(cf: ChromaFrames, t0: float, t1: float) -> float:
    """Share of frames in [t0, t1) above the silence floor (S-KEY peak-normalises, so it must not see silence)."""
    a, b = int(np.searchsorted(cf.times, t0, "left")), int(np.searchsorted(cf.times, t1, "left"))
    m = cf.mask()[a:b]
    return float(m.mean()) if m.size else 0.0


def analyse_key(y22: np.ndarray, cf: ChromaFrames, chord_items: Sequence[Mapping[str, Any]], duration: float, downbeats: np.ndarray,
                bars: Sequence[Mapping[str, Any]] | None,
                skey: "K.SKey | None", params: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    win_s = float(params.get("key_window_s", 30.0))
    hop_s = float(params.get("key_hop_s", 5.0))
    min_region = float(params.get("key_min_region_s", 20.0))
    forced = params.get("key_override") or None
    grid = K.window_grid(duration, win_s, hop_s)
    flags: list[str] = []

    def evidence(t0: float, t1: float, use_skey: bool = True) -> K.Evidence:
        ev = K.Evidence()
        csum = aggregate(cf, t0, t1)
        for n, v in K.profile_evidence(csum).items():
            setattr(ev, n, v)
        ev.chords = K.chord_evidence(chord_items, t0, t1)
        ev.bass = K.bass_evidence(cf, t0, t1)
        ev.phrase = K.phrase_evidence(chord_items, bars or [], t0, t1)
        if use_skey and skey is not None:
            a, b = int(t0 * SR), min(int(t1 * SR), len(y22))
            if b - a >= 8 * SR and _tonal_fraction(cf, t0, t1) >= 0.2:
                ev.skey, ev.skey_probs = skey.log_scores(y22[a:b])
        return ev

    # global evidence: S-KEY on the whole song and averaged over the windows
    g = evidence(0.0, duration, use_skey=False)
    win_ev = [evidence(a, b) for a, b in grid]
    if skey is not None:
        logs = [w.skey for w in win_ev if w.skey is not None]
        gl, gp = skey.log_scores(y22) if (len(y22) >= 8 * SR and _tonal_fraction(cf, 0.0, duration) >= 0.2) else (None, None)
        probs = [w.skey_probs for w in win_ev if w.skey_probs is not None] + ([gp] if gp is not None else [])
        parts = ([gl] if gl is not None else []) + ([np.mean(logs, axis=0)] if logs else [])
        if parts:
            g.skey = np.mean(parts, axis=0)
            g.skey_probs = np.mean(probs, axis=0)
    gscore = K.ensemble(g)
    win_scores = np.stack([K.ensemble(w) for w in win_ev]) if win_ev else np.zeros((0, 24))
    win_top = [int(np.argmax(s)) for s in win_scores]
    gkey = int(np.argmax(gscore))
    if forced:
        pc, mode = T.parse_key_label(str(forced))
        gkey = T.key_index(pc, mode)
        flags.append("key:overridden")
    conf, cinfo = K.global_confidence(gkey, g, win_top, gscore)
    flags += cinfo["flags"]
    if forced:
        conf = 1.0

    # key regions: sticky Viterbi over the windows, boundaries snapped to the nearest downbeat
    regions: list[tuple[float, float, int]] = [(0.0, duration, gkey)]
    if len(grid) >= 3 and not forced:
        path = K.viterbi_regions(win_scores, gkey)
        # a relative key shares the pitch set: it is an ambiguity of the global key, not a key change
        path = np.array([gkey if T.key_relation(int(k), gkey) == "relative" else int(k) for k in path])
        regions = K.regions_from_path(path, grid, duration, min_len_s=min_region)
        snapped: list[tuple[float, float, int]] = []
        for i, (a, b, k) in enumerate(regions):
            a2 = a if i == 0 else snap_time(a, downbeats, 4.0)
            b2 = duration if i + 1 == len(regions) else snap_time(b, downbeats, 4.0)
            snapped.append((a2, b2, k))
        regions = [(a, snapped[i + 1][0] if i + 1 < len(snapped) else duration, k) for i, (a, _b, k) in enumerate(snapped)]
        regions = [(a, b, k) for a, b, k in regions if b - a > 1e-3]
        if not regions:
            regions = [(0.0, duration, gkey)]
        regions[0] = (0.0, regions[0][1], regions[0][2])
    items = []
    for a, b, k in regions:
        if len(regions) == 1:
            rconf, rinfo, rev = conf, cinfo, g
        else:
            rev = evidence(a, b)
            rs = K.ensemble(rev)
            inside = [t for t, (wa, wb) in zip(win_top, grid) if wa >= a - 1e-6 and wb <= b + 1e-6]
            rconf, rinfo = K.global_confidence(k, rev, inside, rs)
            if forced:
                rconf = 1.0
        pc, mode = T.key_from_index(k)
        agree = K.agreement_label(rinfo["winners"], k) == "agree" if rinfo["winners"] else False
        items.append({"t": round(a, 6), "d": round(b - a, 6), "key": T.key_name(pc, mode), "tonic_pc": int(pc), "mode": mode,
                      "conf": round(float(rconf), 3), "agree": bool(agree)})
    if len(items) > 1:
        flags.append("key:modulation")
    pc, mode = T.key_from_index(gkey)
    methods: dict[str, Any] = {}
    for n, v in g.methods().items():
        tk = np.argsort(-v)[:3]
        methods[n] = {"top": [T.key_name(*T.key_from_index(int(i))) for i in tk]}
    if skey is not None and g.skey is not None:
        voted = "skey" in methods
        methods.setdefault("skey", {"top": [T.key_name(*T.key_from_index(int(i))) for i in np.argsort(-g.skey)[:3]]})
        methods["skey"]["voted"] = voted
        sw = [int(np.argmax(w.skey)) for w in win_ev if w.skey is not None]
        methods["skey"]["window_agreement"] = round(float(np.mean([1.0 if w == int(np.argmax(g.skey)) else 0.0 for w in sw])), 3) if sw else None
        methods["skey"]["windows"] = len(sw)
        methods["skey"]["p_max"] = round(float(np.max(g.skey_probs)), 3) if g.skey_probs is not None else None
        methods["skey"]["note"] = "export is softmax(softmax(.)); probability recovered by inverting the outer softmax. Windows with top probability < 0.2 do not vote; the vote is weighted by it"
    post = K.top_keys(gscore, 4)
    alts = [{"key": T.key_name(*T.key_from_index(i)), "tonic_pc": T.key_from_index(i)[0], "mode": T.key_from_index(i)[1],
             "score": round(float(gscore[i]), 3), "relation": T.key_relation(i, gkey)} for i, _p in post if i != gkey][:3]
    methods["ensemble"] = {"weights": dict(K.WEIGHTS), "window_agreement": round(cinfo["window_agreement"], 3),
                           "method_credit": round(cinfo["method_credit"], 3), "margin": round(cinfo["margin"], 3),
                           "n_windows": len(grid), "window_s": win_s, "hop_s": hop_s, "alternatives": alts}
    agreement = K.agreement_label(cinfo["winners"], gkey) if cinfo["winners"] else "disagree"
    if agreement == "relative":
        flags.append("key:relative_ambiguity")
    elif agreement in ("parallel", "fifth"):
        flags.append(f"key:{agreement}_ambiguity")
    elif agreement == "disagree":
        flags.append("key:methods_disagree")
    if conf < 0.5 and "key:low_confidence" not in flags:
        flags.append("key:low_confidence")
    meta = {"global": {"key": T.key_name(pc, mode), "tonic_pc": int(pc), "mode": mode, "conf": round(float(conf), 3)},
            "agreement": agreement, "flags": sorted(set(flags)), "methods": methods}
    return items, meta, flags
