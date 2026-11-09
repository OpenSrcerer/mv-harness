"""Lyric text: reading user files (encoding sniffing), parsing LRC / A2 / SRT / VTT / TXT / Lyricsfile, speaker
labels, backing parentheses, explicit repeat markers, normalisation for alignment and matching.

Nothing here logs or prints lyric text. Parsed lines are plain dicts:

    {"text": str, "t": float | None, "end": float | None, "words": [{"text": str, "t": float | None}] | None,
     "speaker": str | None, "backing": bool, "origin": "source"}

``t``/``end`` are source line times (seconds, source clock), ``words[].t`` source word times when the source
has word sync (A2 / VTT inline / Lyricsfile words).
"""

from __future__ import annotations

import contextvars
import functools
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable

__all__ = [
    "read_text_file", "parse_any", "parse_lrc", "parse_srt", "parse_vtt", "parse_txt", "parse_lyricsfile",
    "norm_words", "line_key", "display_words", "mms_word_tokens", "TokenMaker", "SECTION_WORDS",
]

SECTION_WORDS = ("verse", "chorus", "pre-chorus", "prechorus", "post-chorus", "bridge", "intro", "outro", "hook",
                 "refrain", "interlude", "breakdown", "instrumental", "drop", "build", "solo", "tag", "coda",
                 "spoken", "skit", "part", "section", "repeat")
_TS = r"(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)"
_LRC_TAG_RE = re.compile(r"^\[" + _TS + r"\]")
_LRC_META_RE = re.compile(r"^\[([a-zA-Z#]+)\s*:(.*)\]\s*$")
_WORD_TAG_RE = re.compile(r"<" + _TS + r">")
_REPEAT_RE = re.compile(r"\s*[\(\[]?\s*(?:x\s*(\d{1,2})|(\d{1,2})\s*x|×\s*(\d{1,2})|(\d{1,2})\s*×)\s*[\)\]]?\s*$", re.I)
_LABEL_RE = re.compile(r"^((?:[A-Z][\w'.\-]*|[A-Z]{1,4}\d?)(?:\s*(?:&|and|\+|,)?\s*[A-Z][\w'.\-]*){0,3})\s*:\s+(\S.*)$")
_ENH_VOICE_RE = re.compile(r"^(v\d{1,2}|[MFD])\s*:\s*(\S.*)$")
_HEADER_RE = re.compile(r"^\s*[\[\{]([^\]\}]{1,60})[\]\}]\s*$")
_META_KEYS = {"ar", "ti", "al", "au", "by", "length", "offset", "re", "ve", "#", "id", "la"}
_INSTR_WORDS = {"solo", "break", "guitar", "sax", "saxophone", "drums", "drum", "piano", "keys", "bass", "instrumental",
                "interlude", "breakdown", "fill", "riff", "strings", "synth", "horns", "trumpet", "violin", "silence",
                "music", "beat", "drop", "build", "buildup", "fade", "end", "start", "applause", "laughter", "noise"}
_LABEL_STOP = {"oh", "ooh", "yeah", "hey", "no", "baby", "now", "and", "but", "so", "well", "listen", "look", "chorus",
               "verse", "bridge", "hook", "intro", "outro", "note", "warning", "remember", "uh", "ah", "yo", "boy", "girl"}


# ------------------------------------------------------------------------------------------ reading
def read_text_file(path: Path | str) -> tuple[str, str | None]:
    """Read a lyrics file: UTF-8 BOM / UTF-16 BOM / UTF-16 without BOM (many NULs) / UTF-8 / cp1252.
    Returns (text, warning or None). Never raises on decoding."""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), None
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace"), None
    if len(raw) >= 4 and raw.count(b"\x00") > len(raw) // 4:
        enc = "utf-16-le" if raw[1:2] == b"\x00" else "utf-16-be"
        return raw.decode(enc, errors="replace"), f"lyrics file decoded as {enc} (no BOM)"
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "lyrics file is not UTF-8: decoded as cp1252"


def _ts(m_min: str, m_sec: str) -> float:
    sec = m_sec.replace(":", ".")
    return int(m_min) * 60 + float(sec)


# ------------------------------------------------------------------------------------------ labels / backing
_LABELLED: contextvars.ContextVar[bool] = contextvars.ContextVar("mvh_lyrics_labelled", default=True)
# lone 'Name:' marker lines accepted for the file being parsed (lower-cased names; see _scan_labels)
_MARKERS: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar("mvh_lyrics_markers", default=frozenset())
_STRIP_PREFIX = re.compile(r"^\s*(?:-\s*)?(?:text:\s*[\"']?)?(?:\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]\s*)*(?:<[^>]*>\s*)*")


def _file_labelled(text: str) -> bool:
    """True when inline 'Name: ...' prefixes and bare '[Name]' headers of this lyric file are speaker labels
    (see _scan_labels)."""
    return _scan_labels(text)[0]


def _scan_labels(text: str) -> tuple[bool, frozenset[str]]:
    """(labelled, accepted lone markers) for one lyric file.

    * explicit markers make a file labelled at once: a '[Verse 1: Newton]' / 'Verse 1: Newton' /
      '[Verse 1 - Newton]' / 'Newton (Verse 1):' section header that names a speaker, or a '[Newton:]' header;
    * a 'Newton:' line on its own is a speaker marker only as a set (M5-D47, M5-D54): >= 2 distinct names, and
      either one of them recurs with DIFFERENT text after it, or every one is a strict name (capitalised words
      and name particles, no pronoun / verb) in a file that is not written in Title Case. A sung line that ends
      in a colon ('I said to John:', 'Tell Me Why:') therefore stays a lyric;
    * an inline 'Name: ...' label must recur with DIFFERENT text after it (a chorus line written out twice that
      starts with 'Time:' is a repeated lyric, not a change of speaker);
    * bare '[Name]' headers need >= 2 distinct names, one of them recurring.
    A one-off 'Time: ...' in an unlabelled file stays sung text."""
    inline: dict[str, set[str]] = {}
    inline_n: dict[str, int] = {}
    bare: dict[str, int] = {}
    lone: dict[str, set[str]] = {}
    lone_n: dict[str, int] = {}
    lone_names: dict[str, str] = {}
    explicit = False
    rows = [_WORD_TAG_ANY.sub("", _STRIP_PREFIX.sub("", raw)).strip().strip("\"'") for raw in text.splitlines()]
    rows = [r for r in rows if r]
    lyric_rows: list[str] = []
    for i, s in enumerate(rows):
        name = _lone_marker(s)
        if name is not None:
            key = name.lower()
            nxt = next((line_key(r) for r in rows[i + 1:] if _lone_marker(r) is None), "")
            lone.setdefault(key, set()).add(nxt)
            lone_n[key] = lone_n.get(key, 0) + 1
            lone_names[key] = name
            continue
        is_h, sp, sec, _rep = _header(s, bare=True)
        if is_h:
            if sp:
                if sec is not None or s.rstrip("]}) ").endswith(":"):
                    explicit = True
                    continue
                key = sp.strip().lower()
                bare[key] = bare.get(key, 0) + 1
            continue
        lyric_rows.append(s)
        m = _LABEL_RE.match(s)
        if m:
            lab = m.group(1).strip().lower()
            if _label_ok(lab):
                inline.setdefault(lab, set()).add(line_key(m.group(2)))
                inline_n[lab] = inline_n.get(lab, 0) + 1
    markers: frozenset[str] = frozenset()
    if len(lone) >= 2:
        # R5-1 (W3): only candidates that look like names are ever markers (no pronoun / verb; in a Title Case file a
        # multi-word 'She Said:' is a lyric). One recurring candidate no longer makes the whole set markers.
        tc = _title_case(lyric_rows)
        ok = {k for k, n in lone_names.items() if _strict_name(n) and not (tc and len(n.split()) > 1)}
        recurring = any(lone_n[k] >= 2 and len(lone[k]) >= 2 for k in ok)
        strict = len(ok) == len(lone) and not tc
        if len(ok) >= 2 and (recurring or strict):
            markers = frozenset(ok)
    if explicit or markers:
        return True, markers
    if any(inline_n[k] >= 2 and len(v) >= 2 for k, v in inline.items()):
        return True, markers
    return len(bare) >= 2 and any(n >= 2 for n in bare.values()), markers


_WORD_TAG_ANY = re.compile(r"<[^>]*>")
_NAME_PARTICLES = {"de", "da", "del", "della", "der", "den", "van", "von", "the", "of", "la", "le", "du", "di", "bin",
                   "al", "el", "y", "&", "and", "+"}
_NOT_NAME = {"i", "me", "my", "you", "your", "we", "us", "our", "he", "him", "his", "she", "her", "it", "its", "they",
             "them", "their", "this", "that", "these", "those", "what", "why", "how", "when", "where", "who", "let",
             "go", "tell", "said", "say", "says", "here", "there", "come", "take", "give", "get", "got", "never",
             "always", "is", "are", "was", "were", "be", "do", "don't", "can't", "won't", "not", "to", "in", "on", "at",
             "a", "an", "if", "for", "with", "again", "down", "up", "like", "love", "know", "want", "need", "see",
             "look", "listen", "hear", "feel", "make", "keep", "one", "all", "every", "some"}


def _strict_name(name: str) -> bool:
    """A performer name rather than a lyric fragment: capitalised words or name particles, no pronoun or verb."""
    words = [w.strip(".,!?") for w in name.split()]
    if not words:
        return False
    for w in words:
        low = w.lower()
        if low in _NOT_NAME:
            return False
        if not (w[:1].isupper() or low in _NAME_PARTICLES or (w[:1].islower() and any(c.isupper() for c in w[1:]))):
            return False
    return True


def _title_case(rows: list[str]) -> bool:
    """A file written in Title Case (every word capitalised on most lines of >= 3 words)."""
    n = tc = 0
    for r in rows:
        ws = [w for w in r.split() if w[:1].isalpha()]
        if len(ws) < 3:
            continue
        n += 1
        tc += all(w[:1].isupper() for w in ws)
    return n > 0 and tc / n > 0.5


def _lone_marker(text: str) -> str | None:
    """The name of a 'Bill Nye:' / 'Bill Nye the Science Guy:' line on its own (a speaker-marker CANDIDATE; the
    file decides, see _scan_labels). None for a section header or anything else."""
    s = _strip_deco(text)
    if not s.endswith(":") or s.startswith(("(", "[", "{")):
        return None
    head = s[:-1].strip()
    if not head or ":" in head or _PLAIN_SEC_RE.match(head) or _section_word(head) is not None:
        return None
    if _REPEAT_RE.search(head) or head.lower() in _META_KEYS or "(" in head:
        return None
    return head if _is_name(head, 5) else None


def _strip_deco(text: str) -> str:
    """'*Chorus*' / '_Chorus_' / '**Bill Nye:**' -> the text without markdown emphasis."""
    s = text.strip()
    while len(s) > 2 and s[0] == s[-1] and s[0] in "*_":
        s = s[1:-1].strip()
    return s


def _label_ok(lab: str) -> bool:
    low = lab.strip().lower()
    return (len(low) <= 30 and low not in _LABEL_STOP and low not in _META_KEYS and not low.startswith(SECTION_WORDS)
            and _section_word(low) is None)


def _labels_scoped(fn):
    @functools.wraps(fn)
    def wrapper(text, *a, **kw):
        labelled, markers = _scan_labels(text)
        tok = _LABELLED.set(labelled)
        tok2 = _MARKERS.set(markers)
        try:
            return fn(text, *a, **kw)
        finally:
            _MARKERS.reset(tok2)
            _LABELLED.reset(tok)
    return wrapper


def _label_split(text: str) -> tuple[str | None, str]:
    """'Newton: I'm the ...' -> ('Newton', "I'm the ..."); enhanced LRC 'v1: ...' / 'M: ...' too. Plain 'Name:'
    prefixes count only in a labelled file (see _file_labelled)."""
    m = _ENH_VOICE_RE.match(text)
    if m:
        return m.group(1), m.group(2).strip()
    if not _LABELLED.get():
        return None, text
    m = _LABEL_RE.match(text)
    if m:
        lab = m.group(1).strip()
        if _label_ok(lab):
            return lab, m.group(2).strip()
    return None, text


_SEC_SET = frozenset(SECTION_WORDS)
_PREPOST = {"prechorus": "pre-chorus", "postchorus": "post-chorus", "prehook": "pre-hook", "posthook": "post-hook"}
# a whole unbracketed line that is a section header: 'Verse 1', 'CHORUS', 'Pre Chorus', 'Final Chorus', 'Hook 2'
_PLAIN_SEC_RE = re.compile(
    r"^(?:(?:final|last|first|second|third|fourth|fifth|rap|double|half|extended|spoken|end|repeat(?:\s+the)?|"
    r"\d{1,2}(?:st|nd|rd|th))\s+)?"
    r"(pre[\s-]?chorus|post[\s-]?chorus|pre[\s-]?hook|verse|chorus|bridge|hook|intro|outro|refrain|interlude|breakdown|"
    r"coda|instrumental)(?:\s*(?:\d{1,2}|[ivx]{1,4}|one|two|three|four|five))?"
    r"(?:\s*[\(\[]?\s*(?:repeat|repeated|again|reprise)\s*[\)\]]?)?$", re.I)
_PAREN_SEC_RE = re.compile(r"^(.+?)\s*[\(\[]([^()\[\]]+)[\)\]]$")
_DASH_RE = re.compile(r"\s[-–—]\s")
_NAME_WORD_RE = re.compile(r"^[\w'.\-&+,]+$")


def _section_word(text: str) -> str | None:
    """The section word of a header when ANY of its words is one ('[Final Chorus]', '[Rap Verse]', '[Pre Chorus]',
    '[Verse1]'); 'pre chorus' / 'post chorus' are joined. None for a name."""
    toks = [t.strip("-") for t in re.split(r"[^a-z\-]+", text.lower().replace("–", "-")) if t.strip("-")]
    for i, t in enumerate(toks):
        if t in ("pre", "post") and i + 1 < len(toks) and toks[i + 1] in ("chorus", "hook"):
            return f"{t}-{toks[i + 1]}"
        if t in _PREPOST:
            return _PREPOST[t]
        if t in _SEC_SET:
            return t
    return None


def _is_name(text: str, max_words: int = 4) -> bool:
    """A short capitalised performer name ('Bill Nye', 'Neil deGrasse Tyson', 'MC Ren & DJ Yella')."""
    t = text.strip()
    words = t.split()
    if not (1 <= len(words) <= max_words) or len(t) > 40:
        return False
    if not (words[0][:1].isupper() and words[-1][:1].isupper()):
        return False
    if words[0].lower().strip(",.") in _LABEL_STOP or t.lower() in _META_KEYS:
        return False
    if {w.strip(".,!?").lower() for w in words} & _INSTR_WORDS:
        return False
    return all(_NAME_WORD_RE.match(w) for w in words)


def _plain_header(text: str) -> tuple[bool, str | None, str | None, int]:
    """An unbracketed header line: 'Verse 1:' / 'CHORUS' / '*Chorus*' / 'Chorus x2' / 'Chorus (repeat)' / '(Chorus)' /
    '1st Verse:' / 'Verse 2: Newton' / 'Verse 2 - Newton' / 'Newton (Verse 2):' (sections, M5-D48, M5-D54) or a
    'Bill Nye:' speaker marker alone on its line when the file accepted it (M5-D47, M5-D54). Never a line with
    lyric text."""
    s = _strip_deco(text)
    paren = len(s) > 2 and s[0] == "(" and s[-1] == ")" and s.count("(") == 1
    inner = s[1:-1].strip() if paren else s
    rep = 1
    rm = _REPEAT_RE.search(inner)
    if rm and rm.start() > 0:
        rep = int(next(g for g in rm.groups() if g))
        inner = inner[: rm.start()].strip()
    head, colon, tail = inner.partition(":")
    head, tail = head.strip(), tail.strip()
    if not colon:
        dm = _DASH_RE.search(inner)
        if dm and _PLAIN_SEC_RE.match(inner[: dm.start()].strip()):
            head, tail = inner[: dm.start()].strip(), inner[dm.end():].strip()
    if _PLAIN_SEC_RE.match(head):
        sec = _section_word(head)
        if not tail:
            return True, None, sec, rep
        if not paren and _is_name(tail, 5):
            return True, tail, sec, rep
        return False, None, None, 1
    if colon and not tail and not paren:
        pm = _PAREN_SEC_RE.match(head)
        if pm and _PLAIN_SEC_RE.match(pm.group(2).strip()) and _is_name(pm.group(1), 5):
            return True, pm.group(1).strip(), _section_word(pm.group(2)), rep   # 'Newton (Verse 1):'
        if rep == 1:
            name = _lone_marker(s)
            if name is not None and name.lower() in _MARKERS.get():
                return True, name, None, 1
    return False, None, None, 1


def _header(text: str, bare: bool = False) -> tuple[bool, str | None, str | None, int]:
    """A section / speaker header -> (is_header, speaker, section_word, repeat). Not a lyric line.
    Bracketed: '[Verse 1: Newton]', '[Final Chorus]', '[Newton:]', '[Newton]' (a speaker only in a labelled file).
    Unbracketed: see _plain_header."""
    m = _HEADER_RE.match(text)
    if not m:
        return _plain_header(text)
    inner = m.group(1).strip()
    rep = 1
    rm = _REPEAT_RE.search(inner)
    if rm:
        rep = int(next(g for g in rm.groups() if g))
        inner = inner[: rm.start()].strip()
    speaker = None
    dm = _DASH_RE.search(inner) if ":" not in inner else None
    if dm and _section_word(inner[: dm.start()]) is not None:
        inner = inner[: dm.start()].strip() + ": " + inner[dm.end():].strip()   # '[Verse 1 - Newton]'
    if ":" in inner:
        head, tail = (x.strip() for x in inner.split(":", 1))
        if head.lower() in _META_KEYS:
            return True, None, None, rep  # LRC ID / metadata tag
        hsec = _section_word(head)
        sec = hsec
        if hsec is not None:
            twords = {w.strip(".,!?").lower() for w in tail.split()}
            if tail and _section_word(tail) is None and not (twords & _INSTR_WORDS):
                speaker = tail                        # '[Verse 1: Newton]' ('[Intro: Spoken]' names no one)
        elif not tail:
            words = {w.strip(".,!?").lower() for w in head.split()}
            if 0 < len(head.split()) <= 5 and not (words & _INSTR_WORDS):
                speaker = head                        # '[Bill Nye:]' (M5-D47)
        elif _section_word(tail) is not None and _is_name(head, 5):
            speaker, sec = head, _section_word(tail)  # '[Newton: Verse 1]'
        else:
            speaker = tail
        return True, speaker, sec, rep
    sec = _section_word(inner)
    if sec is None and 0 < len(inner.split()) <= 4:
        words = {w.strip(".,!?").lower() for w in inner.split()}
        if not (words & _INSTR_WORDS) and (bare or _LABELLED.get()):
            speaker = inner
    return True, speaker, sec, rep


def _is_backing(text: str) -> bool:
    s = text.strip()
    return len(s) > 2 and s[0] == "(" and s[-1] == ")" and s.count("(") == 1


# ------------------------------------------------------------------------------------------ parsers
@_labels_scoped
def parse_lrc(text: str) -> dict[str, Any]:
    """LRC with optional A2 word tags (<mm:ss.xx>), multiple line tags per line (repeats), [offset:ms],
    enhanced-LRC voice prefixes and speaker labels."""
    meta: dict[str, str] = {}
    entries: list[tuple[float, str, int]] = []
    order = 0
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        mm = _LRC_META_RE.match(s)
        if mm and not _LRC_TAG_RE.match(s):
            meta[mm.group(1).lower()] = mm.group(2).strip()
            continue
        times = []
        while True:
            m = _LRC_TAG_RE.match(s)
            if not m:
                break
            times.append(_ts(m.group(1), m.group(2)))
            s = s[m.end():]
        for t in times:
            entries.append((t, s.strip(), order))
            order += 1
    offset = 0.0
    if "offset" in meta:
        try:
            offset = float(meta["offset"]) / 1000.0   # LRC: positive offset shows lyrics earlier
        except ValueError:
            pass
    entries.sort(key=lambda e: (e[0], e[2]))
    lines: list[dict[str, Any]] = []
    speaker = None
    for i, (t, body, _) in enumerate(entries):
        t = t - offset
        nxt = entries[i + 1][0] - offset if i + 1 < len(entries) else None
        wts = list(_WORD_TAG_RE.finditer(body))
        words = None
        plain = body
        if wts:
            words = []
            for k, m in enumerate(wts):
                seg = body[m.end(): wts[k + 1].start() if k + 1 < len(wts) else len(body)].strip()
                wt = _ts(m.group(1), m.group(2)) - offset
                if seg:
                    for j, w in enumerate(seg.split()):
                        words.append({"text": w, "t": wt if j == 0 else None})
                elif k == len(wts) - 1 and words:
                    words[-1]["end"] = wt   # trailing tag = end of the last word
            plain = " ".join(w["text"] for w in words)
        if not plain.strip():
            if lines and lines[-1]["end"] is None:
                lines[-1]["end"] = t
            continue
        is_h, sp, sec, _rep = _header(plain)
        if is_h:
            if sp or sec:
                speaker = sp
            continue
        lab, rest = _label_split(plain)
        if lab:
            speaker = lab
            if words:
                drop = len(plain.split()) - len(rest.split())
                words = words[drop:]
                if words and words[0]["t"] is None:
                    words[0]["t"] = t
            plain = rest
        end = None
        if words and words[-1].get("end") is not None:
            end = words[-1].pop("end")
        lines.append({"text": plain, "t": t, "end": end if end is not None else nxt, "words": words,
                      "speaker": speaker, "backing": _is_backing(plain), "origin": "source"})
    for ln in lines:
        if ln["words"]:
            for w in ln["words"]:
                w.pop("end", None)
    return {"format": "lrc", "lines": lines, "meta": meta, "has_line_sync": bool(lines),
            "has_word_sync": any(ln["words"] for ln in lines), "offset_tag_s": offset}


def _vtt_srt_cues(text: str, vtt: bool) -> list[tuple[float, float, str]]:
    ts = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
    rx = re.compile(ts + r"\s*-->\s*" + ts)
    cues = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    for b in blocks:
        ls = [x for x in b.split("\n") if x.strip()]
        for i, ln in enumerate(ls):
            m = rx.search(ln)
            if m:
                g = m.groups()
                t0 = int(g[0] or 0) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3].ljust(3, "0")) / 1000
                t1 = int(g[4] or 0) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7].ljust(3, "0")) / 1000
                body = "\n".join(ls[i + 1:])
                cues.append((t0, t1, body))
                break
    return cues


@_labels_scoped
def parse_srt(text: str) -> dict[str, Any]:
    lines = []
    speaker = None
    for t0, t1, body in _vtt_srt_cues(text, vtt=False):
        for k, part in enumerate(x for x in body.split("\n") if x.strip()):
            plain = re.sub(r"<[^>]+>|\{[^}]+\}", "", part).strip()
            if not plain:
                continue
            is_h, sp, sec, _ = _header(plain)
            if is_h:
                speaker = sp if (sp or sec) else speaker
                continue
            lab, plain = _label_split(plain)
            speaker = lab or speaker
            lines.append({"text": plain, "t": t0 if k == 0 else None, "end": t1, "words": None, "speaker": speaker,
                          "backing": _is_backing(plain), "origin": "source"})
    return {"format": "srt", "lines": lines, "meta": {}, "has_line_sync": bool(lines), "has_word_sync": False}


@_labels_scoped
def parse_vtt(text: str) -> dict[str, Any]:
    """WebVTT; inline <hh:mm:ss.mmm> word timestamps and <v Name> voice spans are honoured."""
    lines = []
    speaker = None
    inline = re.compile(r"<(?:(\d+):)?(\d{1,2}):(\d{2})\.(\d{3})>")
    for t0, t1, body in _vtt_srt_cues(text, vtt=True):
        for k, part in enumerate(x for x in body.split("\n") if x.strip()):
            vm = re.match(r"^<v(?:\.[^ >]*)?\s+([^>]+)>", part)
            if vm:
                speaker = vm.group(1).strip()
            words = None
            if inline.search(part):
                words = []
                pos = 0
                cur_t = t0
                for m in inline.finditer(part + "<99:59:59.999>"):
                    seg = re.sub(r"<[^>]+>", "", part[pos:m.start()]).strip()
                    for j, w in enumerate(seg.split()):
                        words.append({"text": w, "t": cur_t if j == 0 else None})
                    g = m.groups()
                    cur_t = int(g[0] or 0) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
                    pos = m.end()
            plain = re.sub(r"<[^>]+>", "", part).strip()
            if not plain:
                continue
            is_h, sp, sec, _ = _header(plain)
            if is_h:
                speaker = sp if (sp or sec) else speaker
                continue
            lab, rest = _label_split(plain)
            if lab:
                speaker = lab
                if words:
                    words = words[len(plain.split()) - len(rest.split()):]
                plain = rest
            lines.append({"text": plain, "t": t0 if k == 0 else None, "end": t1, "words": words or None,
                          "speaker": speaker, "backing": _is_backing(plain), "origin": "source"})
    return {"format": "vtt", "lines": lines, "meta": {}, "has_line_sync": bool(lines),
            "has_word_sync": any(ln["words"] for ln in lines)}


@_labels_scoped
def parse_txt(text: str) -> dict[str, Any]:
    """Plain text: one lyric line per text line; [headers] (sections, speakers, '[Chorus x2]'), 'Name:' labels,
    '(x2)' line repeats, '(Repeat chorus)' or an empty '[Chorus]' header re-insert the last block of that kind."""
    lines: list[dict[str, Any]] = []
    speaker = None
    blocks: dict[str, list[dict[str, Any]]] = {}
    cur: dict[str, Any] | None = None

    def close() -> None:
        if cur is None:
            return
        if cur["lines"]:
            if cur["sec"]:
                blocks[cur["sec"]] = [dict(x) for x in cur["lines"]]
            for _ in range(min(cur["rep"], 8) - 1):
                lines.extend(dict(x) for x in cur["lines"])
        elif cur["sec"] and cur["sec"] in blocks:
            for _ in range(min(cur["rep"], 8)):
                lines.extend(dict(x) for x in blocks[cur["sec"]])

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        s = raw.strip()
        if not s:
            continue
        rm_repeat = re.match(r"^\(?\s*repeat\s+(?:the\s+)?(chorus|hook|refrain|verse|bridge)\b[^)]*\)?$", s, re.I)
        if rm_repeat:
            close()
            cur = None
            src = blocks.get(rm_repeat.group(1).lower())
            if src:
                lines.extend(dict(x) for x in src)
            continue
        lone_rep = _REPEAT_RE.fullmatch(s)
        if lone_rep:
            # '(x2)' on its own line repeats the line before it (repeated-section expansion only ADDS more)
            n = int(next(g for g in lone_rep.groups() if g))
            if lines:
                for _ in range(max(0, min(n, 16) - 1)):
                    lines.append(dict(lines[-1]))
                    if cur is not None:
                        cur["lines"].append(dict(lines[-1]))
            continue
        is_h, sp, sec, rep = _header(s)
        if is_h:
            close()
            cur = {"sec": sec, "rep": rep, "lines": []}
            if sp or sec:
                speaker = sp
            continue
        n = 1
        rm = _REPEAT_RE.search(s)
        if rm and rm.start() > 0:
            n = int(next(g for g in rm.groups() if g))
            s = s[: rm.start()].strip()
        lab, s2 = _label_split(s)
        if lab:
            speaker = lab
        ln = {"text": s2, "t": None, "end": None, "words": None, "speaker": speaker, "backing": _is_backing(s2),
              "origin": "source"}
        for _ in range(max(1, min(n, 16))):
            lines.append(dict(ln))
            if cur is not None:
                cur["lines"].append(dict(ln))
    close()
    return {"format": "txt", "lines": lines, "meta": {}, "has_line_sync": False, "has_word_sync": False}


@_labels_scoped
def parse_lyricsfile(text: str) -> dict[str, Any]:
    """LRCLIB Lyricsfile (YAML): metadata{duration_ms, language, instrumental}, lines[{text, start_ms, end_ms,
    words[{text, start_ms}]}], plain."""
    import yaml

    y = yaml.safe_load(text) or {}
    md = y.get("metadata") or {}
    lines: list[dict[str, Any]] = []
    speaker = None
    for ln in y.get("lines") or []:
        txt = str(ln.get("text") or "").strip()
        if not txt:
            continue
        is_h, sp, sec, _ = _header(txt)
        if is_h:
            speaker = sp if (sp or sec) else speaker
            continue
        words = None
        if ln.get("words"):
            words = []
            for w in ln["words"]:
                parts = str(w.get("text") or "").split()
                for j, part in enumerate(parts):
                    words.append({"text": part, "t": (float(w["start_ms"]) / 1000.0) if (j == 0 and w.get("start_ms") is not None) else None})
        lab, rest = _label_split(txt)
        if lab:
            speaker = lab
            if words:
                words = words[len(txt.split()) - len(rest.split()):]
            txt = rest
        lines.append({"text": txt, "t": float(ln["start_ms"]) / 1000.0 if ln.get("start_ms") is not None else None,
                      "end": float(ln["end_ms"]) / 1000.0 if ln.get("end_ms") is not None else None,
                      "words": words or None, "speaker": speaker, "backing": _is_backing(txt), "origin": "source"})
    if not lines and y.get("plain"):
        return {**parse_txt(str(y["plain"])), "format": "lyricsfile_plain",
                "meta": {"language": md.get("language"), "duration_ms": md.get("duration_ms")}}
    return {"format": "lyricsfile", "lines": lines, "meta": {"language": md.get("language"), "duration_ms": md.get("duration_ms")},
            "has_line_sync": any(x["t"] is not None for x in lines), "has_word_sync": any(x["words"] for x in lines)}


def parse_any(text: str, name: str = "") -> dict[str, Any]:
    """Pick the parser from the extension, then from the content."""
    ext = Path(name).suffix.lower()
    body = text.lstrip("﻿")
    if ext == ".lrc" or (ext not in (".srt", ".vtt", ".txt") and re.search(r"^\s*\[\d{1,3}:\d{1,2}", body, re.M)):
        return parse_lrc(body)
    if ext == ".vtt" or body.lstrip().startswith("WEBVTT"):
        return parse_vtt(body)
    if ext == ".srt" or re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->", body):
        return parse_srt(body)
    if ext in (".yaml", ".yml", ".lyricsfile") or (re.search(r"^lines:\s*$", body, re.M) and "start_ms" in body):
        try:
            return parse_lyricsfile(body)
        except Exception:  # noqa: BLE001  (not YAML after all)
            pass
    return parse_txt(body)


# ------------------------------------------------------------------------------------------ normalisation
def norm_words(text: str) -> list[str]:
    """Lower-case comparison words (apostrophes removed, punctuation -> space, accents folded)."""
    t = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s']", " ", t).replace("'", "")
    return t.split()


def line_key(text: str) -> str:
    return " ".join(norm_words(text))


def display_words(text: str) -> list[str]:
    """Whitespace words; pure-punctuation tokens are glued to the previous word (or the next one)."""
    out: list[str] = []
    carry = ""
    for w in text.split():
        if not any(ch.isalnum() for ch in w):
            if out:
                out[-1] = out[-1] + " " + w
            else:
                carry = (carry + " " + w).strip()
            continue
        out.append((carry + " " + w).strip() if carry else w)
        carry = ""
    if carry and out:
        out[-1] += " " + carry
    elif carry:
        out.append(carry)
    return out


class TokenMaker:
    """Display word -> MMS_FA token ids (uroman for non-Latin scripts, num2words for digits, the MMS
    dictionary characters only). uroman is loaded lazily (2 s) and only when a word is not ASCII."""

    def __init__(self, dictionary: dict[str, int], lang: str | None = "en"):
        self.dct = dictionary
        self.lang = (lang or "en").split("-")[0]
        self._uro = None
        self._cache: dict[str, list[int]] = {}

    def _n2w(self, m: re.Match) -> str:
        from num2words import num2words

        s = m.group(0)
        try:
            if re.match(r"^\d+(st|nd|rd|th)$", s, re.I):
                return " " + num2words(int(re.sub(r"\D", "", s)), to="ordinal", lang=self.lang) + " "
            return " " + num2words(int(s), lang=self.lang) + " "
        except (NotImplementedError, OverflowError, ValueError):
            from num2words import num2words as n2

            return " " + n2(int(re.sub(r"\D", "", s) or 0)) + " "

    def romanise(self, text: str) -> str:
        t = text.replace("’", "'").replace("&", " and ").replace("%", " percent ")
        t = re.sub(r"\d+(?:st|nd|rd|th)?", self._n2w, t)
        if any(ord(c) > 127 for c in t):
            folded = unicodedata.normalize("NFKD", t)
            folded = "".join(c for c in folded if not unicodedata.combining(c))
            if any(ord(c) > 127 for c in folded):
                if self._uro is None:
                    import uroman

                    self._uro = uroman.Uroman()
                folded = self._uro.romanize_string(folded)
            t = folded
        return t.lower()

    def tokens(self, word: str) -> list[int]:
        if word in self._cache:
            return self._cache[word]
        r = self.romanise(word)
        toks = [self.dct[c] for c in r if c in self.dct and c != "-"]
        self._cache[word] = toks
        return toks


def mms_word_tokens(words: Iterable[str], tm: TokenMaker) -> list[list[int]]:
    return [tm.tokens(w) for w in words]


def any_text(lines: Iterable[dict[str, Any]], f: Callable[[str], Any] = len) -> int:
    """Helper for counts in logs (never the text itself)."""
    return sum(1 for ln in lines if f(ln.get("text") or ""))
