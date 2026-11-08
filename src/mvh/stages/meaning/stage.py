# ruff: noqa: E501  (long templates)
"""The meaning stage (PLAN §8, CONTRACT §7 / D3, D5, D7, D38).

Inputs (never written here): ``meaning/intent.md`` (the user) and ``meaning/authored.json`` (a draft by an agent or
LLM). Outputs: interview.md, request.md + input.json + schema.json (the drafting bundle), meaning.json (merged,
every claim with provenance), meaning.md, orphans.json, events/singing.json and lyrics/lines.tsv.

Merge precedence per field: user (intent.md) > draft (authored.json, its claims keep their own source type
lyric|audio|external|speculative) > harness facts (audio mood words, who sings in each section). Draft claims
never overwrite user claims. ``status`` = user when intent.md says anything, else draft when authored.json
exists, else pending.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from mvh.contract import catalog
from mvh.contract.ids import make_id
from mvh.runner.spec import StageResult

from . import emotion as emo
from .anchor import anchor_claim
from .cites import MAX_QUOTE_WORDS, check_claims, collect_ids, cut_lyric_runs
from .intent import parse_intent
from .singing import build_characters, char_num, join_singing, voice_num
from .source import CtxSource, Source

__all__ = ["run", "build", "mmss"]


def mmss(t: float) -> str:
    t = max(0.0, float(t))
    m = int(t // 60)
    s = t - 60 * m
    if round(s, 1) >= 60.0:
        m, s = m + 1, 0.0
    return f"{m}:{s:04.1f}"


def _read_text(p) -> str | None:
    if p is None:
        return None
    with open(p, encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def _read_json(p) -> Any:
    if p is None:
        return None
    with open(p, encoding="utf-8-sig") as fh:
        return json.load(fh)


# ============================================================================================ stage entry
def run(ctx) -> StageResult:
    src = CtxSource(ctx)
    intent_text = _read_text(ctx.external("intent"))
    authored, authored_err = None, None
    try:
        authored = _read_json(ctx.external("authored"))
    except ValueError as e:  # never quote content (NF5)
        authored_err = f"meaning/authored.json is not valid JSON ({type(e).__name__}); ignored"
    res = build(src, intent_text, authored, dict(ctx.params))
    if authored_err:
        res["warnings"].append(authored_err)
    w = ctx.writer
    w.events("singing", res["singing"], fields=SINGING_FIELDS)
    w.table("lyrics/lines.tsv", res["lines_rows"], LINES_COLUMNS)
    w.json("meaning/meaning.json", res["meaning"])
    w.json("meaning/orphans.json", {"orphans": res["orphans"]})
    w.json("meaning/input.json", res["input"])
    w.json("meaning/schema.json", res["schema"])
    w.text("meaning/interview.md", res["interview"])
    w.text("meaning/request.md", res["request"])
    w.text("meaning/meaning.md", res["meaning_md"])
    return StageResult(status=res["status"], summary=res["summary"], warnings=res["warnings"],
                       fallbacks=res["fallbacks"], provenance={"notes": res["notes"]}, confidence=res["confidence"])


LINES_COLUMNS = [c.name for c in catalog.TABLES_BY_PATH["lyrics/lines.tsv"].columns]
SINGING_FIELDS = {
    "conf": {"unit": "0..1", "type": "number", "description": "confidence of the voice/character assignment"},
    "source": {"unit": None, "type": "string",
               "description": "user (intent.md line_singers) | voice_spans | draft | nearest (line had no span) | default (single/no voice)"},
    "review": {"unit": None, "type": "boolean", "description": "low confidence: check the singer in the viewer"},
}


# ============================================================================================ build (pure)
def _char_field_sources(c: dict[str, Any]) -> dict[str, str]:
    """Per-field origin of a character's name/description: 'user', or 'draft' when the draft filled the gap (or the
    whole character is the draft's / the harness's proposal)."""
    filled = set(c.get("filled_by_draft") or [])
    out: dict[str, str] = {}
    for k in ("name", "description"):
        if c.get("status") != "user" or k in filled:
            if c.get(k):
                out[k] = "draft"
        elif c.get(k):
            out[k] = "user"
    return out


def build(src: Source, intent_text: str | None, authored: Any, params: Mapping[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    fallbacks: list[str] = []
    notes: list[str] = []
    lyrics_to_agents = bool(params.get("lyrics_to_agents", True))
    identity = src.json("meta/identity.json") or {}
    lyrics = src.json("lyrics/lyrics.json")
    sections = sorted(src.events("sections") or [], key=lambda s: float(s["t"]))
    roles = src.events("edm_roles") or []
    mood = src.events("mood") or []
    mood_g = (src.json("meta/mood.json") or {}).get("global") or {}
    vr = src.json("meta/vocal_range.json") or {}
    inst = src.json("meta/instruments.json") or {}
    voices_meta = src.json("meta/voices.json")
    spans = src.events("voice_spans")
    moments = src.events("moments") or []
    cues = src.events("cues") or []
    if lyrics is None:
        fallbacks.append("lyrics:absent")
        warnings.append("lyrics/lyrics.json is missing: no lines, no singing")
    if voices_meta is None or spans is None:
        fallbacks.append("voices:absent")
        if lyrics and lyrics.get("lines"):
            warnings.append("voices are missing: lines are given to one default voice (V1)")
    if not sections:
        fallbacks.append("sections:absent")
        warnings.append("events/sections.json is missing: no per-section meaning")
    voices = list((voices_meta or {}).get("voices") or [])
    spans = list(spans or [])
    lines = sorted(list((lyrics or {}).get("lines") or []), key=lambda ln: (float(ln["t"]), str(ln["id"])))
    duration = float(identity.get("duration_s") or (sections[-1]["t"] + sections[-1]["d"] if sections else 0.0) or 0.0)
    mood_by_sec = {m.get("section_id"): m for m in mood}

    # ---------------------------------------------------------------- inputs
    intent = parse_intent(intent_text)
    warnings += intent["warnings"]
    draft = authored if isinstance(authored, dict) else None
    if authored is not None and draft is None:
        warnings.append("meaning/authored.json is not a JSON object; ignored")
    known = collect_ids([s["id"] for s in sections], [ln["id"] for ln in lines],
                        [w["id"] for w in (lyrics or {}).get("words") or []],
                        [str(v.get("id")) for v in voices], [str(s.get("voice_id")) for s in spans],
                        [c.get("id") for c in cues], [r.get("id") for r in roles],
                        [ln.get("text_group") for ln in lines], [ln.get("repeat_group") for ln in lines],
                        _cue_source_ids(cues))
    draft_problems: list[str] = []
    if draft is not None:
        if draft.get("status") != "draft":
            draft_problems.append("authored.json status is not 'draft' (treated as a draft)")
        from mvh.contract import schemas

        errs = schemas.validate(draft, "mvh/files/meaning")
        if errs:
            draft_problems.append(f"authored.json does not fully match mvh/files/meaning ({len(errs)} problems; the valid parts are used)")
        draft, probs = check_claims(draft, known | _draft_char_ids(draft), duration, status="draft")
        draft_problems += probs
        draft, n_cut = cut_lyric_runs(draft, " ".join(str(ln.get("text") or "") for ln in lines))
        if n_cut:
            draft_problems.append(f"{n_cut} passage(s) of free text quoted more than {MAX_QUOTE_WORDS} consecutive lyric words (cut)")
        notes.append("draft: meaning/authored.json merged (fills gaps only)")
    warnings += [f"authored.json: {p}" for p in draft_problems[:12]]
    if len(draft_problems) > 12:
        warnings.append(f"authored.json: {len(draft_problems) - 12} more problems")

    # ---------------------------------------------------------------- characters + singing
    explicit_lb = {cid: c.get("lead_backing") for cid, c in intent["characters"].items()}
    chars, vmap, vhow, questions = build_characters(
        intent["characters"], (draft or {}).get("characters") or [], voices,
        sorted({str(s.get("voice_id")) for s in spans}, key=voice_num), explicit_lb)
    draft_line_chars: dict[str, list[str]] = {}
    for c in (draft or {}).get("characters") or []:
        for lid in c.get("line_ids") or []:
            draft_line_chars.setdefault(str(lid), []).append(str(c.get("id")))
    voices_present = sorted({str(v.get("id")) for v in voices} | {str(s.get("voice_id")) for s in spans}, key=voice_num)
    if lines and not chars:
        # lyrics but no voices and no characters: one default character for the default voice
        chars["C1"] = {"id": "C1", "name": "Lead voice", "description": None, "status": "draft", "source": "audio",
                       "voices_wanted": ["V1"], "lead_backing_explicit": None, "voice_ids": ["V1"], "proposed": True}
        vmap["V1"] = "C1"
        vhow["V1"] = "proposed"
    sing = join_singing(lines, spans, chars, vmap, intent["line_singers"], voices_present, draft_line_chars)
    warnings += sing["warnings"]
    unknown_line_ovr = [lid for lid in intent["line_singers"] if lid not in {ln["id"] for ln in lines}]
    if unknown_line_ovr:
        questions.append(f"line_singers names {len(unknown_line_ovr)} line(s) that no longer exist "
                         f"({', '.join(unknown_line_ovr[:5])}); lyric line ids changed?")
    unknown_chars = sorted({c for v in intent["line_singers"].values() for c in v if c not in chars}, key=char_num)
    for cid in unknown_chars:
        chars[cid] = {"id": cid, "name": None, "description": None, "status": "user", "source": "user",
                      "voices_wanted": [], "lead_backing_explicit": None, "voice_ids": []}
        questions.append(f"line_singers uses {cid}, which has no entry under characters (name, voice)")
    singing_items = sing["items"]
    lines_by_id = {ln["id"]: ln for ln in lines}
    sec_of_t = _section_lookup(sections)
    char_lines: dict[str, list[str]] = {}
    char_secs: dict[str, list[str]] = {}
    char_lb: dict[str, set[str]] = {}
    for it in singing_items:
        cid = it["character_id"]
        if it["line_id"] not in char_lines.setdefault(cid, []):
            char_lines[cid].append(it["line_id"])
        sid = lines_by_id.get(it["line_id"], {}).get("section_id") or sec_of_t(it["t"] + it["d"] / 2)
        if sid and sid not in char_secs.setdefault(cid, []):
            char_secs[cid].append(sid)
        char_lb.setdefault(cid, set()).add(it["lead_backing"])

    characters_out = []
    for cid in sorted(chars, key=char_num):
        c = chars[cid]
        lbset = char_lb.get(cid, set())
        computed = ("both" if len(lbset) > 1 else next(iter(lbset))) if lbset else None
        lb = computed or c.get("lead_backing_explicit")
        cites = [{"id": v} for v in c.get("voice_ids") or []] + list(c.get("cites") or [])
        cites = [x for i, x in enumerate(cites) if x not in cites[:i]]
        characters_out.append({
            "id": cid, "name": c.get("name") or f"Character {cid}", "description": c.get("description"),
            "voice_ids": list(c.get("voice_ids") or []), "lead_backing": lb if lb in ("lead", "backing", "both") else None,
            "line_ids": char_lines.get(cid, []), "section_ids": sorted(char_secs.get(cid, []), key=_sec_num),
            "provenance": {"source": c.get("source", "user") if c.get("status") == "user" else c.get("source", "speculative"),
                           "status": "user" if c.get("status") == "user" else "draft", "cites": cites},
            "voice_mapping": {v: vhow.get(v, "proposed") for v in c.get("voice_ids") or []},
            "field_sources": _char_field_sources(c),
        })

    # ---------------------------------------------------------------- sections
    user_claims = list(intent["sections"])
    anchored_user: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    orphans: list[dict[str, Any]] = []
    reanchored = 0
    for cl in user_claims:
        a = anchor_claim(cl, sections, roles)
        if a["section_ids"]:
            reanchored += int(a["reanchored"])
            for sid in a["section_ids"]:
                anchored_user.setdefault(sid, []).append((a["specificity"], cl))
        elif a["old_section_id"]:
            orphans.append(_orphan(a["old_section_id"], cl, a["orphan_reason"], "user"))
        else:
            questions.append(f"Your note for '{cl['key']}' matched no section ({a['orphan_reason']}).")
    anchored_draft: dict[str, list[dict[str, Any]]] = {}
    for ds in (draft or {}).get("sections") or []:
        cl = {"key": ds.get("section_id"), "t0": ds.get("t0"), "t1": ds.get("t1"), **ds}
        a = anchor_claim(cl, sections, roles)
        if a["section_ids"]:
            reanchored += int(a["reanchored"])
            for sid in a["section_ids"]:
                anchored_draft.setdefault(sid, []).append(ds)
        else:
            orphans.append(_orphan(str(ds.get("section_id") or "S00"), ds, a["orphan_reason"], "draft"))
    global_dn = list(intent["do_not"])
    sections_out = []
    for s in sections:
        sid = s["id"]
        ucl = [c for _sp, c in sorted(anchored_user.get(sid, []), key=lambda x: -x[0])]
        dcl = anchored_draft.get(sid, [])
        fsrc: dict[str, str] = {}

        def pick(ufield: str, dfield: str, fname: str):
            for c in ucl:
                if c.get(ufield):
                    fsrc[fname] = "user"
                    return c[ufield]
            for c in dcl:
                if c.get(dfield):
                    fsrc[fname] = "draft"
                    return c[dfield]
            return None

        feel = pick("feel", "feel", "feel")
        meaning_txt = pick("meaning", "meaning", "meaning")
        movement = pick("movement", "movement_hint", "movement_hint")
        camera = pick("camera", "camera_hint", "camera_hint")
        lyric_emo = None
        for c in ucl:
            if c.get("emotion"):
                lyric_emo, fsrc["emotion.lyric"] = c["emotion"], "user"
                break
        if lyric_emo is None:
            for c in dcl:
                e = (c.get("emotion") or {}).get("lyric") if isinstance(c.get("emotion"), Mapping) else None
                if e:
                    lyric_emo, fsrc["emotion.lyric"] = e, "draft"
                    break
        m = mood_by_sec.get(sid)
        audio_emo = emo.audio_word(m)
        if audio_emo:
            fsrc["emotion.audio"] = "audio"
        palette_hint: list[str] = []
        for c in ucl:
            if c.get("palette"):
                palette_hint, fsrc["palette_hint"] = list(c["palette"]), "user"
                break
        if not palette_hint:
            for c in dcl:
                ph = [h for h in c.get("palette_hint") or [] if isinstance(h, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", h)]
                if ph:
                    palette_hint, fsrc["palette_hint"] = ph, "draft"
                    break
        present: list[str] = []
        for c in ucl:
            if c.get("characters"):
                present, fsrc["characters_present"] = list(c["characters"]), "user"
                break
        if not present:
            for c in dcl:
                if c.get("characters_present"):
                    present = [x for x in c["characters_present"] if x in chars]
                    if present:
                        fsrc["characters_present"] = "draft"
                        break
        if not present:
            present = _present_in(sid, s, singing_items, lines_by_id)
            if present:
                fsrc["characters_present"] = "audio"
        dn: list[str] = []
        for c in ucl:
            dn += [x for x in c.get("do_not") or [] if x not in dn]
        dn += [x for x in global_dn if x not in dn]
        used_user = any(v == "user" for v in fsrc.values())
        used_draft = any(v == "draft" for v in fsrc.values())
        if used_user:
            prov = {"source": "user", "status": "user"}
        elif used_draft:
            dprov = (dcl[0].get("provenance") or {}) if dcl else {}
            prov = {"source": dprov.get("source", "speculative"), "status": "draft"}
        else:
            prov = {"source": "audio", "status": "draft"}
        prov["cites"] = [{"id": sid, "t0": round(float(s["t"]), 6), "t1": round(float(s["t"]) + float(s["d"]), 6)}]
        sections_out.append({
            "section_id": sid, "t0": round(float(s["t"]), 6), "t1": round(float(s["t"]) + float(s["d"]), 6),
            "occurrence_label": str(s.get("occurrence_label") or f"{s.get('label')}#{s.get('occurrence', 1)}"),
            "feel": feel, "meaning": meaning_txt,
            "emotion": {"lyric": lyric_emo, "audio": audio_emo, "agree": emo.agree(lyric_emo, m)},
            "palette_hint": palette_hint, "movement_hint": movement, "camera_hint": camera,
            "characters_present": sorted(present, key=char_num), "do_not": dn, "provenance": prov,
            "label": s.get("label"), "field_sources": dict(sorted(fsrc.items())),
        })
    if reanchored:
        notes.append(f"re-anchored {reanchored} per-section claim(s) by time overlap")
    if orphans:
        warnings.append(f"{len(orphans)} meaning claim(s) lost their section (meaning/orphans.json)")

    # ---------------------------------------------------------------- global fields
    d = draft or {}
    gsrc: dict[str, str] = {}

    def g(key: str):
        if intent.get(key):
            gsrc[key] = "user"
            return intent[key]
        if d.get(key):
            gsrc[key] = "draft"
            return d.get(key)
        return None

    def claims(key: str) -> list[dict[str, Any]]:
        if intent.get(key):
            gsrc[key] = "user"
            return [{"text": t, "source": "user", "cites": [], "status": "user"} for t in intent[key]]
        if d.get(key):
            gsrc[key] = "draft"
            return list(d[key])
        return []

    perspective = {"narrator": intent["perspective"]["narrator"] or (d.get("perspective") or {}).get("narrator"),
                   "addressee": intent["perspective"]["addressee"] or (d.get("perspective") or {}).get("addressee")}
    palette = list(intent["palette"])
    palette_names = list(intent["palette_names"])
    if palette:
        gsrc["palette"] = "user"
    elif d.get("palette"):
        palette = [h for h in d["palette"] if isinstance(h, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", h)]
        gsrc["palette"] = "draft"
    for bad in intent["palette_unparsed"]:
        questions.append(f"Palette colour '{bad}' was not understood; give it as a hex code (#rrggbb).")
    motifs = _motifs(intent, d, lines_by_id, gsrc)
    has_user = intent["present"] and (any(intent.get(k) for k in ("logline", "summary", "setting", "tone", "themes",
                                                                   "symbolism", "do_not", "palette", "motifs", "sections",
                                                                   "characters", "line_singers"))
                                      or any(intent["perspective"].values()))
    status = "user" if has_user else ("draft" if draft is not None else "pending")
    if intent["present"] and not has_user:
        warnings.append("meaning/intent.md exists but no answer was recognised (see the template in meaning/interview.md)")
    open_q = list(dict.fromkeys(questions))
    if sing["stats"]["review"]:
        open_q.append(f"{sing['stats']['review']} lyric line(s) have a low-confidence singer; check them in the viewer "
                      "(Lyrics & singers lane) or list them under line_singers.")
    for q in (d.get("open_questions") or [])[:10]:
        if isinstance(q, str) and q.strip():
            open_q.append(f"draft asks: {q.strip()}")
    for r in (d.get("do_not") or [])[:10]:
        if isinstance(r, str) and r.strip() and r.strip() not in global_dn:
            open_q.append(f"draft suggests a do-not rule (not applied until you add it to intent.md): {r.strip()}")
    if status == "pending":
        open_q.insert(0, "The meaning is pending: answer meaning/interview.md in meaning/intent.md (the user), or let an "
                         "agent draft the gaps into meaning/authored.json after the user has seen the questions.")
    meaning = {
        "schema": "mvh/files/meaning", "schema_version": catalog.CONTRACT_VERSION, "status": status,
        "logline": g("logline"), "summary": g("summary"), "themes": claims("themes"), "perspective": perspective,
        "characters": characters_out, "setting": g("setting"), "motifs": motifs, "symbolism": claims("symbolism"),
        "sections": sections_out, "palette": palette, "tone": g("tone"), "do_not": global_dn,
        "open_questions": open_q, "palette_names": palette_names, "field_sources": dict(sorted(gsrc.items())),
        "intent_form": intent["form"], "draft_used": draft is not None,
    }
    meaning, final_probs = check_claims(meaning, known | set(chars) | {m["id"] for m in motifs}, duration, status="user")
    # check_claims stamps one status on everything; restore the per-claim origin
    _restore_status(meaning, characters_out, sections_out, motifs, gsrc)
    if final_probs:
        notes.append(f"merged meaning: {len(final_probs)} citation repairs")

    # ---------------------------------------------------------------- lines.tsv
    rows = []
    for ln in lines:
        rows.append({"id": ln["id"], "t": float(ln["t"]), "d": float(ln["d"]), "section_id": ln.get("section_id"),
                     "singer": "+".join(sing["singers"].get(ln["id"], [])) or None,
                     "repeat_group": ln.get("repeat_group"), "grade": ln.get("grade") or (lyrics or {}).get("grade") or "D",
                     "text": (ln.get("text") or "") if lyrics_to_agents else ""})

    # ---------------------------------------------------------------- bundle + docs
    facts_ctx = {"identity": identity, "lyrics": lyrics, "sections": sections, "roles": roles, "mood": mood_by_sec,
                 "mood_g": mood_g, "vr": vr, "inst": inst, "voices": voices, "spans": spans, "cues": cues,
                 "moments": moments, "lines": lines, "chars": characters_out, "singers": sing["singers"],
                 "stats": sing["stats"], "duration": duration, "lyrics_to_agents": lyrics_to_agents}
    from .docs import interview_md, meaning_md, request_md

    gaps = _gaps(meaning, intent)
    inp = {
        "schema_version": catalog.CONTRACT_VERSION,
        "song": {"title": identity.get("title"), "artist": identity.get("artist"), "duration_s": round(duration, 6)},
        "sections": [{"id": s["id"], "t": round(float(s["t"]), 6), "d": round(float(s["d"]), 6), "label": str(s.get("label"))}
                     for s in sections],
        "facts": _facts(facts_ctx, intent, gaps),
        "lines_file": "lyrics/lines.tsv" if (lyrics_to_agents and lines) else None,
    }
    schema = _draft_schema()
    draft_mode = str(params.get("draft", "agent"))
    interview = interview_md(facts_ctx, intent, meaning)
    request = request_md(facts_ctx, meaning, gaps, draft_mode, lyrics_to_agents)
    mmd = meaning_md(identity, meaning, orphans)
    n_review = sing["stats"]["review"]
    conf = {"user": 0.9, "draft": 0.6, "pending": 0.3}[status]
    if n_review and lines:
        conf *= max(0.5, 1.0 - n_review / max(1, len(lines)))
    summary = {
        "status": status, "intent_form": intent["form"], "draft": draft is not None,
        "n_characters": len(characters_out), "n_voices": len(voices_present), "n_lines": len(lines),
        "multi_singer_lines": sing["stats"]["multi_singer"], "review_lines": n_review,
        "lines_by_source": {k: v for k, v in sing["stats"].items() if k in ("from_user", "from_spans", "from_draft", "nearest", "default") and v},
        "orphans": len(orphans), "open_questions": len(open_q),
    }
    stage_status = "ok" if not (fallbacks or orphans) else "degraded"
    return {"singing": singing_items, "lines_rows": rows, "meaning": meaning, "orphans": orphans, "input": inp,
            "schema": schema, "interview": interview, "request": request, "meaning_md": mmd, "status": stage_status,
            "summary": summary, "warnings": warnings, "fallbacks": fallbacks, "notes": notes,
            "confidence": round(conf, 3), "intent": intent, "characters": characters_out, "singers": sing["singers"],
            "stats": sing["stats"]}


# ============================================================================================ helpers
def _sec_num(sid: str) -> int:
    m = re.fullmatch(r"S(\d+)", str(sid))
    return int(m.group(1)) if m else 10**6


def _cue_source_ids(cues: Sequence[Mapping[str, Any]]) -> list[str]:
    out = []
    for c in cues:
        for s in [c.get("source")] + list(c.get("sources") or []):
            if isinstance(s, Mapping) and s.get("id") and ":" not in str(s["id"]):
                out.append(str(s["id"]))
    return out


def _draft_char_ids(d: Mapping[str, Any]) -> set[str]:
    return {str(c.get("id")) for c in d.get("characters") or [] if isinstance(c, Mapping)} | \
        {str(m.get("id")) for m in d.get("motifs") or [] if isinstance(m, Mapping)}


def _section_lookup(sections: Sequence[Mapping[str, Any]]):
    def f(t: float) -> str | None:
        for s in sections:
            if float(s["t"]) <= t < float(s["t"]) + float(s["d"]):
                return s["id"]
        return None
    return f


def _present_in(sid: str, s: Mapping[str, Any], items: Sequence[Mapping[str, Any]],
                lines_by_id: Mapping[str, Mapping[str, Any]]) -> list[str]:
    t0, t1 = float(s["t"]), float(s["t"]) + float(s["d"])
    out: list[str] = []
    for it in items:
        ln = lines_by_id.get(it["line_id"]) or {}
        inside = ln.get("section_id") == sid if ln.get("section_id") else (t0 <= it["t"] + it["d"] / 2 < t1)
        if inside and it["character_id"] not in out:
            out.append(it["character_id"])
    return out


def _orphan(old_id: str, claim: Mapping[str, Any], reason: str | None, origin: str) -> dict[str, Any]:
    t0, t1 = claim.get("t0"), claim.get("t1")
    known_range = isinstance(t0, (int, float)) and isinstance(t1, (int, float))
    c = {k: v for k, v in claim.items() if k not in ("key",) and v not in (None, [], "")}
    c["origin"] = origin
    old = old_id if re.fullmatch(r"S\d{2,}", str(old_id)) else "S00"
    return {"old_section_id": old, "t_range": [round(float(t0), 6), round(float(t1), 6)] if known_range else [0.0, 0.0],
            "occurrence_label": claim.get("occurrence_label"), "claim": c,
            "reason": (reason or "lost its section") + ("" if known_range else " (time range unknown)")}


def _motifs(intent: Mapping[str, Any], d: Mapping[str, Any], lines_by_id: Mapping[str, Mapping[str, Any]],
            gsrc: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    if intent["motifs"]:
        gsrc["motifs"] = "user"
        for k, m in enumerate(intent["motifs"], 1):
            occ = [{"t": round(float(lines_by_id[lid]["t"]), 6), "d": round(float(lines_by_id[lid]["d"]), 6), "line_id": lid}
                   for lid in m["lines"] if lid in lines_by_id]
            out.append({"id": make_id("motif", k), "name": m["name"], "occurrences": occ,
                        "provenance": {"source": "user", "status": "user", "cites": [{"id": o["line_id"]} for o in occ]},
                        **({"note": m["note"]} if m.get("note") else {})})
        return out
    if d.get("motifs"):
        gsrc["motifs"] = "draft"
        return [dict(m) for m in d["motifs"] if isinstance(m, Mapping) and m.get("id") and m.get("name")]
    return out


def _restore_status(meaning: dict[str, Any], chars, secs, motifs, gsrc) -> None:
    by_id = {c["id"]: c for c in chars}
    for c in meaning["characters"]:
        c["provenance"]["status"] = by_id[c["id"]]["provenance"]["status"]
        if c["provenance"]["status"] == "draft" and c["provenance"]["source"] == "user":
            c["provenance"]["source"] = "speculative"
    sec_by = {s["section_id"]: s for s in secs}
    for s in meaning["sections"]:
        s["provenance"]["status"] = sec_by[s["section_id"]]["provenance"]["status"]
    mot_by = {m["id"]: m for m in motifs}
    for m in meaning["motifs"]:
        m["provenance"]["status"] = (mot_by.get(m["id"]) or m)["provenance"].get("status", "draft")
    for key in ("themes", "symbolism"):
        st = "user" if gsrc.get(key) == "user" else "draft"
        for cl in meaning[key]:
            cl["status"] = st


def _gaps(meaning: Mapping[str, Any], intent: Mapping[str, Any]) -> list[str]:
    gaps = []
    for k in ("logline", "summary", "setting", "tone"):
        if not meaning.get(k):
            gaps.append(k)
    for k in ("themes", "motifs", "symbolism", "palette"):
        if not meaning.get(k):
            gaps.append(k)
    if not any((meaning.get("perspective") or {}).values()):
        gaps.append("perspective")
    for c in meaning.get("characters") or []:
        if c["provenance"]["status"] != "user" or not c.get("description"):
            gaps.append(f"characters.{c['id']}")
    for s in meaning.get("sections") or []:
        missing = [f for f in ("feel", "meaning", "movement_hint", "camera_hint") if not s.get(f)]
        if not s["emotion"].get("lyric"):
            missing.append("emotion.lyric")
        if not s.get("palette_hint"):
            missing.append("palette_hint")
        if missing:
            gaps.append(f"sections.{s['section_id']}: " + ", ".join(missing))
    return gaps


def _facts(fc: Mapping[str, Any], intent: Mapping[str, Any], gaps: list[str]) -> dict[str, Any]:
    ident = fc["identity"]
    lyr = fc["lyrics"] or {}
    lines = fc["lines"]
    groups: dict[str, list[str]] = {}
    for ln in lines:
        if ln.get("repeat_group"):
            groups.setdefault(ln["repeat_group"], []).append(ln["id"])
    tgroups: dict[str, list[str]] = {}
    for ln in lines:
        tgroups.setdefault(str(ln.get("text_group")), []).append(ln["id"])
    roles_by_sec: dict[str, list[str]] = {}
    for r in fc["roles"]:
        roles_by_sec.setdefault(str(r.get("section_id")), []).append(f"{r.get('role')} {r.get('id')}")
    secs = []
    for s in fc["sections"]:
        m = fc["mood"].get(s["id"]) or {}
        sl = [ln["id"] for ln in lines if ln.get("section_id") == s["id"]]
        singers = sorted({c for lid in sl for c in fc["singers"].get(lid, [])}, key=char_num)
        secs.append({"id": s["id"], "t": round(float(s["t"]), 3), "d": round(float(s["d"]), 3),
                     "occurrence_label": s.get("occurrence_label"), "repeat_group": s.get("repeat_group"),
                     "edm_roles": roles_by_sec.get(s["id"], []),
                     "mood": {"valence": m.get("valence"), "arousal": m.get("arousal"), "tags": m.get("tags", [])} if m else None,
                     "audio_emotion": emo.audio_word(m), "lines": sl, "singers": singers})
    vr = fc["vr"]
    facts = {
        "identity": {k: ident.get(k) for k in ("title", "artist", "album", "credits")},
        "lyrics": {"grade": lyr.get("grade"), "instrumental": lyr.get("instrumental"), "language": lyr.get("language"),
                   "n_lines": len(lines), "source": (lyr.get("source") or {}).get("kind")},
        "voices": [{"id": str(v.get("id")), "seconds": v.get("seconds"), "n_lines": v.get("n_lines"), "hint": v.get("hint"),
                    "character_id": next((c["id"] for c in fc["chars"] if v.get("id") in c["voice_ids"]), None)}
                   for v in fc["voices"]],
        "characters": [{"id": c["id"], "name": c["name"], "voice_ids": c["voice_ids"], "status": c["provenance"]["status"],
                        "lead_backing": c["lead_backing"], "n_lines": len(c["line_ids"])} for c in fc["chars"]],
        "repeat_groups": groups,
        "hooks": {k: v for k, v in tgroups.items() if len(v) > 1},
        "sections": secs,
        "mood_global": fc["mood_g"] or None,
        "vocal_range": {"present": vr.get("present"), "lowest": (vr.get("lowest") or {}).get("name"),
                        "highest": (vr.get("highest") or {}).get("name"), "register": vr.get("register")} if vr else None,
        "instruments": [s.get("instrument") for s in sorted(fc["inst"].get("summary") or [], key=lambda s: -float(s.get("coverage", 0)))][:10],
        "vocal_style": (fc["inst"].get("vocal_style") or {}).get("dominant"),
        "cues_tier1": [{"id": c["id"], "t": round(float(c["t"]), 3), "kind": c.get("kind")} for c in fc["cues"] if c.get("tier") == 1],
        "moments": [{"rank": m.get("rank"), "t": round(float(m["t"]), 3), "cue_id": m.get("cue_id"), "kind": m.get("kind"),
                     "description": m.get("description")} for m in sorted(fc["moments"], key=lambda m: m.get("rank", 99))][:15],
        "user_fixed": sorted(k for k in ("logline", "summary", "setting", "tone", "themes", "palette", "do_not", "motifs",
                                          "symbolism") if intent.get(k)),
        "gaps": gaps,
    }
    return facts


def _draft_schema() -> dict[str, Any]:
    """mvh/files/meaning with every $ref inlined, so a drafting agent can validate without the schema folder."""
    from mvh.contract import schemas

    root = schemas.load("mvh/files/meaning")

    def inline(x: Any, depth: int = 0) -> Any:
        if isinstance(x, dict):
            if "$ref" in x and depth < 8:
                ref = str(x["$ref"])
                sid = "mvh/" + ref.split("/schema/", 1)[1].rsplit(".schema.json", 1)[0]
                sub = schemas.load(sid)
                sub = {k: v for k, v in sub.items() if k not in ("$schema", "$id")}
                return inline(sub, depth + 1)
            return {k: inline(v, depth) for k, v in x.items()}
        if isinstance(x, list):
            return [inline(v, depth) for v in x]
        return x

    out = inline(root)
    out["description"] = ("JSON Schema for meaning/authored.json (a draft: status must be 'draft'; claims are typed "
                          "lyric|audio|external|speculative and cite ids or time ranges; quotes <= 10 words). "
                          + str(out.get("description", "")))
    return out
