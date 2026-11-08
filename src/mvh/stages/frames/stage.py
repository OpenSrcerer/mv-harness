# ruff: noqa: E501
"""frames stage run(ctx): see the package docstring."""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from mvh.contract import registry
from mvh.runner.spec import StageResult
from mvh.stages.meaning.source import CtxSource

from .export import (
    DEFAULT_EVENTS,
    EVENT_COLUMNS,
    event_columns,
    file_tag,
    frame_times,
    parse_rules,
    sample_frames,
    select_channels,
)

__all__ = ["run"]


def _available(ctx) -> dict[str, str]:
    """channel id -> producing stage, from the upstream done records."""
    out: dict[str, str] = {}
    for d in ctx.spec.deps:
        try:
            rec = ctx.upstream(d).record
        except Exception:  # noqa: BLE001 - an absent upstream has no channels
            continue
        for _fid, chans in (rec.get("curves") or {}).items():
            for cid in chans:
                out.setdefault(cid, d)
    return out


def run(ctx) -> StageResult:
    p = dict(ctx.params)
    src = CtxSource(ctx)
    meta = src.json("meta/source.json") or {}
    if meta.get("n_samples") and meta.get("sample_rate"):
        duration = int(meta["n_samples"]) / int(meta["sample_rate"])
    else:
        duration = float(meta.get("duration_s") or 0.0)
    rules = parse_rules(p.get("fps", 30), int(p.get("frame0", 0)), bool(p.get("early", False)))
    avail = _available(ctx)
    wanted = list(p.get("curves") or [])
    chans = select_channels(sorted(avail), wanted)
    want_spec = "spectrum128" in wanted
    ev_names = list(DEFAULT_EVENTS) if p.get("events", "default") == "default" else [e for e in (p.get("events") or []) if e in EVENT_COLUMNS]
    warnings: list[str] = []
    if duration <= 0:
        warnings.append("meta/source.json has no duration: no frames written")
    curves: dict[str, tuple[np.ndarray, float, str, bool]] = {}
    for cid in chans:
        try:
            c = ctx.upstream(avail[cid]).curve(cid)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"curve {cid} unreadable ({type(e).__name__})")
            continue
        ch = registry.match_channel(cid)
        curves[cid] = (np.asarray(c.values), float(c.rate_hz), str(c.meta.get("resample", ch.resample if ch else "linear")),
                       bool(ch.nan_aware) if ch else False)
    spec_arr = None
    if want_spec:
        try:
            spec_arr, _info = ctx.upstream("spectral").matrix("spectrum128")
        except Exception:  # noqa: BLE001
            warnings.append("spectrum128 requested but not available")
    ev: dict[str, Any] = {}
    if ev_names:
        ev["beats"] = src.events("beats")
        ev["counts"] = src.events("counts")
        ev["sections"] = src.events("sections")
        ev["singing"] = src.events("singing")
        ev["cues"] = src.events("cues")
        ev["hit_points"] = src.events("hit_points")
        lyr = src.json("lyrics/lyrics.json")
        ev["lines"] = [{k: v for k, v in ln.items() if k in ("id", "t", "d")} for ln in (lyr or {}).get("lines") or []] if lyr else None
    files = []
    nan_free = True
    for r in rules:
        n, t, centres = frame_times(r, duration)
        cols: dict[str, Any] = {}
        for cid, (v, rate, pol, nanaw) in curves.items():
            y = sample_frames(v, rate, r, n.size, pol, nanaw)
            nan_free &= bool(np.isfinite(y).all())
            cols[cid] = y
        if spec_arr is not None:
            x = centres * 100.0
            k = np.clip(np.floor(x + 0.5 + 1e-9).astype(np.int64), 0, spec_arr.shape[0] - 1)
            for b in range(spec_arr.shape[1]):
                cols[f"spectrum128.{b:03d}"] = spec_arr[k, b].astype(np.float64) / 255.0
        evc = event_columns(ev_names, r, n, centres, ev) if ev_names else {}
        columns = ["frame", "t"] + list(cols) + [c for c in ev_names if c in evc]
        arrays = {cid: np.round(a, 6) for cid, a in cols.items()}
        rows = []
        for i in range(n.size):
            row = {"frame": int(n[i]), "t": float(t[i])}
            for cid, a in arrays.items():
                row[cid] = float(a[i])
            for cname in evc:
                row[cname] = evc[cname][i]
            rows.append(row)
        tag = file_tag(r)
        rel = f"frames/{tag}fps.csv"
        ctx.writer.table(rel, rows, columns)
        files.append(rel)
        if str(p.get("format", "csv")) == "deforum":
            kf = {cid: ", ".join(f"{int(n[i])}:({float(a[i]):.4f})" for i in range(n.size)) for cid, a in arrays.items()}
            ctx.writer.json(f"frames/{tag}fps.deforum.json", {
                "fps": r.fps, "fps_rational": [r.num, r.den], "frame0": r.frame0, "early": r.early,
                "max_frames": int(n.size), "keyframes": kf,
                "note": "Deforum/ComfyUI schedule strings; frame numbers include frame0; values as in the CSV"})
            files.append(f"frames/{tag}fps.deforum.json")
    if not nan_free:
        raise RuntimeError("frames: a NaN reached the export (never allowed)")
    return StageResult(
        status="ok",
        summary={"files": files, "n_channels": len(curves) + (128 if spec_arr is not None else 0),
                 "event_columns": [c for c in ev_names], "duration_s": round(duration, 6)},
        warnings=warnings,
        provenance={"notes": [f"rules: {json.dumps([[r.num, r.den, r.frame0, r.early] for r in rules])}"]},
    )
