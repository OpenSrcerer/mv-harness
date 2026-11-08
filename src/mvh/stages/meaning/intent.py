# ruff: noqa: E501
"""Parse ``meaning/intent.md`` (the user's answers) into claims. The file is an INPUT: never written here.

Two accepted forms (both may appear in one file; the YAML block wins field by field):

1. **The YAML template** from ``meaning/interview.md``: a fenced block opened with ```` ```yaml ```` (or
   ```` ```mvh-intent ````) containing the keys of ``TEMPLATE_KEYS``. Per-section entries are keyed by section
   id and carry ``t0``/``t1``/``occurrence_label`` so ``mvh meaning`` can re-anchor them when sections move.
2. **Free text** (markdown). Recognised without any template:
   * ``## Characters`` style lines: ``C1 The Lamplighter = voice V1 (the low voice). Lead.``
   * per-line singers anywhere: ``L005: C1+C2`` (the viewer writes these under ``## Singers``)
   * ``## Never show`` / ``Do not`` headings: every bullet, verbatim (the user's words)
   * ``Palette: night blue, #f2a541, rust red``
   * section notes: ``Intro: slow drift ...``, ``S03: ...``, ``chorus#2: ...``, ``Drop: ...`` (several per line OK)
   * ``## The story`` / ``## Meaning``: summary (first sentence = logline); ``## Setting``, ``## Tone``.

The result is a plain dict (see ``empty_intent``); ``n_characters`` is what the voices stage may use as the
voice count (PLAN §5 voices). Stdlib + PyYAML (safe_load only).
"""
from __future__ import annotations

import re
from typing import Any

from .colors import parse_palette

__all__ = ["parse_intent", "empty_intent", "SECTION_WORDS", "TEMPLATE_KEYS", "split_singers"]

TEMPLATE_KEYS = ("logline", "summary", "themes", "setting", "tone", "perspective", "characters", "line_singers",
                 "palette", "do_not", "motifs", "symbolism", "sections", "references", "notes")
#: words that address sections by label or EDM role
SECTION_WORDS = ("intro", "verse", "pre-chorus", "prechorus", "chorus", "post-chorus", "hook", "bridge", "inst",
                 "instrumental", "solo", "break", "breakdown", "build", "buildup", "build-up", "drop", "outro",
                 "interlude", "refrain", "silence")
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1, "final": -1}

_FENCE = re.compile(r"```[ \t]*(yaml|yml|mvh-intent)[^\n]*\n(.*?)```", re.S | re.I)
_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CHAR = re.compile(r"^\s*(?:[-*+]\s+)?\**(C[1-9]\d*)\**\b\s*[:.\-–—]?\s*(.*)$")
_VOICE = re.compile(r"\bV([1-9]\d*)\b")
_LINE_SINGER = re.compile(r"\b(L\d{3,})\b\s*(?:[:=]|->|→)\s*(C[1-9]\d*(?:\s*[+&,/]\s*C[1-9]\d*)*)")
_SEC_ID = r"S\d{2,}"
_WORDS_ALT = "|".join(sorted((re.escape(w) for w in SECTION_WORDS), key=len, reverse=True))
_SEC_KEY = re.compile(
    rf"(?:(?<=^)|(?<=[.;!?]\s)|(?<=[.;!?]\s\s))\s*\**((?:(?:first|second|third|fourth|fifth|last|final)\s+)?"
    rf"(?:{_SEC_ID}|(?:{_WORDS_ALT})(?:#\d+|\s+\d+)?)s?)\**\s*:\s*",
    re.I,
)
_SENT = re.compile(r"(.+?[.!?])(\s|$)", re.S)


def empty_intent() -> dict[str, Any]:
    return {
        "present": False, "form": "none", "logline": None, "summary": None, "setting": None, "tone": None,
        "themes": [], "symbolism": [], "perspective": {"narrator": None, "addressee": None},
        "characters": {}, "line_singers": {}, "palette": [], "palette_names": [], "palette_unparsed": [],
        "do_not": [], "motifs": [], "sections": [], "references": [], "notes": [], "warnings": [],
        "n_characters": None,
    }


def split_singers(s: str) -> list[str]:
    """'C1+C2' / 'C1 & C2' / 'C1, C2' -> ['C1', 'C2'] (order kept, duplicates dropped)."""
    out: list[str] = []
    for c in re.findall(r"C[1-9]\d*", str(s)):
        if c not in out:
            out.append(c)
    return out


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _strs(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[,\n]", v) if s.strip()]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    return [str(v).strip()] if str(v).strip() else []


def _lead_word(text: str) -> str | None:
    t = text.lower()
    has_lead = bool(re.search(r"\blead\b", t))
    has_back = bool(re.search(r"\b(backing|harmony|harmonies|harmonises|harmonizes|backup|choir)\b", t))
    if has_lead and has_back:
        return "both"
    if has_lead:
        return "lead"
    if has_back:
        return "backing"
    return None


# ============================================================================================ YAML
def _parse_yaml(block: str, out: dict[str, Any]) -> None:
    import yaml

    try:
        d = yaml.safe_load(block)
    except yaml.YAMLError as e:
        out["warnings"].append(f"intent.md: the YAML block does not parse ({type(e).__name__}); free text used")
        return
    if not isinstance(d, dict):
        return
    out["form"] = "yaml" if out["form"] == "none" else "yaml+text"
    unknown = [str(k) for k in d if str(k) not in TEMPLATE_KEYS]
    if unknown:
        out["warnings"].append("intent.md: unknown top-level key(s) in the YAML block ignored: " + ", ".join(unknown[:6]))
    for k in ("logline", "summary", "setting", "tone"):
        if _clean(d.get(k)):
            out[k] = _clean(d.get(k))
    for k in ("themes", "symbolism", "references", "notes"):
        vals = _strs(d.get(k))
        if vals:
            out[k] = vals
    p = d.get("perspective")
    if isinstance(p, dict):
        for k in ("narrator", "addressee"):
            if _clean(p.get(k)):
                out["perspective"][k] = _clean(p.get(k))
    chars = d.get("characters")
    if isinstance(chars, dict):
        for cid, c in chars.items():
            cid = str(cid).strip()
            if not re.fullmatch(r"C[1-9]\d*", cid):
                out["warnings"].append("intent.md: character keys must look like C1, C2 (one key ignored)")
                continue
            c = c if isinstance(c, dict) else {"name": c}
            voices = [f"V{m}" for m in _VOICE.findall(" ".join(_strs(c.get("voices") or c.get("voice"))))]
            lb = _clean(c.get("lead_backing"))
            if not (_clean(c.get("name")) or _clean(c.get("description")) or voices or lb):
                continue  # an untouched template entry is not an answer
            out["characters"][cid] = {
                "name": _clean(c.get("name")), "description": _clean(c.get("description")),
                "voices": voices, "lead_backing": lb if lb in ("lead", "backing", "both") else None,
            }
    ls = d.get("line_singers")
    if isinstance(ls, dict):
        for lid, s in ls.items():
            cs = split_singers(str(s))
            if re.fullmatch(r"L\d{3,}", str(lid).strip()) and cs:
                out["line_singers"][str(lid).strip()] = cs
    pal = _strs(d.get("palette"))
    if pal:
        hexes, names, bad = parse_palette(pal)
        out["palette"], out["palette_names"], out["palette_unparsed"] = hexes, names, bad
    dn = _strs(d.get("do_not")) if not isinstance(d.get("do_not"), str) else [d["do_not"].strip()]
    if dn:
        out["do_not"] = dn
    motifs = d.get("motifs")
    if isinstance(motifs, list):
        for m in motifs:
            if isinstance(m, dict) and _clean(m.get("name")):
                out["motifs"].append({"name": _clean(m.get("name")), "lines": re.findall(r"L\d{3,}", " ".join(_strs(m.get("lines")))),
                                      "note": _clean(m.get("note"))})
            elif isinstance(m, str) and m.strip():
                out["motifs"].append({"name": m.strip(), "lines": re.findall(r"L\d{3,}", m), "note": None})
    secs = d.get("sections")
    if isinstance(secs, dict):
        for key, s in secs.items():
            s = s if isinstance(s, dict) else {"feel": s}
            claim = _section_claim(str(key).strip(), s)
            if claim is not None:
                out["sections"].append(claim)


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _section_claim(key: str, s: dict[str, Any], origin: str = "yaml") -> dict[str, Any] | None:
    fields = {
        "feel": _clean(s.get("feel")), "meaning": _clean(s.get("meaning")), "emotion": _clean(s.get("emotion")),
        "movement": _clean(s.get("movement") or s.get("movement_hint")),
        "camera": _clean(s.get("camera") or s.get("camera_hint")),
    }
    pal_in = _strs(s.get("palette") or s.get("palette_hint"))
    hexes, _names, bad = parse_palette(pal_in) if pal_in else ([], [], [])
    chars = split_singers(" ".join(_strs(s.get("characters") or s.get("characters_present"))))
    dn = _strs(s.get("do_not")) if not isinstance(s.get("do_not"), str) else [s["do_not"].strip()]
    if not any(fields.values()) and not hexes and not chars and not dn:
        return None
    return {"key": key, "t0": _num(s.get("t0")), "t1": _num(s.get("t1")),
            "occurrence_label": _clean(s.get("occurrence_label")), **fields, "palette": hexes,
            "palette_unparsed": bad, "characters": chars, "do_not": dn, "origin": origin}


# ============================================================================================ free text
_DO_NOT_HEAD = re.compile(r"\b(never|do not|do-nots?|don'?ts?|avoid|must not|no-?gos?|forbidden|not show)(?![\w'])")
#: a line that IS a do-not label ('**Never show**', 'Never show: text', 'Avoid:'), with optional inline text
_DO_NOT_LABEL = re.compile(
    r"^\s*\**\s*(never show|never|do not show|do not|do-nots?|don'?ts?|avoid|must not|no-?gos?)\s*\**\s*(?::\s*\**\s*(.*?)|)\s*\**\s*$",
    re.I)


def _blocks(text: str) -> list[tuple[str, list[str]]]:
    """[(heading lower-case, lines)] with '' for text before the first heading; fenced blocks removed."""
    text = _FENCE.sub("", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out: list[tuple[str, list[str]]] = [("", [])]
    cur = out[0]
    dn: tuple[str, list[str]] | None = None  # an open do-not block started by a label line
    for ln in text.splitlines():
        m = _HEAD.match(ln)
        if m:
            dn = None
            out.append((m.group(2).strip().lower(), []))
            cur = out[-1]
            continue
        lm = _DO_NOT_LABEL.match(ln) if not _BULLET.match(ln) else None
        if lm:
            dn = ("never show", [])
            out.append(dn)
            if lm.group(2):
                dn[1].append("- " + lm.group(2).strip())
            continue
        if dn is not None:
            if not ln.strip() or _BULLET.match(ln) or ln.startswith((" ", "\t")):
                dn[1].append(ln.rstrip())
                continue
            dn = None
        cur[1].append(ln.rstrip())
    return out


def _first_sentence(s: str) -> str:
    m = _SENT.match(s.strip())
    first = (m.group(1) if m else s).strip()
    return first[:240]


def _bullets(lines: list[str]) -> list[str]:
    out = []
    for ln in lines:
        if _BULLET.match(ln):
            out.append(_BULLET.sub("", ln).strip())
        elif out and ln.startswith(("  ", "\t")) and ln.strip():
            out[-1] += " " + ln.strip()  # continuation of a bullet
    return [b for b in out if b]


def _paragraph(lines: list[str]) -> str:
    return " ".join(ln.strip() for ln in lines if ln.strip() and not _BULLET.match(ln)).strip()


def _parse_text(text: str, out: dict[str, Any]) -> None:
    blocks = _blocks(text)
    if not any(ln.strip() for _h, lines in blocks for ln in lines):
        return
    if out["form"] == "none":
        out["form"] = "text"
    elif out["form"] == "yaml":
        out["form"] = "yaml+text"
    fill = {}
    for head, lines in blocks:
        body = "\n".join(lines).strip()
        if not body:
            continue
        h = head
        if _DO_NOT_HEAD.search(h):
            dn = _bullets(lines) or [ln.strip() for ln in lines if ln.strip()]
            fill.setdefault("do_not", []).extend(dn)
            continue
        if re.search(r"\b(story|meaning|about|means|summary|logline|what)\b", h):
            para = _paragraph(lines)
            if para:
                fill.setdefault("summary", para)
                fill.setdefault("logline", _first_sentence(para))
            continue
        if re.search(r"\b(setting|world|place|where)\b", h):
            fill.setdefault("setting", _paragraph(lines) or "; ".join(_bullets(lines)))
            continue
        if re.search(r"\b(tone)\b", h):
            fill.setdefault("tone", _paragraph(lines) or "; ".join(_bullets(lines)))
            continue
        if re.search(r"\b(theme|themes)\b", h):
            fill.setdefault("themes", _bullets(lines) or [_paragraph(lines)])
            continue
        if re.search(r"\b(symbol|symbolism)\b", h):
            fill.setdefault("symbolism", _bullets(lines) or [_paragraph(lines)])
            continue
        if re.search(r"\b(reference|references|inspiration)\b", h):
            fill.setdefault("references", _bullets(lines) or [_paragraph(lines)])
            continue
        if h == "" and not re.search(r"(^|\n)\s*(?:[-*+]\s+)?(C[1-9]\d*|L\d{3,}|palette|colou?rs?)\b", body, re.I):
            para = _paragraph(lines)
            if para and len([b for b in blocks if not _DO_NOT_HEAD.search(b[0])]) == 1:  # a file with no headings at all: the whole text is the summary
                fill.setdefault("summary", para[:2000])
                fill.setdefault("logline", _first_sentence(para))
    for k in ("summary", "logline", "setting", "tone"):
        if fill.get(k) and not out.get(k):
            out[k] = fill[k]
    for k in ("themes", "symbolism", "references"):
        if fill.get(k) and not out.get(k):
            out[k] = [x for x in fill[k] if x]
    for x in fill.get("do_not") or []:
        if x and x not in out["do_not"]:
            out["do_not"].append(x)
    # ---- lines anywhere in the file
    raw_lines: list[str] = []
    for head, lines in blocks:
        if _DO_NOT_HEAD.search(head):
            continue  # the user's prohibitions are rules, never section feels or characters
        raw_lines.extend(lines)
    for raw in raw_lines:
        ln = raw.strip()
        if not ln or _HEAD.match(raw):
            continue
        for m in _LINE_SINGER.finditer(ln):
            out["line_singers"].setdefault(m.group(1), split_singers(m.group(2)))
        mc = _CHAR.match(raw)
        if mc and not _LINE_SINGER.search(ln):
            cid, rest = mc.group(1), mc.group(2).strip()
            if rest.startswith("{"):
                continue  # a template flow map that did not parse as YAML, not a description
            if cid not in out["characters"]:
                out["characters"][cid] = _char_from_text(rest)
            continue
        body = _BULLET.sub("", ln)
        mp = re.match(r"^\**(palette|colou?rs?)\**\s*[:\-]\s*(.+)$", body, re.I)
        if mp and not out["palette"] and not out["palette_unparsed"]:
            items = re.split(r"[,;]|\s+and\s+", mp.group(2))
            hexes, names, bad = parse_palette(items)
            out["palette"], out["palette_names"], out["palette_unparsed"] = hexes, names, bad
            continue
        for claim in _section_notes(body):
            out["sections"].append(claim)


_KEY_LINE = re.compile(r"^(?:" + "|".join(TEMPLATE_KEYS) + r")\s*:", re.M)
_TKEY = re.compile(r"^(" + "|".join(TEMPLATE_KEYS) + r")\s*:(.*)$")
_ANYKEY = re.compile(r"^[A-Za-z_][\w \-]*?\s*:(?:\s|$)")
_MARKER = re.compile(r"^\s*#\s*mvh-intent\b", re.I)


def _template_region(text: str) -> tuple[str, str] | None:
    """Find the interview's YAML template inside an unfenced file -> (template text, the rest of the file).

    The region starts at the ``# mvh-intent`` marker or, without it, at the first template key line, and runs over the
    YAML-shaped lines that follow (indented lines, template keys, ``- `` items, comments); the first prose line, markdown
    heading or non-template ``key:`` line ends it. Without the marker the region counts as the template only when it
    has two distinct template keys, the file has no other ``key:`` line, and no plain value would lose text to a ``#``
    comment (free-text answers like ``palette: night blue, #f2a541`` stay free text)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if _MARKER.match(ln)), None)
    marker = start is not None
    if start is None:
        start = next((i for i, ln in enumerate(lines) if _TKEY.match(ln)), None)
    if start is None:
        return None
    keys: set[str] = set()
    last = start
    i = start
    while i < len(lines):
        ln = lines[i]
        t = ln.strip()
        m = _TKEY.match(ln)
        if m:
            keys.add(m.group(1))
            last = i
        elif not t:
            pass
        elif ln[0] in " \t":
            last = i
        elif t.startswith("#") and not t.startswith("##"):
            pass  # a comment of the template (or a one-hash heading): counted only when followed by more template
        elif t.startswith("- ") or t == "-" or t[0] in "]}":
            last = i
        else:
            break
        i += 1
    if not marker:
        if len(keys) < 2:
            return None
        for j, ln in enumerate(lines):
            if (j < start or j > last) and _ANYKEY.match(ln) and not _TKEY.match(ln):
                return None
        for j in range(start, last + 1):
            m = _TKEY.match(lines[j])
            v = m.group(2).strip() if m else ""
            if v and v[0] not in "\"'[{|>#" and " #" in v:
                return None
    body = "\n".join(lines[start:last + 1])
    rest = "\n".join(lines[:start] + lines[last + 1:])
    rest = re.sub(r"(?m)^\s*```[\w-]*\s*$", "", rest)
    return body, rest


def _char_from_text(rest: str) -> dict[str, Any]:
    voices = [f"V{v}" for v in _VOICE.findall(rest)]
    name_part = re.split(r"\s*(?:=|\(|:|\bis\b|\bvoice\b|–|—|\s-\s)\s*", rest, maxsplit=1)[0].strip(" *.,")
    desc = rest[len(name_part):] if name_part and rest.startswith(name_part) else rest
    desc = re.sub(r"(?:=|\bis\b)?\s*(?:the\s+)?(?:voice\s*)?\bV[1-9]\d*\b", "", desc, flags=re.I)
    desc = re.sub(r"[()]", "", desc)
    desc = re.sub(r"\s+([.,;])", r"\1", re.sub(r"\s+", " ", desc)).strip(" .,;:=-")
    return {"name": name_part or None, "description": desc or None, "voices": voices,
            "lead_backing": _lead_word(rest)}


def _section_notes(body: str) -> list[dict[str, Any]]:
    """'Intro: slow drift. Verse: call and response' -> two claims (feel)."""
    ms = list(_SEC_KEY.finditer(body))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        txt = body[m.end():end].strip().rstrip(".").strip()
        if not txt or txt.startswith("#"):
            continue  # empty, or a YAML comment of the template
        key = re.sub(r"\s+", " ", m.group(1).strip().lower())
        key = re.sub(r"^(s\d{2,})$", lambda mm: mm.group(1).upper(), key)
        out.append({"key": key, "t0": None, "t1": None, "occurrence_label": None, "feel": txt, "meaning": None,
                    "emotion": None, "movement": None, "camera": None, "palette": [], "palette_unparsed": [],
                    "characters": [], "do_not": [], "origin": "text"})
    return out


# ============================================================================================ entry
def parse_intent(text: str | None) -> dict[str, Any]:
    out = empty_intent()
    if text is None:
        return out
    if text.startswith("﻿"):
        text = text[1:]
    out["present"] = bool(text.strip())
    if not out["present"]:
        return out
    vb = _VB_RE.search(text)
    if vb:
        text = _VB_RE.sub("\n", text)
    for m in _FENCE.finditer(text):
        _parse_yaml(m.group(2), out)
    free_text = text
    if out["form"] == "none":
        reg = _template_region(text)
        if reg is not None:
            before = {k: (list(v) if isinstance(v, list) else v) for k, v in out.items()}
            _parse_yaml(reg[0], out)
            if out["form"] == "yaml":
                free_text = reg[1]  # only what is around the template is free text
            else:
                warns = out["warnings"]
                out.update(before)
                out["warnings"] = warns
    if out["form"] == "none" and len(_KEY_LINE.findall(_FENCE.sub("", text))) >= 2:
        out["warnings"].append("intent.md has 'key:' lines that look like the YAML template but did not parse as YAML; "
                               "they were read as free text (check the indentation, or put the block in a ```yaml fence)")
    _parse_text(free_text, out)
    if vb:
        _parse_viewer_block(vb.group(1), out)
    out["n_characters"] = len(out["characters"]) or None
    return out


# ============================================================================================ viewer block (M6a)
_VB_RE = re.compile(r"<!-- mvh-viewer:begin v\d+ -->(.*?)<!-- mvh-viewer:end -->\n?", re.S)
_VB_VOICE = re.compile(r"^- (V[1-9]\d*) = (C[1-9]\d*)(?: (.*))?$")
_VB_SEC = re.compile(r"^### (S\d{2,})(?: (\S.*?))? (-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?) s$")
_VB_KV = re.compile(r"^- (feel|meaning|movement|camera|palette|do not): ?(.*)$")


def _parse_viewer_block(body: str, out: dict[str, Any]) -> None:
    """The block ``mvh view`` maintains in intent.md (grammar: mvh.stages.viewer.intent_block, M6a): the user's own
    words edited in the viewer. It wins over the YAML template and the free text (it is the latest edit)."""
    claims: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for raw in body.splitlines():
        line = raw.rstrip()
        vm = _VB_VOICE.match(line)
        if vm:
            v, cid, name = vm.group(1), vm.group(2), (vm.group(3) or "").strip()
            for c in out["characters"].values():  # a voice has one character: the viewer's mapping wins
                if v in c["voices"]:
                    c["voices"].remove(v)
            c = out["characters"].setdefault(cid, {"name": None, "description": None, "voices": [], "lead_backing": None})
            if v not in c["voices"]:
                c["voices"].append(v)
            if name and name != cid:
                c["name"] = name
            continue
        sm = _VB_SEC.match(line)
        if sm:
            cur = {"key": sm.group(1), "t0": float(sm.group(3)), "t1": float(sm.group(4)),
                   "occurrence_label": sm.group(2) or None, "feel": None, "meaning": None, "emotion": None,
                   "movement": None, "camera": None, "palette": [], "palette_unparsed": [], "characters": [],
                   "do_not": [], "origin": "viewer"}
            claims.append(cur)
            continue
        km = _VB_KV.match(line)
        if km and cur is not None:
            k, v = km.group(1), km.group(2).strip()
            if not v:
                continue
            if k == "do not":
                cur["do_not"].append(v)
            elif k == "palette":
                hexes, _names, bad = parse_palette(re.split(r"[,\s]+", v))
                cur["palette"], cur["palette_unparsed"] = hexes, bad
            else:
                cur[k] = v
    keep = [c for c in claims if any(c[k] for k in ("feel", "meaning", "movement", "camera", "palette", "do_not"))]
    out["sections"] = keep + out["sections"]  # first = preferred among equally specific claims
    if body.strip():
        out["form"] = "viewer" if out["form"] == "none" else out["form"] + "+viewer"
