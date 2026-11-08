# ruff: noqa: E501
"""Join lyric lines, voices and characters: ``events/singing.json`` and the ``singer`` column (D3, D5, D38).

Voice -> character precedence: the user's intent (``characters.Cn.voices``) > the draft (authored.json
``voice_ids``) > the voices stage's ``proposed_character_id`` > a harness proposal (an unmapped voice is given to a
user character that has no voice yet, in order, or becomes a new character ``Voice Vn``; both are open questions).
Line -> singers precedence: the user's ``line_singers`` (viewer edits) > the voice spans of the line > the nearest
span (a line the voices stage did not cover) > the only voice.

Lead/backing: a line's spans that overlap in time (>= 50 % of the shorter) sing together; one of them is the lead:
an explicit user/draft ``lead`` character first, then the highest span confidence, then the longest span, then the
lowest voice number. Spans that do not overlap (voices trading words inside a line) are each ``lead``. A line the
lyrics mark ``backing`` (parenthetical) is ``backing`` for every singer.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from mvh.contract.ids import make_id

__all__ = ["build_characters", "join_singing", "voice_num", "char_num"]


def voice_num(v: str) -> int:
    m = re.fullmatch(r"V(\d+)", str(v))
    return int(m.group(1)) if m else 10**6


def char_num(c: str) -> int:
    m = re.fullmatch(r"C(\d+)", str(c))
    return int(m.group(1)) if m else 10**6


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def build_characters(user_chars: Mapping[str, Mapping[str, Any]], draft_chars: Sequence[Mapping[str, Any]],
                     voices: Sequence[Mapping[str, Any]], span_voices: Sequence[str],
                     explicit_lb: Mapping[str, str | None]) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str], list[str]]:
    """-> (characters by id, voice -> character, voice -> how ('user'|'draft'|'voices'|'proposed'), open questions).

    ``user_chars``: intent characters {Cn: {name, description, voices, lead_backing}}; ``draft_chars``: authored.json
    characters; ``voices``: meta/voices.json voices; ``span_voices``: voices seen in voice_spans."""
    chars: dict[str, dict[str, Any]] = {}
    questions: list[str] = []
    for cid in sorted(user_chars, key=char_num):
        c = user_chars[cid]
        chars[cid] = {"id": cid, "name": c.get("name"), "description": c.get("description"), "status": "user",
                      "source": "user", "voices_wanted": list(c.get("voices") or []),
                      "lead_backing_explicit": explicit_lb.get(cid)}
    for c in draft_chars:
        cid = str(c.get("id", ""))
        if not re.fullmatch(r"C[1-9]\d*", cid):
            continue
        prov = c.get("provenance") or {}
        if cid in chars:  # user wins; the draft only fills gaps
            for k in ("name", "description"):
                if not chars[cid].get(k) and c.get(k):
                    chars[cid][k] = c.get(k)
                    chars[cid].setdefault("filled_by_draft", []).append(k)
            continue
        chars[cid] = {"id": cid, "name": c.get("name"), "description": c.get("description"), "status": "draft",
                      "source": prov.get("source") if prov.get("source") in ("lyric", "audio", "external", "speculative") else "speculative",
                      "voices_wanted": list(c.get("voice_ids") or []), "lead_backing_explicit": c.get("lead_backing"),
                      "cites": list(prov.get("cites") or [])}
    all_voices: list[str] = []
    for v in [str(v.get("id")) for v in voices] + list(span_voices):
        if re.fullmatch(r"V[1-9]\d*", v) and v not in all_voices:
            all_voices.append(v)
    all_voices.sort(key=voice_num)
    vmap: dict[str, str] = {}
    how: dict[str, str] = {}
    for status in ("user", "draft"):
        for cid in sorted(chars, key=char_num):
            c = chars[cid]
            if c["status"] != status:
                continue
            for v in c["voices_wanted"]:
                if v in vmap and vmap[v] != cid:
                    if status == "user":
                        questions.append(f"Voice {v} is given to both {vmap[v]} and {cid}; which character sings it?")
                    continue
                if v not in all_voices:
                    questions.append(f"{cid} names voice {v}, which the voices stage did not find "
                                     f"(found: {', '.join(all_voices) or 'none'}).")
                    continue
                vmap.setdefault(v, cid)
                how.setdefault(v, status)
    meta_by_id = {str(v.get("id")): v for v in voices}
    # a character whose voices the user (or the draft) named is settled: a voices-stage proposal never adds to it
    settled = set(vmap.values()) | {cid for cid, c in chars.items() if c["status"] == "user" and c["voices_wanted"]}
    for v in all_voices:
        if v in vmap:
            continue
        prop = (meta_by_id.get(v) or {}).get("proposed_character_id")
        if prop and prop in chars and prop not in settled:
            vmap[v], how[v] = prop, "voices"
    voiceless = [cid for cid in sorted(chars, key=char_num)
                 if chars[cid]["status"] == "user" and not any(c == cid for c in vmap.values())]
    for v in all_voices:
        if v in vmap:
            continue
        if voiceless:
            cid = voiceless.pop(0)
            vmap[v], how[v] = cid, "proposed"
            questions.append(f"Is voice {v} the character {cid} ({chars[cid].get('name') or 'unnamed'})? "
                             "The harness assumed so because you did not say which voice is whose.")
            continue
        meta = meta_by_id.get(v) or {}
        prop = meta.get("proposed_character_id")
        cid = prop if (prop and re.fullmatch(r"C[1-9]\d*", str(prop)) and prop not in chars) else None
        if cid is None:
            n = 1
            while make_id("character", n) in chars:
                n += 1
            cid = make_id("character", n)
        hint = meta.get("hint")
        chars[cid] = {"id": cid, "name": str(hint) if hint else f"Voice {v}",
                      "description": None, "status": "draft", "source": "audio", "voices_wanted": [v],
                      "lead_backing_explicit": None, "cites": [{"id": v}], "proposed": True}
        vmap[v], how[v] = cid, "proposed"
    for cid, c in chars.items():
        c["voice_ids"] = sorted([v for v, cc in vmap.items() if cc == cid], key=voice_num)
    unmapped_user = [cid for cid in sorted(chars, key=char_num) if chars[cid]["status"] == "user" and not chars[cid]["voice_ids"]]
    for cid in unmapped_user:
        questions.append(f"No voice was found for {cid} ({chars[cid].get('name') or 'unnamed'}); "
                         "which lines does this character sing (line_singers)?")
    return chars, vmap, how, questions


def join_singing(lines: Sequence[Mapping[str, Any]], spans: Sequence[Mapping[str, Any]],
                 chars: Mapping[str, Mapping[str, Any]], vmap: Mapping[str, str],
                 line_singers: Mapping[str, Sequence[str]], voices_present: Sequence[str],
                 draft_line_chars: Mapping[str, Sequence[str]] | None = None) -> dict[str, Any]:
    """-> {items: singing.json items, singers: {line_id: [cid lead first]}, stats, warnings}."""
    by_line: dict[str, list[Mapping[str, Any]]] = {}
    for s in spans:
        by_line.setdefault(str(s.get("line_id")), []).append(s)
    all_spans = sorted(spans, key=lambda s: float(s["t"]))
    items: list[dict[str, Any]] = []
    singers: dict[str, list[str]] = {}
    stats = {"lines": 0, "from_user": 0, "from_spans": 0, "from_draft": 0, "nearest": 0, "default": 0,
             "review": 0, "multi_singer": 0}
    warnings: list[str] = []
    char_voice = {cid: list(c.get("voice_ids") or []) for cid, c in chars.items()}
    default_voice = sorted(voices_present, key=voice_num)[0] if voices_present else "V1"
    if not voices_present and lines:
        warnings.append("no voices were found for a song with lyrics; every line is given to V1")

    def explicit_lead(cid: str) -> int:
        lb = (chars.get(cid) or {}).get("lead_backing_explicit")
        return 0 if lb == "lead" else (1 if lb in (None, "both") else 2)

    for ln in lines:
        lid = str(ln["id"])
        t0, d = float(ln["t"]), float(ln["d"])
        stats["lines"] += 1
        backing_line = bool(ln.get("backing"))
        line_items: list[dict[str, Any]] = []
        lspans = sorted(by_line.get(lid, []), key=lambda s: (float(s["t"]), voice_num(s.get("voice_id"))))
        override = list(line_singers.get(lid) or [])
        if override:
            stats["from_user"] += 1
            for k, cid in enumerate(override):
                vs = char_voice.get(cid) or []
                sp = next((s for s in lspans if s.get("voice_id") in vs), None)
                v = (sp or {}).get("voice_id") or (vs[0] if vs else (lspans[0]["voice_id"] if lspans else default_voice))
                line_items.append({"t": float(sp["t"]) if sp else t0, "d": float(sp["d"]) if sp else d,
                                   "character_id": cid, "voice_id": v, "line_id": lid,
                                   "lead_backing": "backing" if (backing_line or k > 0) else "lead",
                                   "conf": 1.0, "source": "user", "review": False})
        elif lspans:
            stats["from_spans"] += 1
            # clusters of spans that overlap (sing together)
            clusters: list[list[Mapping[str, Any]]] = []
            for s in lspans:
                s0, s1 = float(s["t"]), float(s["t"]) + float(s["d"])
                for cl in clusters:
                    if any(_overlap(s0, s1, float(o["t"]), float(o["t"]) + float(o["d"]))
                           >= 0.5 * max(1e-6, min(s1 - s0, float(o["d"]))) for o in cl):
                        cl.append(s)
                        break
                else:
                    clusters.append([s])
            for cl in clusters:
                def rank(s):
                    cid = vmap.get(str(s.get("voice_id")), "")
                    return (explicit_lead(cid), -float(s.get("conf", 0.0)), -float(s["d"]), voice_num(s.get("voice_id")))
                order = sorted(cl, key=rank)
                for k, s in enumerate(order):
                    v = str(s.get("voice_id"))
                    cid = vmap.get(v)
                    if cid is None:
                        continue
                    review = bool(s.get("review"))
                    line_items.append({"t": float(s["t"]), "d": float(s["d"]), "character_id": cid, "voice_id": v,
                                       "line_id": lid, "lead_backing": "backing" if (backing_line or k > 0) else "lead",
                                       "conf": float(s.get("conf", 0.5)), "source": "voice_spans", "review": review})
        elif draft_line_chars and draft_line_chars.get(lid):
            stats["from_draft"] += 1
            for k, cid in enumerate(draft_line_chars[lid]):
                vs = char_voice.get(cid) or []
                line_items.append({"t": t0, "d": d, "character_id": cid, "voice_id": vs[0] if vs else default_voice,
                                   "line_id": lid, "lead_backing": "backing" if (backing_line or k > 0) else "lead",
                                   "conf": 0.5, "source": "draft", "review": True})
        else:
            near = None
            if all_spans:
                same_sec = [s for s in all_spans if _section_of(s, lines) == ln.get("section_id")]
                pool = same_sec or all_spans
                near = min(pool, key=lambda s: abs(float(s["t"]) + float(s["d"]) / 2 - (t0 + d / 2)))
            if near is not None and vmap.get(str(near.get("voice_id"))):
                stats["nearest"] += 1
                v = str(near["voice_id"])
                line_items.append({"t": t0, "d": d, "character_id": vmap[v], "voice_id": v, "line_id": lid,
                                   "lead_backing": "backing" if backing_line else "lead", "conf": 0.3,
                                   "source": "nearest", "review": True})
            else:
                stats["default"] += 1
                v = default_voice
                cid = vmap.get(v) or (sorted(chars, key=char_num)[0] if chars else "C1")
                line_items.append({"t": t0, "d": d, "character_id": cid, "voice_id": v, "line_id": lid,
                                   "lead_backing": "backing" if backing_line else "lead",
                                   "conf": 0.5 if len(voices_present) <= 1 else 0.2, "source": "default",
                                   "review": len(voices_present) > 1})
        for it in line_items:
            if it["d"] <= 0:
                it["d"] = max(d, 0.01)
        if any(it["review"] for it in line_items):
            stats["review"] += 1
        lead = [it for it in line_items if it["lead_backing"] == "lead"]
        back = [it for it in line_items if it["lead_backing"] != "lead"]
        order: list[str] = []
        for it in sorted(lead, key=lambda i: (i["t"], voice_num(i["voice_id"]))) + \
                sorted(back, key=lambda i: (voice_num(i["voice_id"]), i["t"])):
            if it["character_id"] not in order:
                order.append(it["character_id"])
        singers[lid] = order
        if len(order) > 1:
            stats["multi_singer"] += 1
        # ties at the same t: lead first (events keep producer order for equal t)
        items.extend(sorted(line_items, key=lambda i: (i["t"], 0 if i["lead_backing"] == "lead" else 1,
                                                       voice_num(i["voice_id"]))))
    return {"items": items, "singers": singers, "stats": stats, "warnings": warnings}


def _section_of(span: Mapping[str, Any], lines: Sequence[Mapping[str, Any]]) -> Any:
    lid = span.get("line_id")
    for ln in lines:
        if ln.get("id") == lid:
            return ln.get("section_id")
    return None
