# ruff: noqa: E501  (long catalogue tables / docstrings)
"""ID formats and links of the mv-harness output contract (PLAN §4.3).

Frozen at contract v1. Stdlib only. The JS loader (lib/mvh.js) and the Python loader
(lib/mvh_load.py) must accept exactly the strings these regexes accept.

Numbering rules
---------------
* Every numbered ID is 1-based and zero-padded to its minimum width; more digits are allowed
  when the count overflows (``S100`` after ``S99``). IDs are assigned in time order (``t`` ascending,
  ties by file order), except voices, characters and motifs, which are assigned in order of first appearance.
* ``E000`` is reserved for the synthesised 5-6-7-8 lead-in before the first eight-count.
* Bars are integers: 1-based; ``0`` is the pickup (anacrusis) bar when there is one.
  ``beat_in_bar`` is 1..N. ``beat_index`` is 0-based and equals the item's position in ``events/beats.json``.
* Word IDs are ``<line_id>.<k>`` with k 1-based within the line, zero-padded to 2 digits (``L001.03``).
* Items that have no ID of their own are referenced with a *reference key*: ``beat:<beat_index>`` or ``bar:<bar>``.
"""
from __future__ import annotations

import re
from typing import NamedTuple

__all__ = [
    "ID_KINDS", "IdKind", "PATTERNS", "is_id", "kind_of", "make_id", "parse_id", "id_number",
    "word_id", "split_word_id", "ref_key", "parse_ref_key", "occurrence_label", "repeat_group_label",
    "SLUG_RE", "CHANNEL_ID_RE", "EVENTS_NAME_RE", "STEM_NAMES", "DRUM_SUBSTEMS", "PITCHED_SOURCES",
    "STAGE_NAME_RE", "SEMVER_RE", "SHA256_RE", "slugify",
]


class IdKind(NamedTuple):
    kind: str          # machine name
    prefix: str        # literal prefix
    width: int         # minimum digit count (zero padding)
    regex: str         # full-match regex
    entity: str        # human description
    file: str          # canonical file that defines the IDs


def _num(prefix: str, width: int) -> str:
    # zero-padded to `width`, more digits allowed; never all zeros except where documented
    return rf"^{prefix}\d{{{width},}}$"


ID_KINDS: dict[str, IdKind] = {k.kind: k for k in [
    IdKind("section", "S", 2, _num("S", 2), "Section", "events/sections.json"),
    IdKind("phrase", "P", 2, _num("P", 2), "Phrase (4/8/16 bars)", "events/phrases.json"),
    IdKind("eight", "E", 3, _num("E", 3), "Eight-count (E000 = synthesised lead-in)", "events/counts.json"),
    IdKind("groove", "G", 2, _num("G", 2), "Groove (per-bar pattern cluster)", "meta/grooves.json"),
    IdKind("line", "L", 3, _num("L", 3), "Lyric line, in sung order", "lyrics/lyrics.json"),
    IdKind("word", "L", 3, r"^L\d{3,}\.\d{2,}$", "Lyric word (line_id.k, k 1-based)", "lyrics/lyrics.json"),
    IdKind("voice", "V", 1, r"^V[1-9]\d*$", "Voice cluster (one singing or rapping voice)", "meta/voices.json"),
    IdKind("character", "C", 1, r"^C[1-9]\d*$", "Character (from intent.md or meaning)", "meaning/meaning.json"),
    IdKind("motif", "M", 1, r"^M[1-9]\d*$", "Motif", "meaning/meaning.json"),
    IdKind("cue", "Q", 4, _num("Q", 4), "Cue", "events/cues.json"),
    # IDs added by the contract (not named in PLAN §4.3) for items that cues and meaning cite:
    IdKind("edm_role", "R", 2, _num("R", 2), "EDM-role segment (build, drop, breakdown)", "events/edm_roles.json"),
    IdKind("hit_point", "H", 3, _num("H", 3), "Choreography hit point", "events/hit_points.json"),
    IdKind("hold", "O", 3, _num("O", 3), "Choreography hold", "events/holds.json"),
    IdKind("impact", "I", 3, _num("I", 3), "Dynamics impact", "events/impacts.json"),
    IdKind("stop", "X", 3, _num("X", 3), "Dynamics stop (sudden cut)", "events/stops.json"),
    IdKind("silence", "Z", 3, _num("Z", 3), "Dynamics silence", "events/silences.json"),
    IdKind("decay_tail", "Y", 3, _num("Y", 3), "Dynamics decay tail", "events/decay_tails.json"),
    IdKind("vocal_phrase", "VP", 3, _num("VP", 3), "Vocal phrase", "events/vocal_phrases.json"),
    IdKind("text_group", "T", 2, _num("T", 2), "Lyric lines with identical normalised text", "lyrics/lyrics.json"),
    IdKind("line_group", "LG", 2, _num("LG", 2), "Lyric repeat group (near-identical lines / hooks)", "lyrics/lyrics.json"),
    IdKind("repeat_group", "", 1, r"^[A-Z]{1,2}$", "Section repeat group (A, B, ..., Z, AA, AB, ...)", "events/sections.json"),
]}

PATTERNS: dict[str, re.Pattern[str]] = {k: re.compile(v.regex) for k, v in ID_KINDS.items()}

# Kinds whose numbering is not "prefix + digits" are excluded from make_id/parse_id.
_NUMBERED = [k for k in ID_KINDS if k not in ("word", "repeat_group")]
# Longest prefix first so "VP001" is not read as a voice and "LG01" not as a line.
_PREFIX_ORDER = sorted(_NUMBERED, key=lambda k: -len(ID_KINDS[k].prefix))

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
STAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
#: curve channel ids: dotted, lower-case namespace first; later parts may hold digits or a voice id (vocal.mouth_open.V2)
CHANNEL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_]+)+$")
#: events names: dotted lower-case (notes.bass, hits.kick, beats)
EVENTS_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

#: stem names (stems/<name>.flac); drum sub-stems live at stems/drums/<sub>.flac and are named drums_<sub>
STEM_NAMES = ("vocals", "lead_vocals", "backing_vocals", "drums", "bass", "guitar", "piano", "other", "instrumental")
DRUM_SUBSTEMS = ("kick", "snare", "toms", "hihat", "ride", "crash")
#: sources that get note events (events/notes.<src>.json)
PITCHED_SOURCES = ("bass", "piano", "guitar", "other", "vocals")


def is_id(kind: str, s: object) -> bool:
    """True when ``s`` is a valid ID of ``kind`` (see ID_KINDS)."""
    return isinstance(s, str) and PATTERNS[kind].match(s) is not None


def kind_of(s: str) -> str | None:
    """Return the ID kind of ``s`` or None. Word IDs win over line IDs; repeat groups are letters only."""
    if not isinstance(s, str):
        return None
    if PATTERNS["word"].match(s):
        return "word"
    for k in _PREFIX_ORDER:
        if PATTERNS[k].match(s):
            return k
    if PATTERNS["repeat_group"].match(s):
        return "repeat_group"
    return None


def make_id(kind: str, n: int) -> str:
    """make_id('section', 3) -> 'S03'; make_id('cue', 12) -> 'Q0012'; make_id('voice', 2) -> 'V2'.

    ``n`` is 1-based (0 is allowed only for the E000 lead-in)."""
    if kind == "repeat_group":
        return repeat_group_label(n)
    if kind not in _NUMBERED:
        raise ValueError(f"make_id does not build {kind!r} ids")
    k = ID_KINDS[kind]
    if n < 0 or (n == 0 and kind != "eight"):
        raise ValueError(f"{kind} ids are 1-based (got {n})")
    s = f"{k.prefix}{n:0{k.width}d}"
    assert PATTERNS[kind].match(s), s
    return s


def parse_id(s: str) -> tuple[str, int]:
    """'S03' -> ('section', 3). Raises ValueError for words, repeat groups and invalid strings."""
    k = kind_of(s)
    if k is None or k in ("word", "repeat_group"):
        raise ValueError(f"not a numbered id: {s!r}")
    return k, int(s[len(ID_KINDS[k].prefix):])


def id_number(s: str) -> int:
    return parse_id(s)[1]


def word_id(line_id: str, k: int) -> str:
    """word_id('L001', 3) -> 'L001.03' (k is 1-based within the line)."""
    if not is_id("line", line_id) or k < 1:
        raise ValueError((line_id, k))
    return f"{line_id}.{k:02d}"


def split_word_id(wid: str) -> tuple[str, int]:
    """'L001.03' -> ('L001', 3)."""
    if not is_id("word", wid):
        raise ValueError(wid)
    line, k = wid.split(".")
    return line, int(k)


def ref_key(kind: str, value: int) -> str:
    """Reference key for items without an ID: ref_key('beat', 12) -> 'beat:12', ref_key('bar', 5) -> 'bar:5'."""
    if kind not in ("beat", "bar") or int(value) != value:
        raise ValueError((kind, value))
    return f"{kind}:{int(value)}"


_REF_RE = re.compile(r"^(beat|bar):(-?\d+)$")


def parse_ref_key(s: str) -> tuple[str, int]:
    m = _REF_RE.match(s)
    if not m:
        raise ValueError(s)
    return m.group(1), int(m.group(2))


def occurrence_label(label: str, occurrence: int) -> str:
    """occurrence_label('chorus', 2) -> 'chorus#2' (occurrence is 1-based per label)."""
    return f"{label}#{occurrence}"


def repeat_group_label(n: int) -> str:
    """1 -> 'A', 26 -> 'Z', 27 -> 'AA', 28 -> 'AB' (bijective base 26, at most two letters)."""
    if not 1 <= n <= 26 + 26 * 26:
        raise ValueError(n)
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def slugify(name: str) -> str:
    """Folder slug: lower-case ASCII letters, digits and single hyphens (used for out/<slug>/)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "song")[:64].rstrip("-")
