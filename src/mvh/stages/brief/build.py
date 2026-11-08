# ruff: noqa: E501  (long templates)
"""brief.md (CONTRACT §12, PLAN §4.7): the LLM entry point, <= 4k tokens (target 2.5k; tokens ~ characters / 4),
and the per-section zoom (``mvh brief --section S05``, <= 1.5k tokens).

Every number is copied (rounded) from a file the block names once, e.g. ``(meta/tempo.json)``; ``m:ss.s`` is the
same time in minutes. No lyric text (line ids only; the zoom quotes <= 10 words per line only with ``--lyrics``).
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from mvh.stages.meaning.source import Source

__all__ = ["gather", "render_brief", "render_section", "tokens", "MAX_TOKENS", "TARGET_TOKENS", "SECTION_MAX_TOKENS",
           "flags_from_records", "note_name", "mmss"]

MAX_TOKENS = 4000
TARGET_TOKENS = 2500
SECTION_MAX_TOKENS = 1500
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def tokens(text: str) -> int:
    """The gate's token estimate: characters / 4."""
    return (len(text) + 3) // 4


def mmss(t: float) -> str:
    t = max(0.0, float(t))
    m = int(t // 60)
    s = t - 60 * m
    if round(s, 1) >= 60.0:
        m, s = m + 1, 0.0
    return f"{m}:{s:04.1f}"


def note_name(midi: float | None) -> str:
    if midi is None:
        return "?"
    n = int(round(float(midi)))
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


def _f(x: Any, nd: int = 1) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "?"


def _sec_t(t: float) -> str:
    return f"{float(t):.1f} ({mmss(t)})"


def _ranges(ids: Sequence[str]) -> str:
    if not ids:
        return "-"
    parsed = []
    for i in ids:
        m = re.fullmatch(r"([A-Z]+)(\d+)", str(i))
        if not m:
            return ", ".join(ids)
        parsed.append((m.group(1), int(m.group(2)), len(m.group(2))))
    out = []
    start = prev = parsed[0]
    for cur in parsed[1:] + [None]:
        if cur is not None and cur[0] == prev[0] and cur[1] == prev[1] + 1:
            prev = cur
            continue
        a = f"{start[0]}{start[1]:0{start[2]}d}"
        b = f"{prev[0]}{prev[1]:0{prev[2]}d}"
        out.append(a if a == b else f"{a}-{b}")
        if cur is not None:
            start = prev = cur
    return ", ".join(out)


def _short(s: Any, words: int) -> str:
    w = str(s or "").replace("|", "/").split()
    return " ".join(w[:words]) + (" ..." if len(w) > words else "")


def _ov(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


# ============================================================================================ flags
def flags_from_records(records: Mapping[str, Mapping[str, Any]], tempo: Mapping[str, Any] | None,
                       key: Mapping[str, Any] | None) -> list[str]:
    """The same flags the runner puts in manifest.status.flags (finalize), from the upstream done records."""
    flags: list[str] = []
    for name in sorted(records):
        rec = records[name] or {}
        res = rec.get("result") or {}
        flags += [f"fallback:{f}" for f in res.get("fallbacks", [])]
        if rec.get("status") == "degraded":
            flags.append(f"degraded:{name}")
        if rec.get("status") == "failed":
            flags.append(f"failed:{name}")
    flags += [str(f) for f in ((tempo or {}).get("qa") or {}).get("flags", [])]
    flags += [f"key:{f}" for f in (key or {}).get("flags", [])]
    return list(dict.fromkeys(flags))


# ============================================================================================ gather
def gather(src: Source, flags: Sequence[str] = ()) -> dict[str, Any]:
    d: dict[str, Any] = {"flags": list(flags)}
    for k, rel in (("source", "meta/source.json"), ("identity", "meta/identity.json"), ("tempo", "meta/tempo.json"),
                   ("key", "meta/key.json"), ("loud", "meta/loudness.json"), ("vr", "meta/vocal_range.json"),
                   ("inst", "meta/instruments.json"), ("sep", "meta/separation.json"), ("stems", "meta/stems.json"),
                   ("meaning", "meaning/meaning.json"), ("lyrics", "lyrics/lyrics.json"), ("voices", "meta/voices.json"),
                   ("orphans", "meaning/orphans.json")):
        d[k] = src.json(rel)
    for name in ("sections", "dynamics", "instruments", "vocal_phrases", "hit_points", "mood", "edm_roles", "counts",
                 "grooves", "holds", "moments", "cues", "singing", "visemes", "chords", "key"):
        d["ev_" + name] = src.events(name)
    d["missing"] = list(src.missing)
    lines = (d["lyrics"] or {}).get("lines") or []
    d["lines"] = [{k: v for k, v in ln.items() if k != "text"} | {"_text": ln.get("text")} for ln in lines]
    return d


# ============================================================================================ per-section facts
def section_facts(d: Mapping[str, Any], s: Mapping[str, Any]) -> dict[str, Any]:
    t0, t1 = float(s["t"]), float(s["t"]) + float(s["d"])
    sid = s["id"]
    out: dict[str, Any] = {"id": sid, "t0": t0, "t1": t1}
    # energy (dynamics)
    dyn = d.get("ev_dynamics") or []
    w: dict[str, float] = {}
    for x in dyn:
        ov = _ov(t0, t1, float(x["t"]), float(x["t"]) + float(x["d"]))
        if ov > 0:
            w[x["level"]] = w.get(x["level"], 0.0) + ov
    out["level"] = max(w, key=lambda k: w[k]) if w else None
    # the LUFS shown is the mean_lufs of the longest segment of the dominant level (a value in the file)
    best = max((x for x in dyn if x["level"] == out["level"]),
               key=lambda x: _ov(t0, t1, float(x["t"]), float(x["t"]) + float(x["d"])), default=None)
    out["lufs"] = best.get("mean_lufs") if best else None
    out["dyn_items"] = [x for x in dyn if _ov(t0, t1, float(x["t"]), float(x["t"]) + float(x["d"])) > 0]
    # instruments active >= 50 % of the section
    cov: dict[str, float] = {}
    for x in d.get("ev_instruments") or []:
        ov = _ov(t0, t1, float(x["t"]), float(x["t"]) + float(x["d"]))
        if ov > 0:
            cov[x["instrument"]] = cov.get(x["instrument"], 0.0) + ov * float(x.get("conf", 1.0))
    out["instruments"] = [k for k, v in sorted(cov.items(), key=lambda kv: -kv[1]) if v >= 0.3 * (t1 - t0)]
    # vocals
    vp = [x for x in d.get("ev_vocal_phrases") or [] if _ov(t0, t1, float(x["t"]), float(x["t"]) + float(x["d"])) > 0]
    out["vocal_share"] = sum(_ov(t0, t1, float(x["t"]), float(x["t"]) + float(x["d"])) for x in vp) / max(1e-9, t1 - t0)
    mins = [x["min_midi"] for x in vp if isinstance(x.get("min_midi"), (int, float))]
    maxs = [x["max_midi"] for x in vp if isinstance(x.get("max_midi"), (int, float))]
    out["vocal_lo"] = min(mins) if mins else None
    out["vocal_hi"] = max(maxs) if maxs else None
    out["vocal_phrases"] = vp
    # singers (events/singing.json)
    chars: list[str] = []
    for x in d.get("ev_singing") or []:
        if _ov(t0, t1, float(x["t"]), float(x["t"]) + float(x["d"])) > 0.5 * float(x["d"]) and x["character_id"] not in chars:
            chars.append(x["character_id"])
    out["singers"] = sorted(chars, key=lambda c: int(c[1:]) if c[1:].isdigit() else 999)
    # hits
    hp = [x for x in d.get("ev_hit_points") or [] if t0 <= float(x["t"]) < t1]
    out["hits"] = sorted(hp, key=lambda x: (x.get("rank", 10**6), x["t"]))
    # lines
    out["lines"] = sorted((ln["id"] for ln in d.get("lines") or []
                           if (ln.get("section_id") == sid) or (not ln.get("section_id") and t0 <= float(ln["t"]) < t1)),
                          key=lambda i: (len(i), i))
    # mood
    out["mood"] = next((m for m in d.get("ev_mood") or [] if m.get("section_id") == sid), None)
    # roles
    out["roles"] = [r for r in d.get("ev_edm_roles") or [] if r.get("section_id") == sid
                    or _ov(t0, t1, float(r["t"]), float(r["t"]) + float(r["d"])) >= 0.5 * (t1 - t0)]
    # meaning
    ms = next((m for m in (d.get("meaning") or {}).get("sections") or [] if m.get("section_id") == sid), None)
    out["meaning"] = ms
    # counts
    out["counts"] = [c for c in d.get("ev_counts") or [] if c.get("section_id") == sid]
    out["grooves"] = [g for g in d.get("ev_grooves") or [] if t0 <= float(g["t"]) + 1e-6 < t1]
    out["holds"] = [h for h in d.get("ev_holds") or [] if t0 <= float(h["t"]) < t1]
    out["cues"] = [c for c in d.get("ev_cues") or [] if t0 <= float(c["t"]) < t1 and int(c.get("tier", 4)) <= 3]
    out["chords"] = [c for c in d.get("ev_chords") or [] if _ov(t0, t1, float(c["t"]), float(c["t"]) + float(c["d"])) > 0]
    return out


def _feel(ms: Mapping[str, Any] | None, words: int = 7) -> str:
    if not ms:
        return "-"
    key = "feel" if ms.get("feel") else "meaning"
    txt = ms.get(key)
    if not txt:
        return "-"
    return _short(txt, words) + (" (draft)" if _is_draft(ms, key) else "")


def _is_draft(ms: Mapping[str, Any], field: str) -> bool:
    """True when the field is agent-drafted text: meaning.json field_sources says so per field; a section without
    field_sources falls back to its provenance.status."""
    fs = ms.get("field_sources") or {}
    if field in fs:
        return fs[field] != "user"
    return (ms.get("provenance") or {}).get("status") != "user"


def _mood_cell(m: Mapping[str, Any] | None) -> str:
    if not m:
        return "-"
    tags = (m.get("tags") or [])[:1]
    return f"A{_f(m.get('arousal'), 2)} V{_f(m.get('valence'), 2)}" + (f" {tags[0]}" if tags else "")


def _vocal_cell(f: Mapping[str, Any]) -> str:
    sing = "+".join(f["singers"])
    if f["vocal_share"] <= 0.0 and not sing:
        return "-"
    rng = f"{note_name(f['vocal_lo'])}-{note_name(f['vocal_hi'])}" if f["vocal_lo"] is not None else ""
    parts = [p for p in (sing, f"{f['vocal_share'] * 100:.0f}%" if f["vocal_share"] > 0 else "", rng) if p]
    return " ".join(parts)


def _bars(s: Mapping[str, Any]) -> str:
    try:
        a, n = int(s["start_bar"]), int(s["n_bars"])
    except (KeyError, TypeError, ValueError):
        return "?"
    return f"{a}-{a + n - 1}" if n > 1 else f"{a}"


# ============================================================================================ blocks
def _status_line(d: Mapping[str, Any]) -> str:
    m = d.get("meaning") or {}
    lyr = d.get("lyrics") or {}
    sep = d.get("sep")
    grade = lyr.get("grade")
    lyrics = "none" if not lyr or (not lyr.get("lines") and not grade) else (f"grade {grade}" if grade else "ungraded")
    if lyr.get("instrumental"):
        lyrics = "instrumental"
    stems = "absent" if sep is None else ("degraded" if sep.get("degraded") else "hq")
    vis = "yes" if d.get("ev_visemes") else "no"
    flags = list(d.get("flags") or [])
    orph = len((d.get("orphans") or {}).get("orphans") or [])
    if orph:
        flags.insert(0, f"meaning:orphans={orph}")
    rv = sum(1 for x in d.get("ev_singing") or [] if x.get("review"))
    if rv:
        flags.append(f"singers:review={rv}")
    vr = d.get("vr") or {}
    if vr and isinstance(vr.get("conf"), (int, float)) and vr["conf"] < 0.5 and vr.get("present"):
        flags.append(f"vocal_range:conf={_f(vr['conf'], 2)}")
    if grade in ("C", "D"):
        flags.append(f"lyrics:grade={grade}")
    flags_txt = ", ".join(flags[:14]) + (f", +{len(flags) - 14} more (manifest.json)" if len(flags) > 14 else "")
    line = (f"meaning: {m.get('status', 'pending')} · lyrics: {lyrics} · stems: {stems} · visemes: {vis} · "
            f"flags: {flags_txt or 'none'}")
    if orph:
        line += f"\n\n**Warning**: {orph} meaning claim(s) lost their section after the sections changed (meaning/orphans.json)."
    return line


def _header(d: Mapping[str, Any]) -> list[str]:
    ident = d.get("identity") or {}
    src = d.get("source") or {}
    tempo = d.get("tempo") or {}
    key = d.get("key") or {}
    loud = d.get("loud") or {}
    vr = d.get("vr") or {}
    inst = d.get("inst") or {}
    title = ident.get("title") or src.get("file_name") or "Untitled"
    out = [f"# {title}" + (f" - {ident['artist']}" if ident.get("artist") else ""), "", _status_line(d), "",
           "| field | value |", "|---|---|"]
    if ident.get("album"):
        out.append(f"| album | {ident['album']} (meta/identity.json) |")
    dur = src.get("duration_s") if src.get("duration_s") is not None else ident.get("duration_s")
    if dur is not None:
        out.append(f"| duration | {_f(dur, 1)} s ({mmss(dur)}) (meta/source.json) |")
    if tempo:
        alts = [c for c in tempo.get("candidates") or [] if c.get("relation") != "x1"][:2]
        alt = ("; alt " + ", ".join(f"{c.get('relation')} {_f(c.get('bpm'), 1)}" for c in alts)) if alts else ""
        out.append(f"| tempo | {_f(tempo.get('bpm'), 1)} BPM, {str(tempo.get('feel') or 'normal').replace('_', ' ')} feel, "
                   f"conf {_f(tempo.get('confidence'), 2)}{alt}{', variable' if tempo.get('is_variable') else ''} (meta/tempo.json) |")
        met = tempo.get("meter") or {}
        ch = met.get("changes") or []
        chs = "; changes: " + ", ".join(f"bar {c.get('bar')} -> {c.get('beats_per_bar')}" for c in ch[:4]) if ch else ""
        out.append(f"| meter | {met.get('time_signature', '?')} (conf {_f(met.get('confidence'), 2)}){chs} |")
    if key:
        g = key.get("global") or {}
        out.append(f"| key | {g.get('key', '?')} (conf {_f(g.get('conf'), 2)}, methods {key.get('agreement', '?')}) (meta/key.json) |")
    if loud:
        out.append(f"| loudness | {_f(loud.get('integrated_lufs'), 1)} LUFS, LRA {_f(loud.get('lra_lu'), 1)} LU, "
                   f"true peak {_f(loud.get('true_peak_dbtp'), 1)} dBTP (meta/loudness.json) |")
    if vr:
        if vr.get("present"):
            lo, hi = vr.get("lowest") or {}, vr.get("highest") or {}
            out.append(f"| vocal range | {lo.get('name', '?')}-{hi.get('name', '?')}, tessitura {note_name(vr.get('p10'))}-"
                       f"{note_name(vr.get('p90'))}, {vr.get('register') or 'register unknown'}, conf {_f(vr.get('conf'), 2)} "
                       f"(meta/vocal_range.json) |")
        else:
            out.append(f"| vocal range | no sustained lead vocal ({_f(vr.get('voiced_s'), 1)} voiced s) (meta/vocal_range.json) |")
    summ = sorted(inst.get("summary") or [], key=lambda s: -float(s.get("coverage", 0)))
    if summ:
        out.append("| instrumentation | " + ", ".join(f"{s['instrument']} {float(s.get('coverage', 0)) * 100:.0f}%" for s in summ[:8])
                   + (f"; vocal style {((inst.get('vocal_style') or {}).get('dominant'))}" if (inst.get("vocal_style") or {}).get("dominant") else "")
                   + " (meta/instruments.json) |")
    sep = d.get("sep")
    if sep:
        stems = d.get("stems") or {}
        present = [k for k, v in (stems.get("stems") or {}).items() if isinstance(v, Mapping) and v.get("present")]
        subs = [k[6:] for k in present if k.startswith("drums_")]
        main = [k for k in present if not k.startswith("drums_")]
        txt = (f"{sep.get('variant', '?')}, lead/backing split {'yes' if sep.get('lead_backing_split') else 'no'}"
               + (f"; present: {', '.join(main)}" if main else "") + (f"; drum sub-stems: {', '.join(subs)}" if subs else ""))
        out.append(f"| stems | {txt} (meta/separation.json, meta/stems.json) |")
    return out


LOGLINE_WORDS = 40


def _meaning_block(d: Mapping[str, Any]) -> list[str]:
    m = d.get("meaning") or {}
    status = m.get("status", "pending")
    out = ["", "## Meaning (meaning/meaning.json)"]
    chars = m.get("characters") or []
    voices = {str(v.get("id")): v for v in (d.get("voices") or {}).get("voices") or []}
    if status == "pending":
        out.append("Meaning pending: show the user `meaning/interview.md` and wait (SKILL.md meaning rule); draft gaps "
                   "only into `meaning/authored.json` afterwards.")
    elif m.get("logline"):
        lsrc = (m.get("field_sources") or {}).get("logline")
        is_draft = (lsrc != "user") if lsrc else status != "user"
        out.append(("Draft (not confirmed by the user): " if is_draft else "") + _short(str(m["logline"]), LOGLINE_WORDS))
    if chars:
        out += ["", "| ID | description | voice | sections |", "|---|---|---|---|"]
        for c in chars:
            desc = c.get("name") or c["id"]
            if c.get("description"):
                desc += f": {_short(c['description'], 10)}"
            if (c.get("provenance") or {}).get("status") != "user":
                desc += " (proposed)" if status == "pending" or (c.get("provenance") or {}).get("source") == "audio" else " (draft)"
            elif "draft" in (c.get("field_sources") or {}).values():
                fsd = [k for k, v in (c.get("field_sources") or {}).items() if v == "draft"]
                desc += f" (draft {' + '.join(fsd)})"
            vtxt = ", ".join(f"{v} {_f((voices.get(v) or {}).get('seconds'), 0)} s" if (voices.get(v) or {}).get("seconds") is not None else v
                             for v in c.get("voice_ids") or []) or "-"
            out.append(f"| {c['id']} | {desc} {('(' + c['lead_backing'] + ')') if c.get('lead_backing') else ''} | {vtxt} | {_ranges(c.get('section_ids') or [])} |")
    dn = m.get("do_not") or []
    if dn:
        out += ["", "Do not (the user's words): " + " ".join(f'"{x}"' for x in dn)]
    pal = m.get("palette") or []
    if pal:
        psrc = (m.get("field_sources") or {}).get("palette")
        pdraft = (psrc != "user") if psrc else status != "user"
        out += ["", "Palette" + (" (draft)" if pdraft else "") + ": " + " ".join(pal)]
    else:
        cov = (d.get("source") or {}).get("palette") or []
        if cov:
            out += ["", "Palette: none authored; cover art palette " + " ".join(cov[:8]) + " (meta/source.json)"]
    oq = [q for q in m.get("open_questions") or [] if not q.startswith("The meaning is pending")]
    if oq:
        out.append(f"Open questions: {len(oq)} (meaning/meaning.md).")
    return out


def _section_rows(d: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], sections: Sequence[Mapping[str, Any]],
                  collapse: bool, compact: bool) -> list[str]:
    head = ("| ID | t s (m:ss.s) | bars | label | grp | energy | vocals | hits | lines | mood | feel |" if compact else
            "| ID | t s (m:ss.s) | bars | label | grp | energy | instruments | vocals | hits | lines | mood | feel / meaning |")
    out = ["", "## Sections (events/sections.json, events/dynamics.json, events/instruments.json, events/vocal_phrases.json, "
           "events/singing.json, events/hit_points.json, events/mood.json)", head,
           "|" + "---|" * (head.count("|") - 1)]
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(sections):
        groups.setdefault(str(s.get("repeat_group")), []).append(i)
    done: set[int] = set()
    for i, s in enumerate(sections):
        if i in done:
            continue
        f = facts[i]
        idx = groups.get(str(s.get("repeat_group")), [i]) if collapse else [i]
        done.update(idx)
        roles = " ".join(f"{r.get('role')} {r.get('id')}" for r in f["roles"])
        label = str(s.get("occurrence_label") or s.get("label")) + (f" {roles}" if roles else "")
        if len(idx) > 1:
            ids = ", ".join(sections[j]["id"] for j in idx)
            label = f"{s.get('label')} x{len(idx)}" + (f" {roles}" if roles else "")
            tcell = ", ".join(f"{float(sections[j]['t']):.1f}" for j in idx)
            lines = _ranges([lid for j in idx for lid in facts[j]["lines"]])
        else:
            ids = s["id"]
            tcell = _sec_t(s["t"])
            lines = _ranges(f["lines"])
        energy = f"{f['level'] or '?'} {_f(f['lufs'], 1)}" if f["level"] else "-"
        hits = ", ".join(h["id"] for h in f["hits"][:2]) or "-"
        inst = ", ".join(f["instruments"][:3]) or "-"
        cells = [ids, tcell, _bars(s), label, str(s.get("repeat_group", "-")), energy]
        if not compact:
            cells.append(inst)
        cells += [_vocal_cell(f), hits, lines, _mood_cell(f["mood"]), _feel(f["meaning"], 5 if compact else 8)]
        out.append("| " + " | ".join(cells) + " |")
    return out


def _choreo_block(d: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], n_hits: int = 6, n_holds: int = 3) -> list[str]:
    counts = d.get("ev_counts")
    if counts is None and d.get("ev_hit_points") is None:
        return ["", "## Choreography", "No choreography data (events/counts.json missing)."]
    out = ["", "## Choreography (events/counts.json, events/grooves.json, events/hit_points.json, events/holds.json)"]
    counts = counts or []
    real = [c for c in counts if not c.get("lead_in")]
    lead = [c for c in counts if c.get("lead_in")]
    part = [c for c in real if c.get("partial")]
    out.append(f"{len(real)} eight-counts" + (f" plus the {lead[0]['id']} lead-in" if lead else "")
               + ("; partial: " + ", ".join(f"{c['id']} (len {c.get('len')})" for c in part[:8]) + (" ..." if len(part) > 8 else "") if part else "; no partial counts")
               + ".")
    per = [f"{f['id']} {len(f['counts'])}" for f in facts if f["counts"]]
    if per:
        out.append("Counts per section: " + ", ".join(per) + ".")
    gro = d.get("ev_grooves") or []
    if gro:
        n: dict[str, list[Mapping[str, Any]]] = {}
        for g in gro:
            n.setdefault(g["groove_id"], []).append(g)
        top = sorted(n.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:4]
        out.append(f"Grooves ({len(n)}): " + "; ".join(f"{gid} {len(v)} bars, swing {_f(v[0].get('swing'), 2)}, sync {_f(v[0].get('syncopation'), 2)}"
                                                    for gid, v in top) + ".")
    hp = sorted(d.get("ev_hit_points") or [], key=lambda x: (x.get("rank", 10**6), x["t"]))[:n_hits]
    if hp:
        out.append("Strongest hit points: " + "; ".join(f"{h['id']} {_f(h['t'], 2)} s ({'+'.join((h.get('kinds') or [])[:3])})" for h in hp) + ".")
    holds = d.get("ev_holds") or []
    if holds:
        kinds: dict[str, int] = {}
        for h in holds:
            kinds[h.get("kind", "?")] = kinds.get(h.get("kind", "?"), 0) + 1
        longest = sorted(holds, key=lambda h: (-float(h["d"]), h["t"]))[:n_holds]
        out.append(f"Holds ({len(holds)}: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) + "): longest "
                   + "; ".join(f"{h['id']} {_f(h['t'], 2)} s for {_f(h['d'], 2)} s ({h.get('kind')})" for h in longest) + ".")
    return out


def _moments_block(d: Mapping[str, Any], n: int = 15, desc_words: int = 14) -> list[str]:
    mom = sorted(d.get("ev_moments") or [], key=lambda m: (m.get("rank", 10**6), m["t"]))[:n]
    if not mom:
        return ["", "## Top moments", "No moments (events/moments.json missing)."]
    out = ["", "## Top moments (events/moments.json)", "| rank | t s | cue | kind | description |", "|---|---|---|---|---|"]
    for m in mom:
        out.append(f"| {m.get('rank')} | {_f(m['t'], 2)} | {m.get('cue_id')} | {m.get('kind')} | {_short(m.get('description'), desc_words)} |")
    return out


FOOTER = "Loaders and file catalogue: SKILL.md and CONTRACT.md (lib/mvh.js, lib/mvh_load.py)."


def render_brief(d: Mapping[str, Any], max_tokens: int = MAX_TOKENS, target_tokens: int = TARGET_TOKENS) -> tuple[str, dict[str, Any]]:
    """-> (brief.md text, info {tokens, collapsed, compact, trimmed_rows})."""
    sections = sorted(d.get("ev_sections") or [], key=lambda s: float(s["t"]))
    facts = [section_facts(d, s) for s in sections]
    info = {"collapsed": False, "compact": False, "trimmed_rows": 0, "n_sections": len(sections)}

    def compose(collapse: bool, compact: bool, n_hits: int = 6, n_holds: int = 3, desc_words: int = 14,
                drop_rows: int = 0) -> str:
        parts = _header(d) + _meaning_block(d)
        if sections:
            rows = _section_rows(d, facts, sections, collapse, compact)
            if drop_rows:
                keep = rows[: max(4, len(rows) - drop_rows)]
                omitted = [r.split("|")[1].strip() for r in rows[len(keep):]]
                rows = keep + [f"(rows {omitted[0]} ... {omitted[-1]} omitted to fit 4k tokens: `mvh brief --section <ID>` or tables/sections.csv)"]
            parts += rows
        else:
            parts += ["", "## Sections", "No sections (events/sections.json missing)."]
        parts += _choreo_block(d, facts, n_hits, n_holds) + _moments_block(d, 15, desc_words) + ["", FOOTER, ""]
        return "\n".join(parts)

    text = compose(False, False)
    max_chars = max_tokens * 4
    if len(text) > max_chars:
        info["collapsed"] = True
        text = compose(True, False)
    if len(text) > max_chars:
        info["compact"] = True
        text = compose(True, True, 4, 2, 9)
    drop = 0
    while len(text) > max_chars and drop < len(sections):
        drop += 1
        text = compose(True, True, 4, 2, 9, drop)
    info["trimmed_rows"] = drop
    info["tokens"] = tokens(text)
    info["over_target"] = info["tokens"] > target_tokens
    return text, info


# ============================================================================================ section zoom
def render_section(d: Mapping[str, Any], sid: str, allow_lyrics: bool = False,
                   max_tokens: int = SECTION_MAX_TOKENS) -> str:
    sections = sorted(d.get("ev_sections") or [], key=lambda s: float(s["t"]))
    s = next((x for x in sections if x["id"] == sid), None)
    if s is None:
        raise KeyError(f"no section {sid} (sections: {', '.join(x['id'] for x in sections[:40])})")
    f = section_facts(d, s)
    ident = d.get("identity") or {}

    def compose(n: int) -> str:
        L = [f"# {sid} {s.get('occurrence_label')} - {ident.get('title') or 'song'}", "",
             f"{_sec_t(f['t0'])} to {_sec_t(f['t1'])}, {_f(f['t1'] - f['t0'], 2)} s, bars {_bars(s)}, repeat group "
             f"{s.get('repeat_group')}, label conf {_f(s.get('conf'), 2)} (events/sections.json)"]
        if f["roles"]:
            L.append("EDM roles: " + "; ".join(f"{r['id']} {r.get('role')} {_f(r['t'], 2)} s +{_f(r['d'], 2)} s conf {_f(r.get('conf'), 2)}" for r in f["roles"]) + " (events/edm_roles.json)")
        if f["dyn_items"]:
            L.append("Dynamics: " + "; ".join(f"{x['level']} {_f(x['t'], 1)}-{_f(float(x['t']) + float(x['d']), 1)} s {_f(x.get('mean_lufs'), 1)} LUFS" for x in f["dyn_items"][:n]) + " (events/dynamics.json)")
        if f["instruments"]:
            L.append("Instruments: " + ", ".join(f["instruments"][:8]) + " (events/instruments.json)")
        if f["vocal_phrases"]:
            L.append(f"Vocals: {len(f['vocal_phrases'])} phrases, {f['vocal_share'] * 100:.0f}% of the section, "
                     f"{note_name(f['vocal_lo'])}-{note_name(f['vocal_hi'])} (events/vocal_phrases.json)")
        if f["mood"]:
            m = f["mood"]
            L.append(f"Mood: arousal {_f(m.get('arousal'), 2)}, valence {_f(m.get('valence'), 2)}; tags {', '.join(m.get('tags') or [])} (events/mood.json)")
        if f["chords"]:
            dur: dict[str, float] = {}
            for c in f["chords"]:
                dur[c["label"]] = dur.get(c["label"], 0.0) + _ov(f["t0"], f["t1"], float(c["t"]), float(c["t"]) + float(c["d"]))
            L.append("Chords by time: " + ", ".join(f"{k} {_f(v, 1)} s" for k, v in sorted(dur.items(), key=lambda kv: -kv[1])[:6]) + " (events/chords.json)")
        ms = f["meaning"]
        if ms:
            L += ["", f"## Meaning ({(ms.get('provenance') or {}).get('status')}, meaning/meaning.json)"]
            def tag(k: str) -> str:
                return " (draft)" if _is_draft(ms, k) else ""
            for k, lab in (("feel", "feel"), ("meaning", "meaning"), ("movement_hint", "movement"), ("camera_hint", "camera")):
                if ms.get(k):
                    L.append(f"- {lab}: {ms[k]}{tag(k)}")
            e = ms.get("emotion") or {}
            if e.get("lyric") or e.get("audio"):
                L.append(f"- emotion: lyric {e.get('lyric') or '?'}, audio {e.get('audio') or '?'}"
                         + ("" if e.get("agree") is None else (", agree" if e["agree"] else ", differ"))
                         + tag("emotion.lyric"))
            if ms.get("palette_hint"):
                L.append("- palette: " + " ".join(ms["palette_hint"]) + tag("palette_hint"))
            if ms.get("characters_present"):
                L.append("- characters: " + ", ".join(ms["characters_present"]) + tag("characters_present"))
            for r in ms.get("do_not") or []:
                L.append(f'- do not: "{r}"')
        lines = [ln for ln in d.get("lines") or [] if ln["id"] in set(f["lines"])]
        if lines:
            sing: dict[str, list[str]] = {}
            for x in d.get("ev_singing") or []:
                if x["character_id"] not in sing.setdefault(x["line_id"], []):
                    sing[x["line_id"]].append(x["character_id"])
            L += ["", "## Lines (lyrics/lyrics.json, events/singing.json)"]
            for ln in lines[: n * 4]:
                q = ""
                if allow_lyrics and ln.get("_text"):
                    ws = str(ln["_text"]).split()
                    q = ' "' + " ".join(ws[:10]) + (' ..."' if len(ws) > 10 else '"')
                L.append(f"- {ln['id']} {_f(ln['t'], 2)} s +{_f(ln['d'], 2)} s {'+'.join(sing.get(ln['id'], [])) or '-'} grade {ln.get('grade', '?')}{q}")
            if len(lines) > n * 4:
                L.append(f"- ... {len(lines) - n * 4} more lines (lyrics/lines.tsv)")
        if f["counts"]:
            L += ["", "## Counts and grooves (events/counts.json, events/grooves.json)"]
            L.append("; ".join(f"{c['id']} {_f(c['t'], 2)} s len {c.get('len')}{' partial' if c.get('partial') else ''}"
                               f" accent max {_f(max(c.get('accents') or [0]), 2)}" for c in f["counts"][: n * 2]))
            gcount: dict[str, int] = {}
            for g in f["grooves"]:
                gcount[g["groove_id"]] = gcount.get(g["groove_id"], 0) + 1
            if gcount:
                L.append("Grooves: " + ", ".join(f"{k} x{v}" for k, v in gcount.items()))
        if f["hits"] or f["holds"]:
            L += ["", "## Hits and holds (events/hit_points.json, events/holds.json)"]
            if f["hits"]:
                L.append("; ".join(f"{h['id']} {_f(h['t'], 2)} s rank {h.get('rank')} {'+'.join((h.get('kinds') or [])[:3])}" for h in f["hits"][: n * 2]))
            if f["holds"]:
                L.append("; ".join(f"{h['id']} {_f(h['t'], 2)} s +{_f(h['d'], 2)} s {h.get('kind')}" for h in f["holds"][:n]))
        if f["cues"]:
            L += ["", "## Cues, tiers 1-3 (events/cues.json)"]
            L.append("; ".join(f"{c['id']} {_f(c['t'], 2)} s {c.get('kind')} t{c.get('tier')}" for c in f["cues"][: n * 3]))
            if len(f["cues"]) > n * 3:
                L.append(f"... {len(f['cues']) - n * 3} more: events('cues').between({_f(f['t0'], 2)}, {_f(f['t1'], 2)}, {{minTier: 3}})")
        L.append("")
        return "\n".join(L)

    n = 6
    text = compose(n)
    while tokens(text) > max_tokens and n > 1:
        n -= 1
        text = compose(n)
    return text
