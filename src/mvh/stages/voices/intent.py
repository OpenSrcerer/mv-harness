# ruff: noqa: E501
"""Reading the user's meaning/intent.md for the voices stage (free text or the YAML-ish interview template).

Extracted (all optional):
* ``n_characters``: distinct character ids defined in the text (``C1 ...``, ``- C2 The Tide``), or the items of
  a "Characters" section when no ids are used;
* ``n_voices``: an explicit count (``voices: 4``, ``number of voices = 3``, ``singers: 2``);
* ``voice_to_character``: ``C1 ... voice V1`` / ``V2 = C3`` / ``V2 -> C3``;
* ``line_voice`` / ``line_characters``: per-line assignments the viewer writes (``L007: V2``, ``L012 = C1+C2``).

The text is the user's; nothing from it is logged.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["parse_intent"]

_CHAR_DEF = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(C[1-9]\d*)\b", re.M)
_COUNT = re.compile(r"\b(?:n_voices|number of voices|voices|singers|number of singers|voice count)\s*[:=]\s*(\d{1,2})\b", re.I)
_C_VOICE = re.compile(r"\b(C[1-9]\d*)\b[^\n]{0,80}?\bvoice\s*(?:id\s*)?[:=]?\s*(V[1-9]\d*)\b", re.I)
_V_TO_C = re.compile(r"\b(V[1-9]\d*)\s*(?:=|->|→|:|is)\s*(C[1-9]\d*)\b")
_LINE = re.compile(r"\b(L\d{3,})\s*(?:=|:|->|→)\s*((?:V[1-9]\d*)|(?:C[1-9]\d*(?:\s*\+\s*C[1-9]\d*)*))\b")


def parse_intent(text: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"n_characters": None, "n_voices": None, "voice_to_character": {}, "line_voice": {},
                           "line_characters": {}}
    if not text:
        return out
    body = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    chars = sorted(set(_CHAR_DEF.findall(body)), key=lambda c: int(c[1:]))
    if not chars:
        m = re.search(r"^#+\s*characters?\s*$(.*?)(?=^#+\s|\Z)", body, re.M | re.S | re.I)
        if m:
            items = [ln for ln in m.group(1).splitlines() if re.match(r"^\s*[-*]\s+\S", ln)]
            if items:
                out["n_characters"] = len(items)
    else:
        out["n_characters"] = len(chars)
    m = _COUNT.search(body)
    if m:
        out["n_voices"] = int(m.group(1))
    v2c: dict[str, str] = {}
    for c, v in _C_VOICE.findall(body):
        v2c.setdefault(v.upper(), c.upper())
    for v, c in _V_TO_C.findall(body):
        v2c.setdefault(v.upper(), c.upper())
    out["voice_to_character"] = dict(sorted(v2c.items(), key=lambda kv: int(kv[0][1:])))
    for lid, who in _LINE.findall(body):
        who = re.sub(r"\s+", "", who)
        if who.startswith("V"):
            out["line_voice"][lid] = who
        else:
            out["line_characters"][lid] = who.split("+")
    return out
