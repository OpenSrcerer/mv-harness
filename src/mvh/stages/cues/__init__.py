# ruff: noqa: E501  (long catalogue tables / docstrings)
"""cues stage (contract v1, owner M2): THE tiered cue list agents cut from, and the top moments.

Tiers (PLAN §5 cues, D15, D37):
* 1 = section start (lead-in one bar), build start (lead-in one bar), drop (lead-in = drop - build start, else one
  bar), breakdown (one bar), and the user's pinned moments (``cues.pinned`` overrides);
* 2 = phrase starts, impacts, stops, silences;
* 3 = hit points, downbeats (strength 0.5, 0.2 for virtual bars);
* 4 = beats, as references to ``events/beats.json`` only (strength / lead-in null), in-pulse beats only.

Candidates within ``snap_s`` (50 ms) of a beat are moved onto that beat so co-timed events merge into ONE cue
(``conventions.merge_cues``, D37: tier = best, kind = highest priority, ``kinds[]``/``sources[]`` list all).
To keep cues.json context-cheap the optional ``kinds``/``sources`` are written only when a cue merges several
candidates (``kinds[0] == kind`` and ``sources[0] == source`` hold whenever they are present).

Moments: tier 1-3 cues scored by kind weight x strength (drops, stops and impacts first), at least ``min_gap_s``
apart, with a short factual description (no lyric text).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from mvh.contract.conventions import merge_cues
from mvh.contract.ids import ref_key
from mvh.runner.spec import StageError, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "cues",
    ('choreo', 'structure', 'dynamics', 'rhythm', 'drums'),
    "main",
    "1.0.0",
    override_keys=('cues.pinned',),
    outputs=catalog_outputs("cues"),
    params={'top_moments': 20, 'snap_s': 0.05, 'beat_cues': 'in_pulse', 'min_moment_gap_s': 2.0},
    module="M2",
    description='Tiered cues.json with lead-in windows and source refs; top moments.',
)

KIND_WEIGHT = {"drop": 1.0, "stop": 0.9, "build_start": 0.85, "impact": 0.85, "breakdown": 0.75, "hit_point": 0.8,
               "section": 0.7, "pinned": 1.0, "silence": 0.6, "phrase": 0.45, "downbeat": 0.25}


def _opt(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def run(ctx) -> StageResult:  # noqa: C901
    p = ctx.params
    notes: list[str] = []
    fallbacks: list[str] = []
    beats = list(ctx.events("beats").items)
    bars = list(ctx.events("bars").items)
    if not beats:
        raise StageError("rhythm produced no beats")
    sections = list(ctx.events("sections").items)
    phrases = list(ctx.events("phrases").items)
    edm = _opt(lambda: list(ctx.events("edm_roles").items), []) or []
    hit_points = _opt(lambda: list(ctx.events("hit_points").items), []) or []
    holds = _opt(lambda: list(ctx.events("holds").items), []) or []
    impacts = _opt(lambda: list(ctx.events("impacts").items), None)
    stops = _opt(lambda: list(ctx.events("stops").items), None)
    silences = _opt(lambda: list(ctx.events("silences").items), None)
    if impacts is None and stops is None:
        fallbacks.append("dynamics:unavailable")
        notes.append("dynamics unavailable: no impact / stop / silence cues")
    impacts, stops, silences = impacts or [], stops or [], silences or []
    drum_hits = _opt(lambda: list(ctx.events("drum_hits").items), []) or []
    bt = np.array([b["t"] for b in beats], float)
    snap = float(p.get("snap_s", 0.05))

    def on_grid(t: float) -> float:
        k = int(np.argmin(np.abs(bt - t)))
        return float(bt[k]) if abs(bt[k] - t) <= snap else float(t)

    ibis = np.diff(bt) if len(bt) > 1 else np.array([0.5])

    def bar_before(t: float) -> float:
        """One nominal bar before t: beats_in_bar of the bar starting at t x the local beat interval."""
        k = int(np.argmin(np.abs(bt - t)))
        bib = int(beats[k].get("beats_in_bar", 4))
        loc = ibis[max(0, k - 4):k] if k > 0 else ibis[:4]
        ibi = float(np.median(loc)) if len(loc) else float(np.median(ibis))
        return bib * ibi

    raw: list[dict[str, Any]] = []
    meta: dict[str, dict[str, Any]] = {}    # key (file, id) -> info for moments

    def add(t, kind, tier, strength, lead_in, file, id_, info=None):
        src = {"file": file, "id": id_}
        raw.append({"t": round(float(t), 6), "kind": kind, "tier": int(tier),
                    "strength": None if strength is None else round(float(np.clip(strength, 0, 1)), 4),
                    "lead_in_s": None if lead_in is None else round(float(max(0.0, lead_in)), 6), "source": src})
        if info is not None:
            meta[f"{file}#{id_}"] = info

    # ---------------- tier 1
    for i, s in enumerate(sections):
        add(s["t"], "section", 1, 1.0 if i == 0 else max(0.5, float(s.get("boundary_conf", 0.5))), bar_before(s["t"]),
            "events/sections.json", s["id"], {"d": s["d"], "desc": f"{s['occurrence_label']} starts (group {s['repeat_group']}, {s['n_bars']} bars)"})
    builds = [e for e in edm if e["role"] == "build"]
    for e in edm:
        if e["role"] == "build":
            add(e["t"], "build_start", 1, e.get("conf", 0.7), bar_before(e["t"]), "events/edm_roles.json", e["id"],
                {"d": e["d"], "desc": f"build ({e['n_bars']} bars): " + ", ".join(e.get("evidence", [])[:3])})
        elif e["role"] == "drop":
            pb = [b for b in builds if b["t"] < e["t"] and e["t"] - (b["t"] + b["d"]) <= 2 * bar_before(e["t"]) + 0.01]
            lead = (e["t"] - pb[-1]["t"]) if pb else bar_before(e["t"])
            add(e["t"], "drop", 1, max(0.6, e.get("conf", 0.8)), lead, "events/edm_roles.json", e["id"],
                {"d": e["d"], "desc": f"drop ({e['n_bars']} bars): " + ", ".join(e.get("evidence", [])[:3])})
        elif e["role"] == "breakdown":
            add(e["t"], "breakdown", 1, e.get("conf", 0.6), bar_before(e["t"]), "events/edm_roles.json", e["id"],
                {"d": e["d"], "desc": f"breakdown ({e['n_bars']} bars): " + ", ".join(e.get("evidence", [])[:2])})
    pinned = ctx.overrides.get("cues.pinned") or []
    for k, pin in enumerate(pinned):
        add(on_grid(float(pin["t"])), "pinned", 1, 1.0, None, "overrides.json", f"cues.pinned:{k}",
            {"d": pin.get("d"), "desc": "pinned by the user" + (f": {str(pin.get('note'))[:60]}" if pin.get("note") else "")})
    # ---------------- tier 2
    sec_t = {round(s["t"], 6) for s in sections}
    for ph in phrases:
        add(ph["t"], "phrase", 2, 0.6 if round(ph["t"], 6) in sec_t else 0.5, None, "events/phrases.json", ph["id"],
            {"d": ph["d"], "desc": f"phrase {ph['id']} ({ph['n_bars']} bars) in {ph['section_id']}"})
    for it in impacts:
        add(on_grid(it["t"]), "impact", 2, it.get("strength", 0.6), None, "events/impacts.json", it["id"],
            {"d": None, "desc": f"impact (+{float(it.get('delta_lu', 0)):.1f} LU, bass {float(it.get('delta_bass_db', 0)):+.1f} dB)"})
    for it in stops:
        add(on_grid(it["t"]), "stop", 2, it.get("strength", 0.8), None, "events/stops.json", it["id"],
            {"d": it.get("gap_s"), "desc": f"hard stop ({float(it.get('gap_s', 0)):.1f} s gap)"})
    for it in silences:
        add(on_grid(it["t"]), "silence", 2, min(1.0, float(it.get("depth_db", 30.0)) / 40.0), None, "events/silences.json", it["id"],
            {"d": it["d"], "desc": f"silence ({float(it['d']):.1f} s)"})
    # ---------------- tier 3
    for h in hit_points:
        add(on_grid(h["t"]), "hit_point", 3, h.get("strength", 0.5), None, "events/hit_points.json", h["id"],
            {"d": None, "desc": "hit point: " + "+".join(h.get("kinds", [])[:6])})
    for b in bars:
        if b["bar"] < 1:
            continue
        add(b["t"], "downbeat", 3, 0.5 if b.get("in_pulse", True) else 0.2, None, "events/bars.json", ref_key("bar", int(b["bar"])),
            {"d": b["d"], "desc": f"downbeat of bar {b['bar']}"})
    # ---------------- tier 4 (references)
    mode = str(p.get("beat_cues", "in_pulse"))
    if mode != "none":
        for b in beats:
            if mode == "in_pulse" and not b.get("in_pulse", True):
                continue
            add(b["t"], "beat", 4, None, None, "events/beats.json", ref_key("beat", int(b["beat_index"])))
    cues = merge_cues(raw)
    for c in cues:
        if "pinned" in c["kinds"] and c["kind"] != "pinned":
            # a user pin keeps its identity (M2-D13): it leads the merged cue whatever its co-timed kinds are
            # (conventions.CUE_KIND_PRIORITY ranks 'pinned' last; change request for the W3 integrator)
            k = c["kinds"].index("pinned")
            c["kinds"].insert(0, c["kinds"].pop(k))
            c["sources"].insert(0, c["sources"].pop(k))
            c["kind"] = "pinned"
            c["source"] = c["sources"][0]
        if len(c["kinds"]) == 1:
            del c["kinds"]
            del c["sources"]
        if c["tier"] == 4:
            c["strength"] = None
            c["lead_in_s"] = None
    w = ctx.writer
    w.events("cues", cues)

    # ---------------- moments
    cand = []
    salient = {"drop", "build_start", "breakdown", "section", "stop", "silence", "impact", "hit_point", "pinned"}
    for c in cues:
        kinds = c.get("kinds") or [c["kind"]]
        if c["tier"] > 3 or not salient.intersection(kinds):
            continue
        srcs = c.get("sources") or [c["source"]]
        best = max(KIND_WEIGHT.get(k, 0.3) for k in kinds)
        score = best * (c["strength"] if c["strength"] is not None else 0.5) + 0.05 * (len(kinds) - 1)
        info = meta.get(f"{c['source']['file']}#{c['source']['id']}", {})
        extra = [meta.get(f"{s['file']}#{s['id']}", {}).get("desc") for s in srcs[1:3]]
        desc = info.get("desc") or c["kind"]
        extra = [e for e in extra if e and not e.startswith("downbeat") and not e.startswith("phrase")]
        if extra:
            desc = desc + "; with " + "; ".join(extra)
        cand.append({"t": c["t"], "score": score, "cue": c, "d": info.get("d"), "desc": desc[:200]})
    cand.sort(key=lambda m: (-m["score"], m["t"]))
    gap = float(p.get("min_moment_gap_s", 2.0))
    chosen: list[dict[str, Any]] = []
    for m in cand:
        if all(abs(m["t"] - q["t"]) >= gap for q in chosen):
            chosen.append(m)
        if len(chosen) >= int(p.get("top_moments", 20)):
            break
    moments = []
    for r, m in enumerate(chosen, start=1):
        c = m["cue"]
        d = m["d"]
        # d: 0.0 for instantaneous moments (the envelope requires a number when d is present; CR M2-1)
        moments.append({"rank": r, "t": c["t"], "d": 0.0 if d is None else round(float(d), 6), "cue_id": c["id"], "kind": c["kind"],
                        "strength": round(float(np.clip(m["score"], 0, 1)), 4), "description": m["desc"]})
    w.events("moments", moments)
    tiers = {k: sum(1 for c in cues if c["tier"] == k) for k in (1, 2, 3, 4)}
    summary = {"n_cues": len(cues), "tiers": {str(k): v for k, v in tiers.items()}, "n_moments": len(moments),
               "top": [f"{m['kind']}@{m['t']:.1f}" for m in moments[:5]], "pinned": len(pinned),
               "n_drum_hits_seen": len(drum_hits), "n_holds_seen": len(holds)}
    prov: dict[str, Any] = {"notes": notes}
    if pinned:
        prov["overrides_applied"] = [{"key": "cues.pinned", "value": pinned}]
    return StageResult(status="ok", summary=summary, fallbacks=sorted(set(fallbacks)), provenance=prov)
