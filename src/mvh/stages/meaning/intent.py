"""Parse ``meaning/intent.md`` (the user's answers) into claims. The file is an INPUT: never written here.

THE INTENT GRAMMAR (v3). One grammar covers every way a user answers; the interview's template round-trips through it
exactly (``docs.yaml_template`` writes back every user claim, and parsing that template gives the same claims).
The file is read in three layers. YAML template regions are read before the free text, and the free text only fills
fields they left empty (do-not rules, characters, line singers and section notes are unions). The viewer block wins.

Layer 1: the viewer block. ``<!-- mvh-viewer:begin v1 --> ... <!-- mvh-viewer:end -->`` (M6a grammar,
  ``mvh.stages.viewer.intent_block``): ``- V1 = C1 Name`` voice mappings and ``### S02 verse#1 9.000-17.000 s`` section
  bullets. It is the latest edit, so it wins over everything below. Other HTML comments are ignored.

Layer 2: template regions (YAML). A region is
  * a fenced block opened by ```` ```yaml ````, ```` ```yml ```` or ```` ```mvh-intent ````, up to its closing fence.
    When the closing fence is missing, the region runs over the template-shaped lines (below) after the opening one;
  * or, unfenced, it starts at a ``# mvh-intent`` marker line or at a column-0 template key line (``logline:``,
    ``characters:``, ... in lower case: ``TEMPLATE_KEYS``), together with the ``#`` comment lines directly above it.
    It runs over the template-shaped lines that follow: blank lines, indented lines, column-0 template key lines,
    column-0 ``- `` items directly under a key with no value, and ``#`` comment lines followed by more template.
    The first other line ends it: prose, a markdown ``##`` heading or a note such as ``Chorus: ...``.
  Values are YAML, with three tolerances so that typing an answer the way the template's hints show never breaks it:
  * a hex colour that starts a value is a value, never a comment: ``[#c93523, night blue]``, ``- #0e2346`` and
    ``palette: #0e2346, rust red`` all work;
  * a ``#`` comment needs two or more spaces (or a tab) before it, or must follow a closed ``[...]``, ``{...}`` or
    quoted value. The template's own hints use three spaces. After one space, ``#`` is part of the text, so
    ``tone: dark #1 hit`` keeps all of it;
  * a plain value that YAML would misread is quoted first. That covers a value with a ``#`` or ``: `` in it, a value
    that ends with ``:``, one that starts with ``@ ` % * & ! ? , ] }``, and yes/no/on/off/true/false.
  When a region still does not parse, each top-level key is parsed on its own, and each entry under ``characters``,
  ``sections``, ``line_singers`` and ``motifs`` too. The parts that parse are kept. An entry that fails is reported
  in a warning, and its lines (comments removed) are read as free text. Template comments never become claims; the
  template's own hint comments (``TEMPLATE_HINTS``) are comments whatever the spacing before them.
  A map key answered with bullets (``characters:`` then ``- C1 The Keeper = V1``; ``sections:`` then
  ``- Chorus: wide``; ``line_singers:`` then ``- L005: C1+C2``; ``perspective:`` then ``- narrator: C1``) reads each
  ``- key: value`` item as that map entry and each text item by the free-text rule of the key (rules 5-7). An item
  that matches nothing is kept in ``notes`` with a warning.
  Untouched template entries (empty strings, empty lists) are no answer.

Layer 3: free text (markdown), everything outside regions, read line by line. The first rule that matches wins:
  0. The interview's own text (the user copied ``interview.md`` and wrote answers under its questions). A question
     line (``9. **Never show**: what must never appear ...``, ``_IV_QUESTIONS``) whose remainder is the harness's
     text, or empty, is a heading for the answer below it; the block class is the question's (meaning -> story,
     the world -> setting, colours -> palette, never show -> do-not, others -> other). Text after the harness's part
     of the line is the first line of the answer. A question line with any other remainder is the user's own label
     line (rule 3/4). The preamble, the status line, the voice-fact bullets and ``## Open questions`` bullets are the
     harness's, never claims. An untouched copy of the interview therefore answers nothing.
  1. A heading (``#`` to ``######``) starts a block. The heading text decides what the block is:
     * an interview question (rule 0);
     * a do-not heading: the WHOLE heading is a do-not phrase (``Never show``, ``Do not``, ``Don'ts``, ``Avoid``,
       ``No-gos``, ``Hard rules``, ...; such a phrase followed by a colon counts too: ``## Never show: on screen``),
       or it is made only of do-not vocabulary with at least one trigger word (never, avoid, don't, do not, not,
       no-go, forbidden, off-limits, must not, banned, taboo) and filler words (what, things, I, we, want, to, see,
       show, these, ever, on screen, in the video, ...): ``What I don't want``, ``Avoid these``, ``Things I never
       want to see``, ``Never show these``. A title with any other word is not (``# Never Let Me Go``,
       ``# Don't Stop Me Now: my notes``, ``## The story: a night that never ends``, ``## Avoiding the obvious``);
     * ``Palette`` / ``Colours`` (the whole heading): each bullet or comma-separated item is a colour;
     * story / meaning / means / about / summary / logline: the summary (its first sentence is the logline);
       setting / world / place / where; tone; theme(s); symbol(s) / symbolism; motif(s); reference(s) / inspiration;
     * any other H1 is a title: its prose counts as the preamble (the text before the first heading).
  2. Inside a do-not heading block, every bullet (or every non-empty line, when there are no bullets) is one rule,
     kept verbatim. Nothing else is read from that block.
  3. A do-not label line, plain, bold, a bullet or numbered (``Never show: X``, ``- **Avoid**: X``,
     ``9. **Never show**: X``), is ONE rule X. A bare label (``**Never show**``, ``Avoid:``) opens a list: the
     bullets that follow it are rules, until the first blank line after a bullet, a heading, a non-bullet line or a
     character bullet (``- C1 ...``). A bare label that is itself a bullet lists the bullets indented under it, or,
     when the first one is at its own level, the bullets at its level.
  4. A field label (case-insensitive, may be bold or a bullet): ``Logline:``, ``Summary:``, ``Story:``, ``Meaning:``,
     ``Setting:``, ``(The) World:``, ``Tone:``, ``Themes:``, ``Symbolism:``, ``References:``, ``Notes:``,
     ``Narrator:`` or ``Addressee:``, followed by the value. ``Palette:`` / ``Colours:`` / ``Colors:`` (also
     ``Palette - ...``) gives the palette as hex codes or colour words (``night blue, #f2a541, rust red``).
  5. Per-line singers anywhere on a line: ``L005: C1+C2`` (also ``=`` / ``->``; ``+ & , /`` join singers).
  6. A character line: ``C1 The Lamplighter = voice V1 (the low voice). Lead.`` (may be a bullet or bold).
  7. Section notes: ``Intro: slow drift. Verse: call and response``, ``S03: ...``, ``chorus#2: ...``,
     ``last chorus: ...``, ``Drop: ...`` (several per line; see ``anchor.py`` for how keys find sections).
  8. In a themes / symbolism / references block, each bullet is one item (prose: one item). In a motifs block, each
     bullet is a motif ``name (L001, L009): note``.
  9. Prose: under a story heading it is the summary; under setting / tone headings, those fields. The preamble's
     prose is the summary when the file has no story heading. Any other prose or unmatched bullet is kept verbatim
     in ``notes``, so nothing the user wrote is dropped silently.

The result is a plain dict (see ``empty_intent``); ``n_characters`` is what the voices stage may use as the voice count
(PLAN §5 voices). Stdlib + PyYAML (safe_load only).
"""
from __future__ import annotations

import re
from typing import Any

from .colors import parse_palette

__all__ = ["parse_intent", "empty_intent", "SECTION_WORDS", "TEMPLATE_KEYS", "split_singers", "tolerant_yaml_line"]

TEMPLATE_KEYS = ("logline", "summary", "themes", "setting", "tone", "perspective", "characters", "line_singers",
                 "palette", "do_not", "motifs", "symbolism", "sections", "references", "notes")
#: words that address sections by label or EDM role
SECTION_WORDS = ("intro", "verse", "pre-chorus", "prechorus", "chorus", "post-chorus", "hook", "bridge", "inst",
                 "instrumental", "solo", "break", "breakdown", "build", "buildup", "build-up", "drop", "outro",
                 "interlude", "refrain", "silence")
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1, "final": -1}

_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CHAR = re.compile(r"^\**(C[1-9]\d*)\**\b\s*[:.\-–—]?\s*(.*)$")
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

# ---- layer 2 (template regions)
_FENCE_OPEN = re.compile(r"^\s*```+\s*(yaml|yml|mvh-intent)\b.*$", re.I)
_FENCE_ANY = re.compile(r"^\s*```")
_FENCE_CLOSE = re.compile(r"^\s*```+\s*$")
_MARKER = re.compile(r"^\s*#\s*mvh-intent\b", re.I)
_TKEY = re.compile(r"^(" + "|".join(TEMPLATE_KEYS) + r")[ \t]*:(?=[ \t]|$)")
_YKEY = re.compile(r"^([A-Za-z0-9_][\w.\- ]*?)[ \t]*:(?=[ \t]|$)")
_PARTS = re.compile(r"^([ \t]*)((?:-[ \t]+)*)(?:([A-Za-z0-9_][\w.\- ]*?)[ \t]*:(?=[ \t]|$))?([ \t]*)(.*)$")
_HEXTOK = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9A-Za-z_\-])")
_BOOLISH = re.compile(r"^(?:yes|no|on|off|y|n|true|false)$", re.I)
_NESTED = ("characters", "sections", "line_singers", "motifs")

# ---- layer 3 (free text)
_DN_PHRASE = (r"(?:never\s+show|never|do\s+not\s+show|do\s+not|don'?t\s+show|don'?ts|do-?nots?|avoid|must\s+not\s+show|"
              r"must\s+not|no-?gos?|forbidden|off[- ]limits|hard\s+rules|prohibited)")
_DN_LABEL = (r"(?:never\s+show|never|do\s+not\s+show|do\s+not|don'?t\s+show|don'?ts|don'?t|do-?nots?|avoid|"
             r"must\s+not\s+show|must\s+not|no-?gos?|forbidden|not\s+allowed)")
_DO_NOT_HEAD = re.compile(
    rf"^(?:things\s+to\s+|what\s+to\s+|please\s+)?{_DN_PHRASE}(?:\s+(?:on\s+screen|ever|list|please|rules|at\s+all|in\s+the\s+video))?"
    rf"\s*[.!?]?\s*$|^{_DN_LABEL}\s*:|^what\s+must\s+never\s+appear\b", re.I)
_DO_NOT_BARE = re.compile(rf"^\**\s*{_DN_LABEL}\s*:?\s*\**\s*:?\s*$", re.I)
_DO_NOT_INLINE = re.compile(rf"^\**\s*{_DN_LABEL}\s*\**\s*:\s*\**\s*(\S.*?)\s*$", re.I)
_LABEL = re.compile(r"^\**\s*(?:the\s+)?(logline|summary|story|meaning|setting|world|tone|themes?|symbolism|symbols?|"
                    r"references?|inspirations?|notes?|narrator|addressee)\s*\**\s*:\s*\**\s*(\S.*?)\s*$", re.I)
_PALETTE = re.compile(r"^\**(palette|colou?rs?)\**\s*[:\-]\s*\**\s*(.+)$", re.I)
#: do-not heading vocabulary (grammar rule 1): a heading made ONLY of these words, with at least one trigger, is a
#: do-not heading ('What I don't want', 'Avoid these', 'Things I never want to see'). A title with any other word
#: ('Never Let Me Go', 'The story: a night that never ends', 'Avoiding the obvious') is not.
_DN_TRIGGERS = frozenset({"never", "avoid", "dont", "donts", "nogo", "forbidden", "offlimits", "prohibited", "mustnot",
                          "banned", "taboo", "not"})
_DN_FILLERS = frozenset({"what", "things", "thing", "stuff", "i", "we", "you", "to", "want", "wanna", "see", "show",
                         "shown", "showing", "these", "this", "those", "ever", "please", "any", "at", "all", "on",
                         "screen", "in", "the", "video", "list", "rules", "rule", "hard", "appear", "appears", "should",
                         "must", "will", "would", "like", "of", "my", "our", "a", "an", "or", "and", "do", "be", "here",
                         "visuals", "images", "anything", "allowed", "seen", "include", "frame", "frames", "shots"})
_DN_JOIN = ((r"\bno[\s-]?gos?\b", "nogo"), (r"\boff[\s-]?limits\b", "offlimits"),
            (r"\b(?:do[\s-]?nots|don'?ts)\b", "donts"), (r"\b(?:do\s+not|don'?t)\b", "dont"),
            (r"\b(?:must\s+not|mustn'?t)\b", "mustnot"))

#: the template's own hint comments: cut as comments whatever the spacing before them (they never become claims)
TEMPLATE_HINTS = ("# hex (#", "# one per person on screen", "# the harness proposes voices", "# lead_backing:",
                  "# optional per-line fixes", "# rules in your own words", "# [{name: lanterns",
                  "# name, the lyric lines")

# ---- layer 3, rule 0: the interview's own text (a user who copies interview.md and answers under its questions)
#: (bold question title, block class, the harness's text after the title). A question line whose remainder is the
#: harness's text (or empty) is a heading for the answer below it; text after the harness's part is the answer.
_IV_QUESTIONS: tuple[tuple[str, str, str], ...] = (
    (r"What does this song mean to you\?", "story",
     r"One sentence \(the logline\), then as much as you like\.(?:\s*Credits found: .*?\)\.)?"),
    (r"Who sings to whom\?", "other", r"\d+ voice\(s\) were found\b.*?lane\):"),
    (r"Check the singer", "other", r"of \d+ low-confidence line\(s\).*?under `line_singers`\."),
    (r"The hooks", "other", r"repeat:\s*\S+ \(\d+x:.*?Should they look the same each time\?"),
    (r"The world", "setting", r":\s*where and when does the video take place\?(?:\s*Who are the characters "
                              r"\(look, age, costume\)\?)?(?:\s*Any visual references \(films, artists, photos\)\?)?"),
    (r"The mood arc", "other", r"the audio models hear\b.*?Where should it differ\?"),
    (r"How should each section feel and move\?", "other",
     r"Sections:.*?For each: feel, what it means, movement/choreography, camera\."),
    (r"The top moments", "other", r":\s*#\d+ \d+:\d.*?What should happen on screen at each\?"),
    (r"Colours", "palette", r":\s*which palette belongs to the song\b[^?]*\?(?:\s*Per-section colours\?)?"),
    (r"Never show", "do_not", r":\s*what must never appear on screen\?(?:\s*\(copied verbatim to every agent\))?"),
)
#: unbolded questions (the whole question is harness text)
_IV_PLAIN: tuple[tuple[str, str], ...] = (
    (r"The song is \*\*instrumental\*\* \(no lyrics were found\)\. What story or image should carry it\?", "story"),
    (r"No lyrics were found\. Are there words to show\?(?: \(pass `--lyrics`[^)]*\))?", "other"),
    (r"No separate voices were detected\. Is it one singer throughout\?(?: If not, who sings which lines\?)?", "other"),
)
_IV_LEAD = r"^[ \t]*(?:\d+[.)][ \t]+|[-*+][ \t]+)?"
_IV_Q_RE = [(re.compile(_IV_LEAD + r"\*\*(" + t + r")\*\*[ \t]*(.*)$"), cls, re.compile(tail))
            for t, cls, tail in _IV_QUESTIONS]
_IV_PLAIN_RE = [(re.compile(_IV_LEAD + "(" + t + r")[ \t]*(.*)$"), cls) for t, cls in _IV_PLAIN]
#: the interview's other lines (preamble, status, voice facts): never claims
_IV_ECHO = re.compile(
    r"^[ \t]*(?:The harness found the facts below\.|Current meaning status: \*\*\w+\*\*|Already answered in intent\.md:"
    r"|(?:[-*][ \t]+)?\*\*V\d+\*\*: \d+(?:\.\d+)? s, \d+ lines\b"
    r"|Which character is each voice\? Is any voice a narrator or announcer)")


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
        parts = [f"{k}: {v}" if v not in (None, "") else str(k) for k, v in x.items()]
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


def _first_sentence(s: str) -> str:
    m = _SENT.match(s.strip())
    first = (m.group(1) if m else s).strip()
    return first[:240]


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
    if ("#" in val or re.search(r":(\s|$)", val) or c0 in "@`%*&!?,]}" or val.startswith("- ")
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
            list_ok = False
            continue
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
        elif (t.startswith("- ") or t == "-") and list_ok:
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


def _chunks(lines: list[str], indent: int) -> list[tuple[int, int]]:
    """Split ``lines`` at the lines that hold a key at ``indent`` -> [(start, end)]; leading lines join the first."""
    starts = [k for k, ln in enumerate(lines)
              if ln.strip() and (len(ln) - len(ln.lstrip(" "))) == indent and _YKEY.match(ln[indent:])]
    if not starts:
        return [(0, len(lines))]
    starts[0] = 0
    return [(a, starts[k + 1] if k + 1 < len(starts) else len(lines)) for k, a in enumerate(starts)]


def _load_region(raw: list[str], warns: list[str]) -> tuple[dict[str, Any] | None, set[int]]:
    """Parse one template region. -> (merged mapping or None, raw line indices to read as free text instead)."""
    safe = _safe_lines(raw)
    d, ok = _yaml_load("\n".join(safe))
    if ok:
        if d is None:
            return {}, set()
        if isinstance(d, dict):
            return d, set()
        if any(ln.strip() for ln in safe):
            warns.append("intent.md: a template block is not a 'key: value' map; read as free text")
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
            for sa, sb in _chunks(body, ind):
                piece, ok2 = _yaml_load(f"{key}:\n" + "\n".join(body[sa:sb]))
                val = piece.get(key) if ok2 and isinstance(piece, dict) else None
                if ok2 and isinstance(val, dict):
                    sub.update(val)
                elif ok2 and isinstance(val, list):
                    subl.extend(val)
                elif ok2 and val is None:
                    continue
                else:
                    first = next((x.strip() for x in body[sa:sb] if x.strip()), "")
                    warns.append(f"intent.md: the template entry '{key}: {first.split(':', 1)[0][:20]}' does not parse "
                                 "as YAML; its lines were read as free text (check quotes and brackets)")
                    fallback.update(range(a_key + 1 + sa, a_key + 1 + sb))
            if sub or subl:
                merged[key] = sub if sub else subl
            continue
        warns.append(f"intent.md: the template key '{key or '?'}' does not parse as YAML; its lines were read as free "
                     "text (check quotes and brackets)")
        fallback.update(range(a, b))
    return merged, fallback


def _safe_lines(raw: list[str]) -> list[str]:
    """``tolerant_yaml_line`` over a region, except inside a block scalar (``key: |`` / ``key: >``), where every
    line is text as typed (a '#' there is not a comment)."""
    out: list[str] = []
    block_indent: int | None = None
    for ln in raw:
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
        out["warnings"].append("intent.md: unknown top-level key(s) in the YAML template ignored: " + ", ".join(unknown[:6]))
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
    for k in ("symbolism", "notes"):
        vals = _texts(d.get(k))
        if vals and not out[k]:
            out[k] = vals
    d = dict(d)
    for k in ("perspective", "characters", "line_singers", "sections"):
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
    """A map key (``characters``, ``line_singers``, ``sections``, ``perspective``) answered with a list of bullets.
    A ``- key: value`` item is that map entry; a text item is read by the free-text rule of the key (character line,
    per-line singers, section notes). An item that matches nothing is kept in ``notes`` with a warning."""
    merged: dict[str, Any] = {}
    for it in items:
        if it is None:
            continue
        if isinstance(it, dict) and (key == "perspective" or all(isinstance(v, dict) for v in it.values())
                                     or key == "line_singers"
                                     or (key == "characters" and all(re.fullmatch(r"C[1-9]\d*", str(k).strip())
                                                                     for k in it))):
            merged.update(it)
            continue
        text = _item_text(it) or ""
        hit = False
        if key == "characters":
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


# ============================================================================================ layer 3: free text
def _is_do_not_heading(h: str) -> bool:
    """``h``: the lower-cased heading text. A whole do-not phrase, or only do-not vocabulary (grammar rule 1)."""
    if _DO_NOT_HEAD.match(h):
        return True
    s = h
    for pat, rep in _DN_JOIN:
        s = re.sub(pat, rep, s)
    toks = re.findall(r"[a-z]+", s.replace("'", ""))
    return (0 < len(toks) <= 8 and any(t in _DN_TRIGGERS for t in toks)
            and all(t in _DN_TRIGGERS or t in _DN_FILLERS for t in toks))


def _head_class(text: str, level: int) -> str:
    raw = re.sub(r"^\d+[.)]\s*", "", text.strip().strip("*_ ").replace("’", "'")).strip("*_ ")
    iv = _iv_class(raw)
    if iv:
        return iv  # an interview question used as a heading (rule 0)
    h = raw.lower()
    if _is_do_not_heading(h):
        return "do_not"
    if re.fullmatch(r"open questions", h):
        return "harness"  # the interview's open questions (copied): the harness's text, not answers
    if re.fullmatch(r"(?:the\s+|my\s+)?(?:colou?r\s+)?(?:palette|colou?rs?)\s*[:.]?", h):
        return "palette"
    if re.search(r"\b(story|meaning|about|means|summary|logline)\b", h):
        return "story"
    if re.search(r"\b(setting|world|place|where)\b", h):
        return "setting"
    if re.search(r"\btone\b", h):
        return "tone"
    if re.search(r"\bthemes?\b", h):
        return "themes"
    if re.search(r"\b(symbols?|symbolism)\b", h):
        return "symbolism"
    if re.search(r"\bmotifs?\b", h):
        return "motifs"
    if re.search(r"\b(references?|inspirations?)\b", h):
        return "references"
    return "title" if level == 1 else "other"


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
            continue  # empty, or a comment
        key = re.sub(r"\s+", " ", m.group(1).strip().lower())
        key = re.sub(r"^(s\d{2,})$", lambda mm: mm.group(1).upper(), key)
        out.append({"key": key, "t0": None, "t1": None, "occurrence_label": None, "feel": txt, "meaning": None,
                    "emotion": None, "movement": None, "camera": None, "palette": [], "palette_unparsed": [],
                    "characters": [], "do_not": [], "origin": "text"})
    return out


def _interview_echo(pairs: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Rule 0: the interview's own text in intent.md (the user copied interview.md and answered under its questions).
    A question line becomes a heading (``## <title>``, see ``_IV_QUESTIONS`` for its block class) and the text after
    the harness's part of it is the first line of the answer. The preamble, status and voice-fact lines are dropped.
    A question line whose remainder is not the harness's text is the user's own label line and is left alone
    (``9. **Never show**: blood`` is the rule 'blood')."""
    out: list[tuple[int, str]] = []
    for i, ln in pairs:
        if _IV_ECHO.match(ln):
            out.append((i, ""))
            continue
        head: tuple[str, str] | None = None
        for rx, cls, tail in _IV_Q_RE:
            m = rx.match(ln)
            if not m:
                continue
            rest = m.group(2).strip()
            tm = tail.match(rest)
            if tm:
                head = (m.group(1), rest[tm.end():].strip())
            elif not rest and cls != "do_not":  # a bare '**Never show**' is the label of rule 3
                head = (m.group(1), "")
            break
        if head is None:
            for rx, _cls in _IV_PLAIN_RE:
                m = rx.match(ln)
                if m:
                    head = (m.group(1), m.group(2).strip())
                    break
        if head is None:
            out.append((i, ln))
            continue
        out.append((i, "## " + head[0]))
        if head[1]:
            out.append((i, head[1]))
    return out


_IV_CLASS = {t: cls for t, cls, _tail in _IV_QUESTIONS} | {t: cls for t, cls in _IV_PLAIN}


def _iv_class(title: str) -> str | None:
    for pat, cls in _IV_CLASS.items():
        if re.fullmatch(pat, title, re.I):
            return cls
    return None


def _logical_lines(pairs: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join an indented non-bullet line to the bullet above it (a wrapped bullet)."""
    out: list[tuple[int, str]] = []
    prev = ""
    for i, ln in pairs:
        if (out and ln[:1] in (" ", "\t") and ln.strip() and not _BULLET.match(ln) and _BULLET.match(out[-1][1])
                and prev.strip()):
            out[-1] = (out[-1][0], out[-1][1].rstrip() + " " + ln.strip())
            prev = ln
            continue
        out.append((i, ln.rstrip()))
        prev = ln
    return out


def _unbold(s: str) -> str:
    s = s.strip()
    if s.endswith("**") and s.count("**") % 2 == 1:
        s = s[:-2].strip()
    return s


def _parse_text(lines: list[str], no_prose: set[int], out: dict[str, Any]) -> None:
    if not any(ln.strip() for ln in lines):
        return
    out["form"] = "text" if out["form"] == "none" else ("yaml+text" if out["form"] == "yaml" else out["form"])
    fill: dict[str, Any] = {}
    rules: list[str] = []
    pre_prose: list[str] = []
    notes: list[str] = []
    story_seen = False
    blk: dict[str, Any] = {"cls": "title", "prose": [], "bullets": []}

    def commit(b: dict[str, Any]) -> None:
        nonlocal story_seen
        prose = " ".join(b["prose"]).strip()
        bl = [x for x in b["bullets"] if x]
        cls = b["cls"]
        if cls == "story":
            text = " ".join([prose] + bl).strip()
            if text:
                story_seen = True
                fill.setdefault("summary", text[:2000])
                fill.setdefault("logline", _first_sentence(text))
        elif cls in ("setting", "tone"):
            v = prose or "; ".join(bl)
            if v:
                fill.setdefault(cls, v)
        elif cls in ("themes", "symbolism", "references"):
            v = bl or ([prose] if prose else [])
            if v:
                fill.setdefault(cls, v)
        elif cls == "title":
            if prose:
                pre_prose.append(prose)
            notes.extend(bl)
        elif cls == "palette":
            items = [x for v in [prose] + bl for x in re.split(r"[,;]|\s+and\s+", v) if x.strip()]
            if items and not out["palette"] and not out["palette_unparsed"]:
                out["palette"], out["palette_names"], out["palette_unparsed"] = parse_palette(items)
        elif cls == "harness":  # the interview's open questions: its bullets are the harness's, prose is the user's
            if prose:
                notes.append(prose)
        else:
            if prose:
                notes.append(prose)
            notes.extend(bl)

    dn_list = False  # inside the list a bare do-not label opened
    dn_started = False
    dn_indent = -1  # the indent of a bare label that is itself a bullet (-1: not a bullet)
    dn_nested = True  # its list is the bullets indented under it (else: the bullets at its own level)
    for idx, raw in _logical_lines(_interview_echo(list(enumerate(lines)))):
        t = raw.strip()
        if not t:
            if dn_list and dn_started:
                dn_list = False
            continue
        hm = _HEAD.match(raw)
        if hm:
            commit(blk)
            blk = {"cls": _head_class(hm.group(2), len(hm.group(1))), "prose": [], "bullets": []}
            dn_list = False
            continue
        is_bullet = bool(_BULLET.match(raw))
        indent = len(raw) - len(raw.lstrip())
        body = _BULLET.sub("", t).strip() if is_bullet else t
        norm = body.replace("’", "'")
        if blk["cls"] == "do_not":
            rules.append(body)
            continue
        if blk["cls"] == "harness":  # the copied open questions: only the user's own prose under them is kept
            if not is_bullet:
                blk["prose"].append(body)
            continue
        if dn_list:
            if not dn_started and is_bullet and dn_indent >= 0:
                dn_nested = indent > dn_indent
            level_ok = indent > dn_indent if dn_nested else indent == dn_indent
            if is_bullet and level_ok and not _CHAR.match(body) and not _LINE_SINGER.search(body):
                rules.append(body)
                dn_started = True
                continue
            dn_list = False
        im = _DO_NOT_INLINE.match(norm)
        if im and not im.group(1).lower().startswith("what must never appear"):
            rules.append(_unbold(body[im.start(1):]))
            continue
        if _DO_NOT_BARE.match(norm) or im:
            dn_list, dn_started, dn_indent, dn_nested = True, False, (indent if is_bullet else -1), True
            continue
        lm = _LABEL.match(body)
        if lm:
            _label(lm.group(1).lower(), _unbold(lm.group(2)), fill, out)
            continue
        pm = _PALETTE.match(body)
        if pm:
            if not out["palette"] and not out["palette_unparsed"]:
                items = re.split(r"[,;]|\s+and\s+", _unbold(pm.group(2)))
                out["palette"], out["palette_names"], out["palette_unparsed"] = parse_palette(items)
            continue
        if _LINE_SINGER.search(body):
            for m in _LINE_SINGER.finditer(body):
                out["line_singers"].setdefault(m.group(1), split_singers(m.group(2)))
            continue
        mc = _CHAR.match(body)
        if mc:
            cid, rest = mc.group(1), mc.group(2).strip()
            if not rest.startswith("{") and cid not in out["characters"]:
                out["characters"][cid] = _char_from_text(rest)
            continue
        notes_here = _section_notes(body)
        if notes_here:
            out["sections"].extend(notes_here)
            continue
        if idx in no_prose or re.fullmatch(r"[\w.\- ]+:", body) or re.fullmatch(r"S\d{2,}:?", body):
            continue  # a template line that did not parse (already warned), or an empty 'key:'
        if blk["cls"] == "motifs" and is_bullet:
            out["motifs"].append(_motif_from_text(body))
            continue
        (blk["bullets"] if is_bullet else blk["prose"]).append(body)
    commit(blk)
    if not story_seen and pre_prose:
        text = " ".join(pre_prose)
        fill.setdefault("summary", text[:2000])
        fill.setdefault("logline", _first_sentence(text))
    elif pre_prose:
        notes = pre_prose + notes
    for k in ("summary", "logline", "setting", "tone"):
        if fill.get(k) and not out.get(k):
            out[k] = fill[k]
    for k in ("themes", "symbolism", "references"):
        if fill.get(k) and not out.get(k):
            out[k] = [x for x in fill[k] if x]
    for k in ("narrator", "addressee"):
        if fill.get(k) and not out["perspective"][k]:
            out["perspective"][k] = fill[k]
    for x in rules:
        if x and x not in out["do_not"]:
            out["do_not"].append(x)
    for x in (fill.get("notes") or []) + notes:
        if x and x not in out["notes"]:
            out["notes"].append(x)


def _label(word: str, val: str, fill: dict[str, Any], out: dict[str, Any]) -> None:
    if word in ("logline",):
        fill.setdefault("logline", val)
    elif word in ("summary", "story", "meaning"):
        fill.setdefault("summary", val)
        fill.setdefault("logline", _first_sentence(val))
    elif word in ("setting", "world"):
        fill.setdefault("setting", val)
    elif word == "tone":
        fill.setdefault("tone", val)
    elif word.startswith("theme"):
        fill.setdefault("themes", [s.strip() for s in re.split(r"[,;]", val) if s.strip()])
    elif word.startswith("symbol"):
        fill.setdefault("symbolism", [val])
    elif word.startswith(("reference", "inspiration")):
        fill.setdefault("references", [s.strip() for s in re.split(r"[;]", val) if s.strip()])
    elif word.startswith("note"):
        fill.setdefault("notes", []).append(val)
    elif word in ("narrator", "addressee"):
        fill.setdefault(word, val)


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
    free = ["" if i in consumed else ln for i, ln in enumerate(lines)]
    no_prose: set[int] = set()
    for a, b in regions:
        raw = lines[a:b]
        d, fallback = _load_region(raw, out["warnings"])
        if d:
            _apply_yaml(d, out)
        elif d is not None and out["form"] == "none":
            out["form"] = "yaml"  # an empty template region is still the template
        for k in fallback:
            free[a + k] = _cut_comment(raw[k])
            no_prose.add(a + k)
    _parse_text(free, no_prose, out)
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
