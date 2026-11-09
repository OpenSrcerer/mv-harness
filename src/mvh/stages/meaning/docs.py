"""Human-facing texts of the meaning stage: interview.md (questions + the YAML template), request.md (the drafting
agent's instructions) and meaning.md. No lyric text beyond quotes of at most 8 words (NF5)."""
from __future__ import annotations

from typing import Any, Mapping

from .emotion import audio_word
from .singing import char_num

__all__ = ["interview_md", "request_md", "meaning_md", "yaml_template"]


def _mmss(t: float) -> str:
    from .stage import mmss

    return mmss(t)


def _q(s: Any) -> str:
    """A YAML-safe double-quoted scalar."""
    if s is None:
        return '""'
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "\\n").replace("\t", "\\t") + '"'


def _quote(text: str | None, n: int = 8) -> str:
    words = (text or "").split()
    if not words:
        return ""
    q = " ".join(words[:n])
    return f'"{q}{" ..." if len(words) > n else ""}"'


def _ranges(ids: list[str]) -> str:
    """['L001','L002','L003','L007'] -> 'L001-L003, L007'."""
    if not ids:
        return "-"
    nums = []
    for i in ids:
        try:
            nums.append((i[:1], int(i[1:]), len(i) - 1))
        except ValueError:
            return ", ".join(ids)
    out, start, prev = [], nums[0], nums[0]
    for cur in nums[1:] + [None]:
        if cur is not None and cur[1] == prev[1] + 1:
            prev = cur
            continue
        a = f"{start[0]}{start[1]:0{start[2]}d}"
        b = f"{prev[0]}{prev[1]:0{prev[2]}d}"
        out.append(a if a == b else f"{a}-{b}")
        if cur is not None:
            start = prev = cur
    return ", ".join(out)


def yaml_template(fc: Mapping[str, Any], intent: Mapping[str, Any], meaning: Mapping[str, Any]) -> str:
    """The intent template prefilled with this song's characters and sections. Every user claim is written back
    (global fields, characters, line singers, palette, do_not, motifs, symbolism, references, notes and each
    section's own fields and do_not rules), so parsing the template gives the same claims as the file it came from
    (grammar: ``intent.py``; round trip: tests/unit/meaning/test_intent_grammar.py)."""
    L = ["```yaml", "# mvh-intent v1: copy this block into meaning/intent.md (with or without the markdown fence) and fill it in. Empty = no answer.",
         "# Times are in seconds of audio/mix.flac; keep t0/t1 so the notes follow the sections if they move.",
         "# Hex colours can be typed as they are ([#1b2a49, night blue]); a comment needs two spaces before its '#'.",
         f"logline: {_q(intent.get('logline'))}", f"summary: {_q(intent.get('summary'))}",
         "themes: [" + ", ".join(_q(t) for t in intent.get("themes") or []) + "]",
         f"setting: {_q(intent.get('setting'))}", f"tone: {_q(intent.get('tone'))}",
         f"perspective: {{narrator: {_q(intent['perspective'].get('narrator'))}, addressee: {_q(intent['perspective'].get('addressee'))}}}",
         "characters:   # one per person on screen; voices = which detected voice(s) they sing with; lead_backing = lead, backing or both"]
    chars = meaning.get("characters") or []
    if not chars:
        L.append('  C1: {name: "", description: "", voices: [], lead_backing: ""}   # lead_backing: lead, backing or both')
    for c in chars:
        ic = (intent.get("characters") or {}).get(c["id"]) or {}
        mapping = c.get("voice_mapping") or {}
        said = [v for v in c["voice_ids"] if mapping.get(v) == "user"]
        guess = [v for v in c["voice_ids"] if v not in said]
        note = f"   # the harness proposes voices: {', '.join(guess)}" if guess else ""
        L.append(f"  {c['id']}: {{name: {_q(ic.get('name'))}, "
                 f"description: {_q(ic.get('description'))}, voices: [{', '.join(said)}], "
                 f"lead_backing: {_q(ic.get('lead_backing'))}}}{note}")
    L.append("line_singers:   # optional per-line fixes, lead first: {L005: C1+C2}")
    for lid, cs in sorted((intent.get("line_singers") or {}).items()):
        L.append(f"  {lid}: {'+'.join(cs)}")
    pal = intent.get("palette_names") or intent.get("palette") or []
    L.append("palette: [" + ", ".join(_q(p) for p in pal) + "]   # hex (#1b2a49) or colour words (night blue)")
    L.append("do_not:   # rules in your own words; copied verbatim to every agent")
    global_dn = list(intent.get("do_not") or [])
    for r in global_dn:
        L.append(f"  - {_q(r)}")
    motifs = intent.get("motifs") or []
    if motifs:
        L.append("motifs:   # name, the lyric lines it appears on, a note")
        for m in motifs:
            L.append(f"  - {{name: {_q(m.get('name'))}, lines: [{', '.join(m.get('lines') or [])}], note: {_q(m.get('note'))}}}")
    else:
        L.append("motifs: []   # [{name: lanterns, lines: [L001, L009], note: \"\"}]")
    for key in ("symbolism", "references", "notes"):
        L.append(f"{key}: [" + ", ".join(_q(t) for t in intent.get(key) or []) + "]")
    L.append("sections:")
    for s in fc["sections"]:
        sm = next((x for x in meaning.get("sections") or [] if x["section_id"] == s["id"]), {})
        user = (sm.get("provenance") or {}).get("status") == "user"
        fs = sm.get("field_sources") or {}

        def val(f: str) -> str:
            return _q(sm.get(f) if user and fs.get(f) == "user" else None)
        t0, t1 = float(s["t"]), float(s["t"]) + float(s["d"])
        L.append(f"  {s['id']}:   # {s.get('occurrence_label')} {_mmss(t0)}-{_mmss(t1)}")
        L.append(f"    t0: {t0:.3f}")
        L.append(f"    t1: {t1:.3f}")
        L.append(f"    occurrence_label: {s.get('occurrence_label')}")
        L.append(f"    feel: {val('feel')}")
        L.append(f"    meaning: {val('meaning')}")
        L.append(f"    emotion: {_q(sm.get('emotion', {}).get('lyric') if fs.get('emotion.lyric') == 'user' else None)}")
        L.append(f"    movement: {val('movement_hint')}")
        L.append(f"    camera: {val('camera_hint')}")
        ph = sm.get("palette_hint") if fs.get("palette_hint") == "user" else []
        L.append(f"    palette: [{', '.join(_q(h) for h in ph or [])}]")
        cp = sm.get("characters_present") if fs.get("characters_present") == "user" else []
        L.append(f"    characters: [{', '.join(cp or [])}]")
        own_dn = [r for r in sm.get("do_not") or [] if r not in global_dn]  # the section's own rules (user only)
        L.append(f"    do_not: [{', '.join(_q(r) for r in own_dn)}]")
    L.append("```")
    return "\n".join(L)


def interview_md(fc: Mapping[str, Any], intent: Mapping[str, Any], meaning: Mapping[str, Any]) -> str:
    ident = fc["identity"] or {}
    title = ident.get("title") or "this song"
    artist = ident.get("artist")
    lines = fc["lines"]
    st = fc["stats"]
    out = [f"# Interview: {title}" + (f" - {artist}" if artist else ""), "",
           "The harness found the facts below. **You are the authority on what the song means**: answer in "
           "`meaning/intent.md` (free text is fine, or copy the template at the end). `mvh analyze` never edits "
           "that file. An agent may draft the gaps into `meaning/authored.json` only after you have seen these "
           "questions; your answers always win over its draft.", ""]
    status = meaning.get("status")
    out.append(f"Current meaning status: **{status}**" + (" (answers recognised in intent.md)" if status == "user" else "") + ".")
    out.append("")
    q = 1

    def ask(text: str) -> None:
        nonlocal q
        out.append(f"{q}. {text}")
        q += 1

    credits = ", ".join(f"{c.get('name')} ({c.get('role')})" for c in (ident.get("credits") or [])[:6] if isinstance(c, Mapping))
    ask("**What does this song mean to you?** One sentence (the logline), then as much as you like."
        + (f" Credits found: {credits}." if credits else ""))
    if fc["lyrics"] and fc["lyrics"].get("instrumental"):
        ask("The song is **instrumental** (no lyrics were found). What story or image should carry it?")
    elif not lines:
        ask("No lyrics were found. Are there words to show? (pass `--lyrics` with a .lrc/.txt file and re-run)")
    voices = fc["voices"]
    if voices:
        desc = []
        for v in voices:
            vid = str(v.get("id"))
            first = next((ln for ln in lines if any(it == vid for it in _voices_of_line(fc, ln["id"]))), None)
            secs = sorted({ln.get("section_id") for ln in lines if vid in _voices_of_line(fc, ln["id"]) and ln.get("section_id")})
            desc.append(f"   - **{vid}**: {float(v.get('seconds') or 0):.1f} s, {v.get('n_lines', 0)} lines"
                        + (f", first heard at {_mmss(float(first['t']))} ({first['id']})" if first else "")
                        + (f", sections {', '.join(secs[:8])}" if secs else "")
                        + (f"; the lyrics label it '{v.get('hint')}'" if v.get("hint") else "")
                        + (f"; now mapped to {_char_name(fc, vid)}" if _char_name(fc, vid) else ""))
        ask(f"**Who sings to whom?** {len(voices)} voice(s) were found (play each in the viewer's Lyrics & singers lane):")
        out.extend(desc)
        out.append("   Which character is each voice? Is any voice a narrator or announcer (rap battles often open with one)?")
    elif lines:
        ask("No separate voices were detected. Is it one singer throughout? If not, who sings which lines?")
    if st.get("review"):
        rv = [ln["id"] for ln in lines if _line_review(fc, ln["id"])]
        ask(f"**Check the singer** of {len(rv)} low-confidence line(s): {', '.join(rv[:20])}{' ...' if len(rv) > 20 else ''}. "
            "Fix them in the viewer or under `line_singers`.")
    hooks = {}
    for ln in lines:
        if ln.get("repeat_group"):
            hooks.setdefault(ln["repeat_group"], []).append(ln)
    if hooks:
        top = sorted(hooks.items(), key=lambda kv: -len(kv[1]))[:3]
        parts = [f"{g} ({len(v)}x: {', '.join(x['id'] for x in v[:6])}, {_quote(v[0].get('text'), 6) if fc.get('lyrics_to_agents', True) else 'text in lines.tsv'})" for g, v in top]
        ask("**The hooks** repeat: " + "; ".join(parts) + ". What do they mean to you? Should they look the same each time?")
    ask("**The world**: where and when does the video take place? Who are the characters (look, age, costume)? Any visual references (films, artists, photos)?")
    arc = []
    for s in fc["sections"]:
        m = fc["mood"].get(s["id"])
        w = audio_word(m)
        if w:
            arc.append(f"{s['id']} {s.get('occurrence_label')}: {w}")
    if arc:
        ask("**The mood arc** the audio models hear (arousal is more reliable than valence): " + "; ".join(arc[:12])
            + ("; ..." if len(arc) > 12 else "") + ". Does this match the feeling you want? Where should it differ?")
    roles = [f"{r.get('role')} {r.get('id')} at {_mmss(float(r['t']))} ({r.get('section_id')})" for r in fc["roles"]]
    tier1 = [c for c in fc["cues"] if c.get("tier") == 1]
    ask("**How should each section feel and move?** Sections: "
        + ", ".join(f"{s['id']} {s.get('occurrence_label')} {_mmss(float(s['t']))}" for s in fc["sections"][:24])
        + (" ..." if len(fc["sections"]) > 24 else "")
        + (". EDM roles: " + ", ".join(roles) if roles else "")
        + (f". {len(tier1)} tier-1 cues (section starts, drops, builds) are in events/cues.json" if tier1 else "")
        + ". For each: feel, what it means, movement/choreography, camera.")
    mom = sorted(fc["moments"], key=lambda m: m.get("rank", 99))[:5]
    if mom:
        ask("**The top moments**: " + "; ".join(f"#{m.get('rank')} {_mmss(float(m['t']))} {m.get('kind')} ({m.get('cue_id')})" for m in mom)
            + ". What should happen on screen at each?")
    ask("**Colours**: which palette belongs to the song (hex codes or words like 'night blue')? Per-section colours?")
    ask("**Never show**: what must never appear on screen? (copied verbatim to every agent)")
    if intent.get("present"):
        got = [k for k in ("logline", "summary", "setting", "tone", "themes", "palette", "do_not", "motifs") if intent.get(k)]
        out.append("")
        out.append(f"Already answered in intent.md: {', '.join(got) or 'nothing recognised yet'}; "
                   f"{len(intent.get('characters') or {})} character(s), {len(intent.get('sections') or [])} section note(s), "
                   f"{len(intent.get('line_singers') or {})} line singer fix(es).")
    oq = [x for x in meaning.get("open_questions") or [] if not x.startswith("The meaning is pending")]
    if oq:
        out += ["", "## Open questions", ""] + [f"- {x}" for x in oq[:15]]
    out += ["", "## Template (copy into meaning/intent.md)", "", yaml_template(fc, intent, meaning), ""]
    return "\n".join(out)


def _voices_of_line(fc: Mapping[str, Any], lid: str) -> list[str]:
    return [str(s.get("voice_id")) for s in fc["spans"] if s.get("line_id") == lid]


def _line_review(fc: Mapping[str, Any], lid: str) -> bool:
    sp = [s for s in fc["spans"] if s.get("line_id") == lid]
    return (not sp and len(fc["voices"]) > 1) or any(s.get("review") for s in sp)


def _char_name(fc: Mapping[str, Any], vid: str) -> str | None:
    for c in fc["chars"]:
        if vid in c["voice_ids"]:
            return f"{c['id']} ({c['name']}, {c['provenance']['status']})"
    return None


def request_md(fc: Mapping[str, Any], meaning: Mapping[str, Any], gaps: list[str], draft_mode: str,
               lyrics_to_agents: bool) -> str:
    title = (fc["identity"] or {}).get("title") or "this song"
    out = [f"# Meaning draft request: {title}", ""]
    if draft_mode == "off":
        out += ["Drafting is turned off for this song (`--param meaning.draft=\"off\"`). Do not write meaning/authored.json.", ""]
    out += [
        "You are drafting **only the gaps** the user left in `meaning/intent.md`. The user is the authority; your draft is a",
        "labelled suggestion that never overwrites them.", "",
        "**Before drafting** (SKILL.md rule): if the meaning status is `pending` and `meaning/intent.md` is empty, show the user",
        "the questions in `meaning/interview.md` and wait for their answers. Draft only after that (or when they ask you to).", "",
        "## Read", "",
        "- `meaning/input.json`: the facts you may cite (sections, voices, characters, moods, hooks, cues, moments, and `facts.gaps`).",
        "- `meaning/intent.md`: the user's answers (never contradict them; conflicts become `open_questions`).",
    ]
    if lyrics_to_agents:
        out.append("- `lyrics/lines.tsv`: the lyric lines (id, time, section, singer, text). Quote at most 10 words per citation.")
    else:
        out.append("- Lyrics are **not** available to agents for this song (`--no-lyrics-to-agents`): work from the facts only.")
    out += ["", "## Write `meaning/authored.json`", "",
            "- Valid against `meaning/schema.json`, with `\"status\": \"draft\"`.",
            "- Every claim is typed: `source` is `lyric`, `audio`, `external` or `speculative` (never `user`), and cites ids",
            "  (`S03`, `L012`, `Q0034`, `V2`, `C1`) and/or time ranges (`t0`, `t1` in seconds); `quote` <= 10 words.",
            "- Per-section entries keep `section_id`, `t0`, `t1` and `occurrence_label` exactly as in input.json, so they can be",
            "  re-anchored if the sections move.",
            "- Keep the character ids and voice mapping of input.json (`facts.characters`); add a character only for a voice",
            "  that has none. Do not write `do_not` rules for the user; suggest them in `open_questions`.",
            "- Then run `mvh meaning <song folder>` (or `mvh analyze <song folder> --only meaning,brief`): the draft is merged,",
            "  checked (ids, times, quote length) and `brief.md` is refreshed.", ""]
    st = meaning.get("status")
    out += [f"## Gaps to fill (meaning status: {st})", ""]
    out += [f"- {g}" for g in gaps[:60]] or ["- none: the user answered everything"]
    if len(gaps) > 60:
        out.append(f"- ... {len(gaps) - 60} more in input.json facts.gaps")
    out.append("")
    return "\n".join(out)


def meaning_md(identity: Mapping[str, Any], meaning: Mapping[str, Any], orphans: list[dict[str, Any]]) -> str:
    title = (identity or {}).get("title") or "this song"
    st = meaning["status"]
    out = [f"# Meaning: {title}", "",
           f"Status: **{st}**" + {"user": " (the user's intent; draft and audio facts fill gaps)",
                                  "draft": " (an agent/LLM draft: not confirmed by the user)",
                                  "pending": " (nothing authored yet: see meaning/interview.md)"}[st], ""]
    if meaning.get("logline"):
        out += [f"**Logline**: {meaning['logline']}", ""]
    if meaning.get("summary") and meaning.get("summary") != meaning.get("logline"):
        out += [meaning["summary"], ""]
    for k, lab in (("setting", "Setting"), ("tone", "Tone")):
        if meaning.get(k):
            out.append(f"**{lab}**: {meaning[k]}")
    p = meaning.get("perspective") or {}
    fs = meaning.get("field_sources") or {}
    if any(p.values()):
        def who(k: str) -> str:
            return (p.get(k) or "?") + (" (draft)" if p.get(k) and fs.get(f"perspective.{k}") == "draft" else "")
        out.append(f"**Perspective**: narrator {who('narrator')}, addressee {who('addressee')}")
    if meaning.get("themes"):
        out.append("**Themes**: " + "; ".join(f"{t['text']} ({t['source']}, {t.get('status')})" for t in meaning["themes"]))
    out.append("")
    out += ["## Characters", ""]
    for c in sorted(meaning.get("characters") or [], key=lambda c: char_num(c["id"])):
        pv = c["provenance"]
        out.append(f"- **{c['id']} {c['name']}** (voices {', '.join(c['voice_ids']) or '-'}; {c.get('lead_backing') or '?'}; "
                   f"{len(c['line_ids'])} lines; {pv['status']}/{pv['source']}"
                   + ("; draft " + " + ".join(k for k, v in (c.get("field_sources") or {}).items() if v == "draft")
                      if pv["status"] == "user" and "draft" in (c.get("field_sources") or {}).values() else "")
                   + ")" + (f": {c['description']}" if c.get("description") else ""))
    if not meaning.get("characters"):
        out.append("- none (no lyrics or voices)")
    out += ["", "## Sections", ""]
    for s in meaning.get("sections") or []:
        bits = []
        for k, lab in (("feel", "feel"), ("meaning", "meaning"), ("movement_hint", "movement"), ("camera_hint", "camera")):
            if s.get(k):
                bits.append(f"{lab}: {s[k]}")
        e = s.get("emotion") or {}
        if e.get("lyric") or e.get("audio"):
            bits.append(f"emotion: {e.get('lyric') or '?'} / audio {e.get('audio') or '?'}"
                        + ("" if e.get("agree") is None else (" (agree)" if e["agree"] else " (differ)")))
        if s.get("palette_hint"):
            bits.append("palette " + " ".join(s["palette_hint"]))
        if s.get("characters_present"):
            bits.append("characters " + ", ".join(s["characters_present"]))
        out.append(f"- **{s['section_id']}** ({s['occurrence_label']}, {s['t0']:.1f}-{s['t1']:.1f} s; "
                   f"{s['provenance']['status']}): " + ("; ".join(bits) or "-"))
    if meaning.get("palette"):
        names = meaning.get("palette_names") or []
        out += ["", "## Palette", "", " ".join(meaning["palette"]) + (f" ({', '.join(names)})" if names else "")]
    if meaning.get("motifs"):
        out += ["", "## Motifs", ""] + [f"- {m['id']} {m['name']}: {len(m.get('occurrences') or [])} occurrence(s)" for m in meaning["motifs"]]
    if meaning.get("references"):
        out += ["", "## References (user)", ""] + [f"- {r}" for r in meaning["references"]]
    if meaning.get("notes"):
        out += ["", "## Notes (user)", ""] + [f"- {r}" for r in meaning["notes"][:30]]
    out += ["", "## Never show", ""] + ([f"- {r}" for r in meaning.get("do_not") or []] or ["- (no rules yet)"])
    if orphans:
        out += ["", f"## Orphaned claims ({len(orphans)})", "", "Claims whose section no longer exists (meaning/orphans.json):"]
        out += [f"- {o['old_section_id']} {o['t_range'][0]:.1f}-{o['t_range'][1]:.1f} s: {o['reason']}" for o in orphans[:20]]
    if meaning.get("open_questions"):
        out += ["", "## Open questions", ""] + [f"- {q}" for q in meaning["open_questions"][:20]]
    out.append("")
    return "\n".join(out)
