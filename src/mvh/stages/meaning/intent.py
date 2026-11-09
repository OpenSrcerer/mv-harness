"""Read ``meaning/intent.md`` (the user's answers) into claims. The file is an INPUT: never written here.

THE INTENT GRAMMAR, mvh-intent v2 (user decision UD1, CONTRACT D78). intent.md is read in exactly two ways, plus the
viewer's machine-written block:

1. **The interview template** is the ONLY source of structured fields (logline, summary, themes, setting, tone,
   perspective, characters, voice mapping, line singers, palette, motifs, symbolism, references, per-section
   feel / meaning / emotion / movement / camera / palette / characters) and of do-not rules, the only hard
   constraints. Anything that must be obeyed goes in the template.
2. **Free text** (everything outside the template and the viewer block) is the user's prose. It is passed to every
   agent verbatim as ``notes`` (user-authored) and is NEVER parsed into fields or rules: a ``## Never show`` heading,
   a ``**Story:**`` label or a ``Chorus: wide`` line in free text is a note, not a do-not rule, a summary or a feel.
3. **The viewer block** ``<!-- mvh-viewer:begin v1 --> ... <!-- mvh-viewer:end -->`` (M6a grammar,
   ``mvh.stages.viewer.intent_block``): ``- V1 = C1 Name`` voice mappings and ``### S02 verse#1 9.000-17.000 s``
   section bullets. It is machine-written and the latest edit, so it wins over the template.

Other HTML comments (``<!-- ... -->``) are ignored.

TEMPLATE REGIONS. A region is
  * fenced: a block opened by ```` ```yaml ````, ```` ```yml ```` or ```` ```mvh-intent ```` up to its closing fence.
    When the closing fence is missing, the region runs over the template-shaped lines (below) after the opening one;
  * or unfenced: it starts at a ``# mvh-intent`` marker line or at a column-0 template key line in lower case
    (``logline:``, ``characters:``, ... ``TEMPLATE_KEYS``), together with the ``#`` comment lines directly above it.
    It runs over the template-shaped lines that follow: blank lines, indented lines, column-0 template key lines,
    column-0 ``- `` items under a key with no value (blank lines between them are fine, as in YAML), and ``#``
    comment lines followed by more template.
    The first other line ends it (prose, a markdown ``##`` heading, a capitalised ``Tone: ...`` line): that line is
    free text. ``Palette: ...`` (capitalised) is therefore a note, ``palette: ...`` the template key.
  Several regions may appear; the first one that answers a single-valued field wins, list fields are unions.

TEMPLATE VALUES are YAML (``safe_load``), with these tolerances so that typing an answer the way the template's hints
show never breaks it:
  * tabs in the indentation (and between ``-`` and an item) count as spaces to the next multiple of 4 (YAML forbids
    them; Notepad types them); a value holding a tab is quoted;
  * a hex colour that starts a value is a value, never a comment: ``[#c93523, night blue]``, ``- #0e2346`` and
    ``palette: #0e2346, rust red`` all work;
  * a ``#`` comment needs two or more spaces (or a tab) before it, or must follow a closed ``[...]``, ``{...}`` or
    quoted value. The template's own hints use three spaces. After one space, ``#`` is part of the text, so
    ``tone: dark #1 hit`` keeps all of it. The template's own hint comments (``TEMPLATE_HINTS``) are comments
    whatever the spacing before them;
  * a plain value that YAML would misread is quoted first: a value with a ``#`` or ``: `` in it, a value that ends
    with ``:``, one that starts with ``@ ` % * & ! ? , ] }``, and yes/no/on/off/true/false.
  When a region still does not parse, each top-level key is parsed on its own, and each entry under ``characters``,
  ``voices``, ``sections``, ``line_singers``, ``motifs``, ``do_not``, ``symbolism``, ``notes``, ``themes``,
  ``references`` and ``palette`` too (an entry starts at every line at the entries' indent: a key, a ``- `` item or a
  stray line). The parts that parse are kept. An entry that fails is reported in a warning and in ``unparsed_keys``
  (meaning.json ``intent_unparsed``, an open question and a brief.md line) and its lines (comments removed) are kept
  verbatim as a note: never silently dropped, and one bad line never takes the other rules with it.
  Untouched template entries (empty strings, empty lists, empty keys) are no answer.

TEMPLATE KEYS (``TEMPLATE_KEYS``):
  ``logline``, ``summary``, ``setting``, ``tone``: text. ``themes``, ``references``: a list, or a comma-separated
  string. ``symbolism``, ``notes``, ``do_not``: a list; a plain string is ONE item (commas are text). ``do_not`` items
  are kept verbatim: they are the hard constraints.
  ``perspective``: ``{narrator: C1, addressee: C2}`` (or ``- narrator: C1`` bullets).
  ``characters``: ``C1: {name, description, voices: [V1], lead_backing: lead|backing|both}``, or ``C1: The Keeper = V1``,
  or bullets ``- C1 The Keeper = V1 (the low voice). Lead.`` (short form: the name runs up to ``=`` / ``(`` / ``:``;
  ``V<n>`` ids are its voices; the words lead / backing (harmony, choir, backup) set lead_backing; the rest is the
  description).
  ``voices``: which character sings each detected voice, voice first like the viewer block: ``V1: C1 The Keeper``
  (a map) or bullets ``- V1 = C1 The Keeper``; ``V1 -> C1`` and ``V1 is C1`` are accepted too. A voice has one
  character: this mapping wins over ``characters.*.voices``. An integer (``voices: 3``) is the number of singers
  (the voices stage clusters into that many voices).
  ``line_singers``: ``{L005: C1+C2}`` or bullets ``- L005: C1+C2`` (``=`` / ``->`` too; ``+ & , /`` join singers).
  ``palette``: hex codes or colour words. ``motifs``: ``[{name, lines: [L001], note}]`` or ``- name (L001, L009): note``.
  ``sections``: keyed by section id (``S05``) or by a label (``chorus``, ``chorus#2``, ``last chorus``, ``drop``; see
  ``anchor.py``), each ``{t0, t1, occurrence_label, feel, meaning, emotion, movement, camera, palette, characters,
  do_not}``; a plain string is the feel; bullets ``- Chorus: wide shots`` are ``{chorus: {feel: wide shots}}``.
  Unknown keys are reported in a warning and kept verbatim as a note.

FREE TEXT -> NOTES. The text outside template regions and the viewer block is cut into notes: a note is a markdown
heading with everything under it up to the next heading, template region or the end (text before the first heading is
a note of its own). Lines are kept verbatim (trailing spaces cut, runs of blank lines collapsed). A heading with no text
of its own joins the note below it; directly above a template region it is the region's label and is not a note.
A copy of ``meaning/interview.md`` is recognised: the harness's own lines (title, preamble, status, voice facts, the
template heading, the bullets of ``## Open questions``) are not the user's; a question title is kept only as the
heading of the user's answer below or after it, and text the user typed after a harness line stays the user's.
An untouched copy of the interview therefore answers nothing.

The result is a plain dict (see ``empty_intent``); ``n_characters`` is what the voices stage may use as the voice count
(PLAN §5 voices), ``n_voices`` an explicit singer count. Stdlib + PyYAML (safe_load only).
"""
from __future__ import annotations

import re
from typing import Any

from . import interview_text as IV
from .colors import parse_palette

__all__ = ["parse_intent", "empty_intent", "SECTION_WORDS", "TEMPLATE_KEYS", "TEMPLATE_HINTS", "split_singers",
           "tolerant_yaml_line", "free_text_notes", "RULE_WORDS"]

TEMPLATE_KEYS = ("logline", "summary", "themes", "setting", "tone", "perspective", "characters", "voices",
                 "line_singers", "palette", "do_not", "motifs", "symbolism", "sections", "references", "notes")
#: words that address sections by label or EDM role
SECTION_WORDS = ("intro", "verse", "pre-chorus", "prechorus", "chorus", "post-chorus", "hook", "bridge", "inst",
                 "instrumental", "solo", "break", "breakdown", "build", "buildup", "build-up", "drop", "outro",
                 "interlude", "refrain", "silence")
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1, "final": -1}
#: words that make a free-text note read like a rule. Advisory only: such a note stays a note (never a do-not rule);
#: the meaning stage asks the user to move it into the template's do_not.
RULE_WORDS = re.compile(r"\b(?:never|avoid|don'?t|do\s+not|must\s+not|mustn'?t|no-?gos?|forbidden|off[- ]limits|"
                        r"banned|taboo)\b", re.I)

_HEAD = re.compile(r"^(#{1,6})[ \t]+\S")
_CHAR = re.compile(r"^\**(C[1-9]\d*)\**\b\s*[:.\-–—]?\s*(.*)$")
_VOICE = re.compile(r"\bV([1-9]\d*)\b")
_VMAP = re.compile(r"^\**(V[1-9]\d*)\**\s*(?:=|->|→|:|\bis\b)\s*\**(C[1-9]\d*)\**\b[\s,.:;=\-–—]*(.*?)\s*$", re.I)
_LINE_SINGER = re.compile(r"\b(L\d{3,})\b\s*(?:[:=]|->|→)\s*(C[1-9]\d*(?:\s*[+&,/]\s*C[1-9]\d*)*)")
_SEC_ID = r"S\d{2,}"
_WORDS_ALT = "|".join(sorted((re.escape(w) for w in SECTION_WORDS), key=len, reverse=True))
_SEC_KEY = re.compile(
    rf"(?:(?<=^)|(?<=[.;!?]\s)|(?<=[.;!?]\s\s))\s*\**((?:(?:first|second|third|fourth|fifth|last|final)\s+)?"
    rf"(?:{_SEC_ID}|(?:{_WORDS_ALT})(?:#\d+|\s+\d+)?)s?)\**\s*:\s*",
    re.I,
)

# ---- template regions
_FENCE_OPEN = re.compile(r"^\s*```+\s*(yaml|yml|mvh-intent)\b.*$", re.I)
_FENCE_ANY = re.compile(r"^\s*```")
_FENCE_CLOSE = re.compile(r"^\s*```+\s*$")
_MARKER = re.compile(r"^\s*#\s*mvh-intent\b", re.I)
_TKEY = re.compile(r"^(" + "|".join(TEMPLATE_KEYS) + r")[ \t]*:(?=[ \t]|$)")
#: a map key: may hold a '#' that does not follow a space ('chorus#2:'); ' #' would start a YAML comment
_KEY = r"[A-Za-z0-9_](?:[\w.\-]|(?<! )#| (?!#))*?"
_YKEY = re.compile(r"^(" + _KEY + r")[ \t]*:(?=[ \t]|$)")
_PARTS = re.compile(r"^([ \t]*)((?:-[ \t]+)*)(?:(" + _KEY + r")[ \t]*:(?=[ \t]|$))?([ \t]*)(.*)$")
_HEXTOK = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9A-Za-z_\-])")
_BOOLISH = re.compile(r"^(?:yes|no|on|off|y|n|true|false)$", re.I)
_NESTED = ("characters", "voices", "sections", "line_singers", "motifs", "do_not", "symbolism", "notes", "themes",
           "references", "palette")
#: template keys whose value is a list of items: a bare 'key: value' line among their '- ' items is a stray line, not
#: an item (VWU1-a)
_LIST_KEYS = ("do_not", "symbolism", "notes", "themes", "references", "palette", "motifs")
#: a column-0 block-sequence item: a dash then a space, a tab or nothing ('- item', '-<TAB>item', '-') (VWU1-b)
_COL0_ITEM = re.compile(r"^-(?:[ \t]|$)")
#: tab stop used to expand tabs in the indentation of template lines (YAML forbids tab indentation)
TAB_WIDTH = 4

#: the template's own hint comments: cut as comments whatever the spacing before them (they never become claims)
TEMPLATE_HINTS = ("# hex (#", "# one per person on screen", "# the harness proposes voices", "# lead_backing:",
                  "# optional per-line fixes", "# rules in your own words", "# [{name: lanterns",
                  "# name, the lyric lines", "# which character sings each voice")


def empty_intent() -> dict[str, Any]:
    return {
        "present": False, "form": "none", "logline": None, "summary": None, "setting": None, "tone": None,
        "themes": [], "symbolism": [], "perspective": {"narrator": None, "addressee": None},
        "characters": {}, "voice_map": {}, "n_voices": None, "line_singers": {}, "palette": [], "palette_names": [],
        "palette_unparsed": [], "do_not": [], "motifs": [], "sections": [], "references": [], "notes": [],
        "free_notes": [], "warnings": [], "n_characters": None,
        # W4A-UD1: the template key of every entry that did not parse and was kept as a note (one per entry)
        "unparsed_keys": [],
    }


def split_singers(s: str) -> list[str]:
    """'C1+C2' / 'C1 & C2' / 'C1, C2' -> ['C1', 'C2'] (order kept, duplicates dropped)."""
    out: list[str] = []
    for c in re.findall(r"C[1-9]\d*", str(s)):
        if c not in out:
            out.append(c)
    return out


def _clean(v: Any) -> str | None:
    if v is None or isinstance(v, (dict, list)):
        return None
    s = str(v).strip()
    return s or None


def _item_text(x: Any) -> str | None:
    """A list item as text. A one-key map (``- Chorus: no faces`` reads as YAML ``{Chorus: no faces}``) is the
    'key: value' the user typed."""
    if x is None:
        return None
    if isinstance(x, dict):
        parts = [f"{k}: {v}" if v not in (None, "") else f"{k}:" for k, v in x.items()]  # "- x:" is "x:"
        return "; ".join(parts).strip() or None
    s = str(x).strip()
    return s or None


def _strs(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[,\n]", v) if s.strip()]
    if isinstance(v, (list, tuple)):
        return [t for t in (_item_text(x) for x in v) if t]
    t = _item_text(v)
    return [t] if t else []


def _texts(v: Any) -> list[str]:
    """Free-text list items (do_not rules, symbolism, notes): a plain string is ONE item (commas are text)."""
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    return _strs(v)


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


def _char_from_text(rest: str) -> dict[str, Any]:
    """The template's short character form (after the id): 'The Keeper = V1 (the low voice). Lead.'"""
    voices = [f"V{v}" for v in _VOICE.findall(rest)]
    name_part = re.split(r"\s*(?:=|\(|:|\bis\b|\bvoice\b|–|—|\s-\s)\s*", rest, maxsplit=1)[0].strip(" *.,")
    desc = rest[len(name_part):] if name_part and rest.startswith(name_part) else rest
    desc = re.sub(r"(?:=|\bis\b)?\s*(?:the\s+)?(?:voice\s*)?\bV[1-9]\d*\b", "", desc, flags=re.I)
    desc = re.sub(r"[()]", "", desc)
    desc = re.sub(r"\s+([.,;])", r"\1", re.sub(r"\s+", " ", desc)).strip(" .,;:=-")
    return {"name": name_part or None, "description": desc or None, "voices": voices,
            "lead_backing": _lead_word(rest)}


def _section_notes(body: str) -> list[dict[str, Any]]:
    """A ``sections:`` bullet: 'Intro: slow drift. Verse: call and response' -> two claims (feel)."""
    ms = list(_SEC_KEY.finditer(body))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        txt = body[m.end():end].strip().rstrip(".").strip()
        if not txt or txt.startswith("#"):
            continue  # empty, or a comment
        key = re.sub(r"\s+", " ", m.group(1).strip().lower())
        key = re.sub(r"^(s\d{2,})$", lambda mm: mm.group(1).upper(), key)
        out.append({"key": key, "t0": None, "t1": None, "occurrence_label": None, "feel": txt, "meaning": None,
                    "emotion": None, "movement": None, "camera": None, "palette": [], "palette_unparsed": [],
                    "characters": [], "do_not": [], "origin": "yaml"})
    return out


def _vmap_text(text: str) -> tuple[str, str, str] | None:
    """'V1 = C1 The Keeper' / 'V1 -> C1' / 'V1 is C1, the Keeper' -> ('V1', 'C1', 'The Keeper')."""
    m = _VMAP.match(text.strip())
    if not m:
        return None
    return m.group(1).upper(), m.group(2).upper(), m.group(3).strip(" .,;*")


# ============================================================================================ layer 2: YAML tolerance
def _is_comment_line(ln: str) -> bool:
    t = ln.lstrip()
    return t.startswith("#") and not t.startswith("##") and not _HEXTOK.match(t)


def _cut_comment(line: str) -> str:
    """The line without its trailing ``#`` comment ('' for a comment line), by the grammar's comment rule: quote-aware;
    a hex colour that starts a value is text; ``#`` needs 2+ spaces or a tab before it, or a closed flow/quoted value."""
    if line.lstrip().startswith("#"):
        return ""
    in_dq = in_sq = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_dq:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_dq = False
        elif in_sq:
            if ch == "'":
                in_sq = False
        elif ch == '"' and (i == 0 or line[i - 1] in " \t[{,:-"):
            in_dq = True
        elif ch == "'" and (i == 0 or line[i - 1] in " \t[{,:-"):
            in_sq = True
        elif ch == "#" and i > 0 and line[i - 1] in " \t":
            j = i
            while j > 0 and line[j - 1] in " \t":
                j -= 1
            ws = line[j:i]
            prev = line[j - 1] if j > 0 else ""
            if line.startswith(TEMPLATE_HINTS, i):
                return line[:j]  # the template's own hint, whatever the spacing
            value_start = prev in "[{,:-" or j == 0
            if value_start and _HEXTOK.match(line, i):
                i += 1
                continue
            if len(ws) >= 2 or "\t" in ws or prev in "]}\"'":
                return line[:j]
        i += 1
    return line


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _quote_flow(v: str) -> tuple[str, bool]:
    """Quote the plain items that hold a ``#`` inside a one-line flow collection (``[#c93523, night blue]``).
    -> (text, closed on this line). Text after the closing bracket is kept (a comment was already cut)."""
    out: list[str] = []
    stack: list[str] = []
    i = 0
    n = len(v)
    expect = False
    while i < n:
        ch = v[i]
        if ch in "\"'":
            j = i + 1
            while j < n and v[j] != ch:
                j += 2 if (ch == '"' and v[j] == "\\") else 1
            out.append(v[i:j + 1])
            i, expect = j + 1, False
            continue
        if ch in "[{":
            stack.append(ch)
            out.append(ch)
            expect = True
        elif ch in "]}":
            if stack:
                stack.pop()
            out.append(ch)
            expect = False
            if not stack:
                return "".join(out) + v[i + 1:], True
        elif ch == "," or (ch == ":" and i + 1 < n and v[i + 1] in " \t"):
            out.append(ch)
            expect = True
        elif ch in " \t" or not expect:
            out.append(ch)
        else:  # a plain item: up to the next ',', ']' or '}' (or ': ' inside a {map})
            j = i
            while j < n and v[j] not in ",]}" and not (v[j] == ":" and j + 1 < n and v[j + 1] in " \t"
                                                        and stack and stack[-1] == "{"):
                j += 1
            item = v[i:j].rstrip()
            out.append(_q(item) if "#" in item else item)
            out.append(v[i + len(item):j])
            i, expect = j, False
            continue
        i += 1
    return "".join(out), not stack


def tolerant_yaml_line(line: str) -> str:
    """One template line made safe for ``yaml.safe_load`` by the grammar's tolerances (comment rule, hex colours,
    quoting plain values YAML would misread). Structure (indent, ``- ``, keys) is unchanged."""
    cut = _cut_comment(line).rstrip()
    if not cut.strip():
        return ""
    m = _PARTS.match(cut)
    if not m:
        return cut
    indent, dashes, key, sep, val = m.groups()
    if not val:
        return cut
    head = indent + dashes + (f"{key}:" if key is not None else "") + (sep if key is not None else "")
    if key is not None and not sep:
        head += " "
    c0 = val[0]
    if c0 in "\"'|>":
        return head + val
    if c0 in "[{":
        flow, _closed = _quote_flow(val)
        return head + flow
    if val in ("~", "null", "Null", "NULL"):
        return head + val
    if ("#" in val or "\t" in val or re.search(r":(\s|$)", val) or c0 in "@`%*&!?,]}" or val.startswith("- ")
            or _BOOLISH.match(val)):
        return head + _q(val)
    return head + val


# ============================================================================================ layer 2: regions
def _scan_unfenced(lines: list[str], i: int) -> int:
    """-> end index (exclusive) of the template-shaped run starting at ``lines[i]`` (see the grammar, layer 2)."""
    last = i - 1
    list_ok = False  # column-0 '- ' items continue the region only directly under a key that has no value
    for j in range(i, len(lines)):
        ln = lines[j]
        t = ln.strip()
        if not t:
            continue  # a blank line inside a block sequence is valid YAML: 'do_not:', blank, '- item' (W4A-UD1)
        if _FENCE_ANY.match(ln):
            break
        if _MARKER.match(ln):
            last, list_ok = j, False
        elif _TKEY.match(ln):
            last, list_ok = j, not _cut_comment(ln).split(":", 1)[1].strip()
        elif ln[0] in " \t":
            last, list_ok = j, False
        elif _is_comment_line(ln):
            continue  # counted only when more template follows
        elif _COL0_ITEM.match(t) and list_ok:  # '- item' and '-<TAB>item' (VWU1-b)
            last = j
        elif t[0] in "]}":
            last = j
        else:
            break
    return last + 1


def _regions(lines: list[str]) -> tuple[list[tuple[int, int]], set[int]]:
    """-> ([(start, end)] YAML line ranges, every consumed line index incl. fences)."""
    regions: list[tuple[int, int]] = []
    consumed: set[int] = set()
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        if _FENCE_OPEN.match(ln):
            j = next((k for k in range(i + 1, n) if _FENCE_ANY.match(lines[k])), None)
            if j is not None and _FENCE_CLOSE.match(lines[j]):
                regions.append((i + 1, j))
                consumed.update(range(i, j + 1))
                i = j + 1
                continue
            e = max(_scan_unfenced(lines, i + 1), i + 1)  # no closing fence: the template-shaped lines after it
            regions.append((i + 1, e))
            consumed.update(range(i, e))
            i = e
            continue
        if _FENCE_ANY.match(ln):  # another code fence: its text is free text, the fence lines are dropped
            consumed.add(i)
            i += 1
            continue
        if _MARKER.match(ln) or _TKEY.match(ln):
            start = i
            while start > 0 and start - 1 not in consumed and _is_comment_line(lines[start - 1]):
                start -= 1  # the template's comment lines directly above its first key
            e = _scan_unfenced(lines, i)
            regions.append((start, e))
            consumed.update(range(start, e))
            i = max(e, i + 1)
            continue
        i += 1
    return regions, consumed


def _yaml_load(text: str) -> tuple[Any, bool]:
    import yaml

    try:
        return yaml.safe_load(text), True
    except yaml.YAMLError:
        return None, False


def _chunks(lines: list[str], indent: int, entries: bool = False) -> list[tuple[int, int]]:
    """Split ``lines`` at the lines that hold a key at ``indent`` -> [(start, end)]; leading lines join the first.
    ``entries`` (the body of one key): EVERY line at ``indent`` or less starts an entry (a key, a ``- `` item or a
    stray line), so one bad line never takes its neighbours' entries with it (W4A-UD1)."""
    if entries:
        starts = [k for k, ln in enumerate(lines) if ln.strip() and (len(ln) - len(ln.lstrip(" "))) <= indent]
    else:
        starts = [k for k, ln in enumerate(lines)
                  if ln.strip() and (len(ln) - len(ln.lstrip(" "))) == indent and _YKEY.match(ln[indent:])]
    if not starts:
        return [(0, len(lines))]
    starts[0] = 0
    return [(a, starts[k + 1] if k + 1 < len(starts) else len(lines)) for k, a in enumerate(starts)]


def _load_region(raw: list[str], warns: list[str],
                 demoted: list[str] | None = None) -> tuple[dict[str, Any] | None, set[int]]:
    """Parse one template region. -> (merged mapping or None, raw line indices to read as free text instead).
    ``demoted`` collects the template key of every entry whose lines became a note."""
    demoted = demoted if demoted is not None else []
    safe = _safe_lines(raw)
    d, ok = _yaml_load("\n".join(safe))
    if ok:
        if d is None:
            return {}, set()
        if isinstance(d, dict):
            return d, set()
        if any(ln.strip() for ln in safe):
            warns.append("intent.md: a template block is not a 'key: value' map; its lines were kept as a note")
            demoted.append("?")
        return None, set(range(len(raw)))
    merged: dict[str, Any] = {}
    fallback: set[int] = set()
    for a, b in _chunks(safe, 0):
        part, ok = _yaml_load("\n".join(safe[a:b]))
        if ok and isinstance(part, dict):
            merged.update(part)
            continue
        if ok and part is None:
            continue
        key_line = next((x for x in safe[a:b] if x.strip() and _YKEY.match(x)), "")
        key_m = _YKEY.match(key_line)
        key = key_m.group(1) if key_m else None
        a_key = a + safe[a:b].index(key_line) if key_line else a
        if key in _NESTED and b - a_key > 1:
            body = safe[a_key + 1:b]
            ind = next((len(x) - len(x.lstrip(" ")) for x in body if x.strip()), 2)
            sub: dict[str, Any] = {}
            subl: list[Any] = []
            order: list[tuple[str, Any, int, int]] = []  # ('map' | 'list', value, sa, sb) as typed (VWU1-a)
            for sa, sb in _chunks(body, ind, entries=True):
                piece, ok2 = _yaml_load(f"{key}:\n" + "\n".join(body[sa:sb]))
                val = piece.get(key) if ok2 and isinstance(piece, dict) else None
                if ok2 and isinstance(val, dict):
                    sub.update(val)
                    order.append(("map", val, sa, sb))
                elif ok2 and isinstance(val, list):
                    subl.extend(val)
                    order.append(("list", val, sa, sb))
                elif ok2 and val is None:
                    continue
                else:
                    first = next((x.strip() for x in body[sa:sb] if x.strip()), "")
                    warns.append(f"intent.md: the template entry '{key}: {first.split(':', 1)[0][:20]}' does not parse "
                                 "as YAML; its lines were kept verbatim as a note, not as fields (check quotes and brackets)")
                    fallback.update(range(a_key + 1 + sa, a_key + 1 + sb))
                    demoted.append(key)
            if sub and subl:  # VWU1-a: '- ' items AND 'key: value' lines under one key: one form never drops the other
                if key in _LIST_KEYS and key != "notes":
                    # the '- ' items are the answer; a stray 'Also: ...' line beside them is a note, never an item
                    merged[key] = subl
                    for kind, _v, sa, sb in order:
                        if kind != "map":
                            continue
                        first = next((x.strip() for x in body[sa:sb] if x.strip()), "")
                        warns.append(f"intent.md: under '{key}:' the line '{first.split(':', 1)[0][:20]}: ...' is not a "
                                     "'- ' item like the others; it was kept verbatim as a note, not as an item (start it "
                                     "with '- ' to make it one)")
                        fallback.update(range(a_key + 1 + sa, a_key + 1 + sb))
                        demoted.append(key)
                else:  # notes (text either way) and the map keys (bullets are read by _list_answer): all, as typed
                    merged[key] = [x for kind, v, _sa, _sb in order
                                   for x in (v if kind == "list" else [{kk: vv} for kk, vv in v.items()])]
            elif sub or subl:
                merged[key] = sub if sub else subl
            continue
        warns.append(f"intent.md: the template key '{key or '?'}' does not parse as YAML; its lines were kept verbatim as a note, "
                     "not as fields (check quotes and brackets)")
        fallback.update(range(a, b))
        demoted.append(key or "?")
    return merged, fallback


def _expand_indent(line: str) -> str:
    """Tabs in a line's indentation (and between its ``- `` dashes) -> spaces (tab stop ``TAB_WIDTH``): Notepad and
    many editors indent with a tab, which YAML forbids. Tabs inside the text are kept."""
    m = re.match(r"^[ 	]*(?:-[ 	]+)*", line)
    lead = m.group(0) if m else ""
    if "	" not in lead:
        return line
    return lead.expandtabs(TAB_WIDTH) + line[len(lead):]


def _safe_lines(raw: list[str]) -> list[str]:
    """``tolerant_yaml_line`` over a region, except inside a block scalar (``key: |`` / ``key: >``), where every
    line is text as typed (a '#' there is not a comment)."""
    out: list[str] = []
    block_indent: int | None = None
    for ln in raw:
        ln = _expand_indent(ln)
        ind = len(ln) - len(ln.lstrip(" "))
        if block_indent is not None:
            if not ln.strip() or ind > block_indent:
                out.append(ln.rstrip())
                continue
            block_indent = None
        safe = tolerant_yaml_line(ln)
        out.append(safe)
        if re.search(r":[ \t]*[|>][+-]?\d?$", safe) or re.fullmatch(r"[ \t]*-[ \t]+[|>][+-]?\d?", safe):
            block_indent = ind
    return out


# ============================================================================================ layer 2: apply
def _apply_yaml(d: dict[str, Any], out: dict[str, Any]) -> None:
    out["form"] = "yaml" if out["form"] == "none" else ("yaml+text" if out["form"] == "text" else out["form"])
    unknown = [str(k) for k in d if str(k) not in TEMPLATE_KEYS]
    if unknown:
        out["warnings"].append("intent.md: unknown template key(s) kept as notes, not fields: " + ", ".join(unknown[:6]))
        for k in d:
            if str(k) not in TEMPLATE_KEYS:
                v = d[k]
                txt = "; ".join(_strs(v)) if isinstance(v, (list, dict)) else (_clean(v) or "")
                if isinstance(v, dict):
                    txt = "; ".join(f"{kk}: {vv}" for kk, vv in v.items())
                note = f"{k}: {txt}".strip().rstrip(":")
                if note and note not in out["notes"]:
                    out["notes"].append(note)
    for k in TEMPLATE_KEYS:
        v = d.get(k)
        if isinstance(v, list) and any(x is None for x in v):
            out["warnings"].append(f"intent.md: an empty item in '{k}' was ignored")
    for k in ("logline", "summary", "setting", "tone"):
        if _clean(d.get(k)) and not out.get(k):
            out[k] = _clean(d.get(k))
    for k in ("themes", "references"):
        vals = _strs(d.get(k))
        if vals and not out[k]:
            out[k] = vals
    for k in ("symbolism",):
        vals = _texts(d.get(k))
        if vals and not out[k]:
            out[k] = vals
    for x in _texts(d.get("notes")):  # notes are a union (template notes, then the free text)
        if x not in out["notes"]:
            out["notes"].append(x)
    d = dict(d)
    for k in ("perspective", "characters", "voices", "line_singers", "sections"):
        if isinstance(d.get(k), list):  # a key answered with bullets: '- C1 Ann = V1', '- L005: C1+C2', '- Chorus: wide'
            d[k] = _list_answer(k, d[k], out)
    p = d.get("perspective")
    if isinstance(p, dict):
        for k in ("narrator", "addressee"):
            if _clean(p.get(k)) and not out["perspective"][k]:
                out["perspective"][k] = _clean(p.get(k))
    chars = d.get("characters")
    if isinstance(chars, dict):
        for cid, c in chars.items():
            cid = str(cid).strip()
            if not re.fullmatch(r"C[1-9]\d*", cid):
                out["warnings"].append("intent.md: character keys must look like C1, C2 (one key ignored)")
                continue
            if not isinstance(c, dict) or "_text" in c:  # 'C1: The Keeper = V1', or a '- C1 ...' bullet
                txt = c["_text"] if isinstance(c, dict) else (_clean(c) or "")
                if txt and cid not in out["characters"]:
                    out["characters"][cid] = _char_from_text(txt)
                continue
            c = c if isinstance(c, dict) else {"name": c}
            voices = [f"V{m}" for m in _VOICE.findall(" ".join(_strs(c.get("voices") or c.get("voice"))))]
            lb = _clean(c.get("lead_backing"))
            if not (_clean(c.get("name")) or _clean(c.get("description")) or voices or lb):
                continue  # an untouched template entry is not an answer
            if cid in out["characters"]:
                continue
            out["characters"][cid] = {
                "name": _clean(c.get("name")), "description": _clean(c.get("description")),
                "voices": voices, "lead_backing": lb if lb in ("lead", "backing", "both") else None,
            }
    _apply_voices(d.get("voices"), out)
    ls = d.get("line_singers")
    if isinstance(ls, dict):
        for lid, s in ls.items():
            cs = split_singers(str(s))
            if re.fullmatch(r"L\d{3,}", str(lid).strip()) and cs:
                out["line_singers"].setdefault(str(lid).strip(), cs)
    pal = _strs(d.get("palette"))
    if pal and not out["palette"] and not out["palette_unparsed"]:
        hexes, names, bad = parse_palette(pal)
        out["palette"], out["palette_names"], out["palette_unparsed"] = hexes, names, bad
    for r in _texts(d.get("do_not")):
        if r not in out["do_not"]:
            out["do_not"].append(r)
    motifs = d.get("motifs")
    if isinstance(motifs, list):
        for m in motifs:
            if isinstance(m, dict) and _clean(m.get("name")):
                out["motifs"].append({"name": _clean(m.get("name")),
                                      "lines": re.findall(r"L\d{3,}", " ".join(_strs(m.get("lines")))),
                                      "note": _clean(m.get("note"))})
            elif isinstance(m, str) and m.strip():
                out["motifs"].append(_motif_from_text(m))
    secs = d.get("sections")
    if isinstance(secs, dict):
        for key, s in secs.items():
            s = s if isinstance(s, dict) else {"feel": s}
            claim = _section_claim(str(key).strip(), s)
            if claim is not None:
                out["sections"].append(claim)


def _list_answer(key: str, items: list[Any], out: dict[str, Any]) -> dict[str, Any]:
    """A map key (``characters``, ``voices``, ``line_singers``, ``sections``, ``perspective``) answered with a list of
    bullets. A ``- key: value`` item is that map entry; a text item is read by the key's short form (character line,
    voice mapping, per-line singers, section notes). An item that matches nothing is kept in ``notes`` with a warning."""
    merged: dict[str, Any] = {}
    for it in items:
        if it is None:
            continue
        if isinstance(it, dict) and (key == "perspective" or all(isinstance(v, dict) for v in it.values())
                                     or key == "line_singers"
                                     or (key == "characters" and all(re.fullmatch(r"C[1-9]\d*", str(k).strip())
                                                                     for k in it))
                                     or (key == "voices" and all(re.fullmatch(r"V[1-9]\d*", str(k).strip(), re.I)
                                                                 for k in it))):
            merged.update(it)
            continue
        text = _item_text(it) or ""
        hit = False
        if key == "voices":
            vm = _vmap_text(text)
            if vm:
                merged.setdefault(vm[0], f"{vm[1]} {vm[2]}".strip())
                hit = True
        elif key == "characters":
            mc = _CHAR.match(text)
            if mc and not mc.group(2).strip().startswith("{"):
                merged.setdefault(mc.group(1), {"_text": mc.group(2).strip()})
                hit = True
        elif key == "line_singers":
            for m in _LINE_SINGER.finditer(text):
                merged.setdefault(m.group(1), m.group(2))
                hit = True
        elif key == "sections":
            for claim in _section_notes(text):
                merged.setdefault(claim["key"], {"feel": claim["feel"]})
                hit = True
        if not hit and text:
            out["warnings"].append(f"intent.md: an item under '{key}:' was not understood; kept in notes")
            if text not in out["notes"]:
                out["notes"].append(text)
    return merged


def _apply_voices(v: Any, out: dict[str, Any]) -> None:
    """The ``voices`` key: an integer is the singer count; a map ``{V1: C1 Name}`` (or bullets, already merged by
    ``_list_answer``) maps each voice to one character and wins over ``characters.*.voices``."""
    if v is None or v == "" or v == {} or v == []:
        return
    if isinstance(v, bool):
        out["warnings"].append("intent.md: 'voices' is a number of singers or a 'V1: C1 Name' map; ignored")
        return
    if isinstance(v, int) or (isinstance(v, str) and re.fullmatch(r"\s*\d{1,2}\s*", v)):
        n = int(v)
        if n >= 1 and out["n_voices"] is None:
            out["n_voices"] = n
        return
    if not isinstance(v, dict):
        out["warnings"].append("intent.md: 'voices' is a number of singers or a 'V1: C1 Name' map; kept as a note")
        txt = "voices: " + "; ".join(_strs(v))
        if txt not in out["notes"]:
            out["notes"].append(txt)
        return
    for vid, who in v.items():
        vid_s = str(vid).strip().upper()
        mm = re.fullmatch(r"(C[1-9]\d*)\b[\s,.:;=\-–—]*(.*?)\s*", str(who or "").strip())
        if not re.fullmatch(r"V[1-9]\d*", vid_s) or not mm:
            if who not in (None, ""):
                out["warnings"].append("intent.md: a 'voices' entry is not 'V1: C1 Name'; kept as a note")
                note = f"voices: {vid}: {who}"
                if note not in out["notes"]:
                    out["notes"].append(note)
            continue
        if vid_s in out["voice_map"]:
            continue  # an earlier template region answered this voice
        cid, name = mm.group(1), mm.group(2).strip(" .,;*") or None
        other = [c for c, rec in out["characters"].items() if vid_s in rec["voices"] and c != cid]
        if other:
            out["warnings"].append(f"intent.md: {vid_s} is listed under {other[0]} and mapped to {cid} under 'voices'; "
                                   "'voices' wins (a voice has one character)")
        known = cid in out["characters"]
        _map_voice(out, vid_s, cid, None)
        if name and not (known and out["characters"][cid].get("name")):
            out["characters"][cid]["name"] = name


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
    dn = _texts(s.get("do_not"))
    if not any(fields.values()) and not hexes and not chars and not dn:
        return None
    return {"key": key, "t0": _num(s.get("t0")), "t1": _num(s.get("t1")),
            "occurrence_label": _clean(s.get("occurrence_label")), **fields, "palette": hexes,
            "palette_unparsed": bad, "characters": chars, "do_not": dn, "origin": origin}


def _motif_from_text(s: str) -> dict[str, Any]:
    """'lanterns (L001, L009): memory' -> {name: lanterns, lines: [L001, L009], note: memory}."""
    lines = re.findall(r"L\d{3,}", s)
    name, _sep, note = re.sub(r"\(?\s*L\d{3,}(?:\s*[,;/&]\s*L\d{3,})*\s*\)?", " ", s).partition(":")
    name = re.sub(r"\s+", " ", name).strip(" *.,;-")
    return {"name": name or s.strip(), "lines": lines, "note": note.strip() or None}



# ============================================================================================ free text -> notes
_Q_RE = [(re.compile(r"^[ \t]*(?:\d+[.)][ \t]+|[-*+][ \t]+)?\*\*(" + t + r")\*\*[ \t]*(.*)$"), re.compile(tail))
         for t, tail in IV.QUESTIONS]
_PLAIN_RE = [re.compile(r"^[ \t]*(?:\d+[.)][ \t]+|[-*+][ \t]+)?(" + t + r")[ \t]*(.*)$") for t in IV.PLAIN_QUESTIONS]


def _strip_markup(s: str) -> str:
    return re.sub(r"\*\*|__|`", "", s).strip()


def _echo(line: str, in_open_questions: bool) -> list[tuple[str, str]]:
    """One line of free text -> [(kind, text)]: kind 'user' (the user's words), 'ctx' (the harness's question, kept
    only as the heading of an answer) or nothing (the harness's own text, dropped). See the grammar: interview copy."""
    if IV.ECHO_LINE.match(line):
        return []
    if line.strip() == IV.OPEN_QUESTIONS_HEADING:
        return [("ctx", IV.OPEN_QUESTIONS_HEADING)]
    if in_open_questions and re.match(r"^[-*][ \t]+\S", line):
        return [("ctx", line.rstrip())]  # a copied open question (column 0): context for a sub-bullet answer
    for rx, tail in _Q_RE:
        m = rx.match(line)
        if not m:
            continue
        rest = m.group(2).strip()
        tm = tail.match(rest)
        if not tm:  # a bare title or the user's own text after it: the user's line, verbatim
            return [("user", line.rstrip())]
        user = rest[tm.end():].strip()
        return [("ctx", "## " + _strip_markup(m.group(1)))] + ([("user", user)] if user else [])
    for rx in _PLAIN_RE:
        m = rx.match(line)
        if m:
            user = m.group(2).strip()
            return [("ctx", "## " + _strip_markup(m.group(1)))] + ([("user", user)] if user else [])
    m = IV.VOICE_FACT.match(line)
    if m:
        user = line[m.end():].strip()
        return [("user", f"- {m.group(1)}: {user}")] if user else []
    m = IV.WHICH_CHARACTER.match(line)
    if m:
        user = line[m.end():].strip()
        return [("user", user)] if user else []
    return [("user", line.rstrip())]


def free_text_notes(lines: list[str | None]) -> list[str]:
    """The free-text notes of intent.md. ``lines``: the file's lines with every template-region line replaced by
    None (the viewer block and HTML comments already removed). Grammar: FREE TEXT -> NOTES."""
    items: list[tuple[str, str]] = []  # (kind, text); kind: user | ctx | head | ctxhead | blank | region
    in_oq = False
    for ln in lines:
        if ln is None:
            if not items or items[-1][0] != "region":
                items.append(("region", ""))
            continue
        if not ln.strip():
            items.append(("blank", ""))
            continue
        if _HEAD.match(ln):
            in_oq = ln.strip() == IV.OPEN_QUESTIONS_HEADING
        for kind, text in _echo(ln, in_oq):
            if kind == "ctx" and _HEAD.match(text):
                items.append(("ctxhead", text))
            elif kind == "user" and _HEAD.match(text):
                items.append(("head", text))
            else:
                items.append((kind, text))
    notes: list[str] = []
    heads: list[tuple[str, str]] = []  # the headings of the open note
    body: list[tuple[str, str]] = []  # its lines: (user | ctx | blank, text)

    def flush(at_region: bool, at_end: bool) -> None:
        nonlocal heads, body
        users = [i for i, (k, _t) in enumerate(body) if k == "user"]
        if users:
            keep: list[str] = []
            for i, (k, t) in enumerate(body):
                if k == "ctx" and not any(j > i for j in users):
                    continue  # a harness line with no answer after it
                if k == "ctx" and body[i + 1:i + 2] and body[i + 1][0] == "ctx":
                    continue  # a harness line followed by another one: no answer to it
                keep.append(t)
            text = "\n".join([t for _k, t in heads] + _tidy(keep))
            notes.append(text.strip("\n"))
            heads, body = [], []
            return
        user_heads = [(k, t) for k, t in heads if k == "head"]
        if at_region:
            heads = []  # a heading directly above the template labels it: not a note
        elif at_end:
            if user_heads:
                notes.append("\n".join(t for _k, t in user_heads))
            heads = []
        else:
            heads = user_heads  # a heading with no text of its own joins the note below it
        body = []

    for kind, text in items:
        if kind == "region":
            flush(at_region=True, at_end=False)
        elif kind in ("head", "ctxhead"):
            flush(at_region=False, at_end=False)
            heads.append((kind, text))
        elif kind == "blank":
            if body and body[-1][0] != "blank":
                body.append(("blank", ""))
        else:
            body.append((kind, text))
    flush(at_region=False, at_end=True)
    return [n for n in notes if n.strip()]


def _tidy(lines: list[str]) -> list[str]:
    """Strip leading / trailing blank lines and collapse inner runs to one."""
    out: list[str] = []
    for t in lines:
        if not t.strip() and (not out or not out[-1].strip()):
            continue
        out.append(t)
    while out and not out[-1].strip():
        out.pop()
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
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    lines = text.splitlines()
    regions, consumed = _regions(lines)
    free: list[str | None] = [None if i in consumed else ln for i, ln in enumerate(lines)]
    broken: list[str] = []
    for a, b in regions:
        raw = lines[a:b]
        d, fallback = _load_region(raw, out["warnings"], out["unparsed_keys"])
        if d:
            _apply_yaml(d, out)
        elif d is not None and out["form"] == "none":
            out["form"] = "yaml"  # an empty template region is still the template
        if fallback:  # an entry that did not parse: kept verbatim as a note (warned in _load_region)
            kept = _tidy([_cut_comment(raw[k]).rstrip() for k in sorted(fallback)])
            if kept:
                broken.append("\n".join(kept))
    notes = free_text_notes(free) + broken
    if notes:
        out["form"] = "text" if out["form"] == "none" else ("yaml+text" if out["form"] == "yaml" else out["form"])
    for n in notes:
        if n not in out["notes"]:
            out["notes"].append(n)
        out["free_notes"].append(n)
    if vb:
        _parse_viewer_block(vb.group(1), out)
    out["n_characters"] = len(out["characters"]) or None
    return out


# ============================================================================================ viewer block (M6a)
_VB_RE = re.compile(r"<!-- mvh-viewer:begin v\d+ -->(.*?)<!-- mvh-viewer:end -->\n?", re.S)
_VB_VOICE = re.compile(r"^- (V[1-9]\d*) = (C[1-9]\d*)(?: (.*))?$")
_VB_SEC = re.compile(r"^### (S\d{2,})(?: (\S.*?))? (-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?) s$")
_VB_KV = re.compile(r"^- (feel|meaning|movement|camera|palette|do not): ?(.*)$")


def _map_voice(out: dict[str, Any], v: str, cid: str, name: str | None) -> None:
    """A voice has one character: map ``v`` to ``cid`` (removing it from any other character)."""
    for c in out["characters"].values():
        if v in c["voices"]:
            c["voices"].remove(v)
    c = out["characters"].setdefault(cid, {"name": None, "description": None, "voices": [], "lead_backing": None})
    if v not in c["voices"]:
        c["voices"].append(v)
    if name and name != cid:
        c["name"] = name
    out["voice_map"][v] = cid


def _parse_viewer_block(body: str, out: dict[str, Any]) -> None:
    """The block ``mvh view`` maintains in intent.md (grammar: mvh.stages.viewer.intent_block, M6a): the user's own
    words edited in the viewer. It wins over the template (it is the latest edit)."""
    claims: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for raw in body.splitlines():
        line = raw.rstrip()
        vm = _VB_VOICE.match(line)
        if vm:
            _map_voice(out, vm.group(1), vm.group(2), (vm.group(3) or "").strip())
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
