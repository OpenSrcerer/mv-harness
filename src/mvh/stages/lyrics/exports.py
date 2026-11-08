# ruff: noqa: E501
"""Lyric exports derived from the canonical lyrics.json lines/words: LRC with A2 word tags, WebVTT with inline
word timestamps (and <v speaker> when a speaker hint exists), SRT (line level) and ASS karaoke (\\k tags)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = ["to_lrc", "to_vtt", "to_srt", "to_ass"]


def _mmss(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 6000:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


def _hms(t: float, sep: str = ".") -> str:
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:{(ms // 1000) % 60:02d}{sep}{ms % 1000:03d}"


def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000:d}:{(cs // 6000) % 60:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


def _words_by_line(words: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = {}
    for w in words:
        out.setdefault(w["line_id"], []).append(w)
    return out


def _clean(s: str) -> str:
    return " ".join(str(s).replace("\r", " ").replace("\n", " ").split())


def to_lrc(meta: Mapping[str, Any], lines: Sequence[Mapping[str, Any]], words: Sequence[Mapping[str, Any]]) -> str:
    out = []
    for k, tag in (("title", "ti"), ("artist", "ar"), ("album", "al")):
        if meta.get(k):
            out.append(f"[{tag}:{_clean(meta[k])}]")
    if meta.get("duration_s"):
        d = float(meta["duration_s"])
        out.append(f"[length:{int(d // 60):02d}:{d % 60:05.2f}]")
    out.append("[by:mv-harness (MMS_FA word alignment)]")
    wb = _words_by_line(words)
    for ln in lines:
        ws = wb.get(ln["id"], [])
        if ws:
            parts = [f"[{_mmss(ln['t'])}]"]
            for w in ws:
                parts.append(f"<{_mmss(w['t'])}> {_clean(w['text'])}")
            parts.append(f"<{_mmss(ws[-1]['t'] + ws[-1]['d'])}>")
            out.append(" ".join(parts))
        else:
            out.append(f"[{_mmss(ln['t'])}] {_clean(ln['text'])}")
    return "\n".join(out) + "\n"


def to_vtt(lines: Sequence[Mapping[str, Any]], words: Sequence[Mapping[str, Any]]) -> str:
    out = ["WEBVTT", ""]
    wb = _words_by_line(words)
    for ln in lines:
        ws = wb.get(ln["id"], [])
        body = ""
        if ws:
            toks = []
            for i, w in enumerate(ws):
                toks.append(_clean(w["text"]) if i == 0 else f"<{_hms(w['t'])}>{_clean(w['text'])}")
            body = " ".join(toks)
        else:
            body = _clean(ln["text"])
        if ln.get("speaker_hint"):
            body = f"<v {_clean(ln['speaker_hint'])}>{body}"
        out += [ln["id"], f"{_hms(ln['t'])} --> {_hms(ln['t'] + max(ln['d'], 0.01))}", body, ""]
    return "\n".join(out)


def to_srt(lines: Sequence[Mapping[str, Any]]) -> str:
    out = []
    for i, ln in enumerate(lines, 1):
        out += [str(i), f"{_hms(ln['t'], ',')} --> {_hms(ln['t'] + max(ln['d'], 0.01), ',')}", _clean(ln["text"]), ""]
    return "\n".join(out)


def to_ass(meta: Mapping[str, Any], lines: Sequence[Mapping[str, Any]], words: Sequence[Mapping[str, Any]]) -> str:
    head = [
        "[Script Info]",
        f"Title: {_clean(meta.get('title') or 'lyrics')}",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding",
        "Style: Default,Arial,64,&H00FFFFFF,&H0000A5FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,80,1",
        "Style: Backing,Arial,48,&H00C8C8C8,&H0000A5FF,&H00000000,&H64000000,0,1,0,0,100,100,0,0,1,2,1,8,60,60,80,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    wb = _words_by_line(words)
    ev = []
    for ln in lines:
        ws = wb.get(ln["id"], [])
        t0, t1 = float(ln["t"]), float(ln["t"]) + max(float(ln["d"]), 0.01)
        if ws:
            t1 = max(t1, ws[-1]["t"] + ws[-1]["d"])
            parts = []
            cur = t0
            for w in ws:
                gap = w["t"] - cur
                if gap >= 0.01:
                    parts.append(f"{{\\k{int(round(gap * 100))}}}")
                parts.append(f"{{\\k{max(1, int(round(w['d'] * 100)))}}}{_clean(w['text'])} ")
                cur = w["t"] + w["d"]
            text = "".join(parts).rstrip()
        else:
            text = _clean(ln["text"])
        style = "Backing" if ln.get("backing") else "Default"
        name = _clean(ln.get("speaker_hint") or "")
        ev.append(f"Dialogue: {1 if ln.get('backing') else 0},{_ass_time(t0)},{_ass_time(t1)},{style},{name},0,0,0,karaoke,{text}")
    return "\n".join(head + ev) + "\n"
