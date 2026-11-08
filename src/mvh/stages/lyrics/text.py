# ruff: noqa: E501
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
_STRIP_PREFIX = re.compile(r"^\s*(?:-\s*)?(?:text:\s*[\"']?)?(?:\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]\s*)*(?:<[^>]*>\s*)*")


def _file_labelled(text: str) -> bool:
    """True when inline 'Name: ...' prefixes of this lyric file are speaker labels: the same label recurs, or a
    header names a speaker. A one-off 'Time: ...' in an unlabelled file is sung text, not a label."""
    counts: dict[str, int] = {}
    for raw in text.splitlines():
        s = _STRIP_PREFIX.sub("", raw).strip().strip("\"'")
        if not s:
            continue
        is_h, sp, sec, _rep = _header(s, bare=True)
        if is_h:
            if sp:
                if sec is not None and ":" in s:  # '[Verse 1: Newton]' names a speaker explicitly
                    return True
                key = sp.strip().lower()
                counts[key] = counts.get(key, 0) + 1  # bare '[Name]': needs a recurrence
            continue
        m = _LABEL_RE.match(s)
        if m:
            lab = m.group(1).strip().lower()
            if len(lab) <= 30 and lab not in _LABEL_STOP and not lab.startswith(SECTION_WORDS):
                counts[lab] = counts.get(lab, 0) + 1
    return any(n >= 2 for n in counts.values())


def _labels_scoped(fn):
    @functools.wraps(fn)
    def wrapper(text, *a, **kw):
        tok = _LABELLED.set(_file_labelled(text))
        try:
            return fn(text, *a, **kw)
        finally:
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
        if len(lab) <= 30 and lab.lower() not in _LABEL_STOP and not lab.lower().startswith(SECTION_WORDS):
            return lab, m.group(2).strip()
    return None, text


def _header(text: str, bare: bool = False) -> tuple[bool, str | None, str | None, int]:
    """A '[Verse 1: Newton]' style header -> (is_header, speaker, section_word, repeat). Not a lyric line."""
    m = _HEADER_RE.match(text)
    if not m:
        return False, None, None, 1
    inner = m.group(1).strip()
    rep = 1
    rm = _REPEAT_RE.search(inner)
    if rm:
        rep = int(next(g for g in rm.groups() if g))
        inner = inner[: rm.start()].strip()
    sec = None
    low = inner.lower()
    for w in SECTION_WORDS:
        if low.startswith(w):
            sec = w
            break
    speaker = None
    if ":" in inner:
        head, tail = inner.split(":", 1)
        speaker = tail.strip() or None
        if head.strip().lower() in _META_KEYS:
            speaker = None  # LRC ID / metadata tag
        elif sec is None and head.strip().lower().startswith(SECTION_WORDS):
            sec = head.strip().lower()
    elif sec is None and 0 < len(inner.split()) <= 4:
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
