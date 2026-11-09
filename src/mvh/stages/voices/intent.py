"""Reading the user's meaning/intent.md for the voices stage (free text or the YAML-ish interview template).

Extracted (all optional):
* ``n_characters``: distinct character ids defined in the text (``C1 ...``, ``- C2 The Tide``), or the items of
  a "Characters" section when no ids are used;
* ``n_voices``: an explicit count (``voices: 4``, ``number of voices = 3``, ``singers: 2``);
* ``voice_to_character``: ``C1 ... voice V1`` / ``V2 = C3`` / ``V2 -> C3``;
* ``line_voice`` / ``line_characters``: per-line assignments the viewer writes (``L007: V2``, ``L012 = C1+C2``).

W3 (CONTRACT D51, CR M6a-1 / M6b CR-5): two more readers are layered on top of the regexes above.
* The viewer's managed block (``<!-- mvh-viewer:begin v1 -->``, grammar ``mvh.stages.viewer.intent_block``): its
  ``- V2 = C1 Name`` lines are the user's latest edit and WIN for ``voice_to_character``. The highest voice id it maps
  is a floor ``n_voices_min`` (mapping V1 and V2 to one character must not re-cluster the song into one voice; mapping
  only V1 must not fold the other singers into it).
* The interview's YAML template, through ``mvh.stages.meaning.intent.parse_intent`` (the meaning stage's parser):
  its ``characters: {C1: {voices: [V1]}}`` lists fill ``voice_to_character`` and its character count fills
  ``n_characters``; ``line_singers`` fill ``line_characters``. The regex results win where both answer.

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
    out: dict[str, Any] = {"n_characters": None, "n_voices": None, "n_voices_min": None, "voice_to_character": {},
                           "line_voice": {}, "line_characters": {}}
    if not text:
        return out
    from mvh.stages.viewer.intent_block import _BLOCK_RE

    # the viewer's managed block is read by _merge_viewer_block only: its "C1 ... V2" lines are mappings, not a
    # character count (F-R4-VOICE-FLOOR)
    body = re.sub(r"<!--.*?-->", " ", _BLOCK_RE.sub("\n", text), flags=re.S)
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
    _merge_template(text, out)
    _merge_viewer_block(text, out)
    return out


def _vkey(v: str) -> int:
    return int(v[1:])


def _merge_template(text: str, out: dict[str, Any]) -> None:
    """The YAML interview template (meaning's parser): characters, their voice lists, line singers."""
    try:
        from mvh.stages.meaning.intent import parse_intent as meaning_parse
        from mvh.stages.viewer.intent_block import _BLOCK_RE

        mi = meaning_parse(_BLOCK_RE.sub("\n", text))
    except Exception:  # noqa: BLE001 - a parser problem must not fail the voices stage; the regexes still answer
        return
    if "yaml" not in str(mi.get("form", "")):
        return
    chars = mi.get("characters") or {}
    if chars and out["n_characters"] is None:
        out["n_characters"] = len(chars)
    v2c = dict(out["voice_to_character"])
    for cid in sorted(chars, key=_vkey):
        for v in chars[cid].get("voices") or []:
            if isinstance(v, str) and re.fullmatch(r"V[1-9]\d*", v):
                v2c.setdefault(v, cid)
    out["voice_to_character"] = dict(sorted(v2c.items(), key=lambda kv: _vkey(kv[0])))
    for lid, cs in (mi.get("line_singers") or {}).items():
        if isinstance(cs, list) and cs:
            out["line_characters"].setdefault(str(lid), [str(c) for c in cs])


def _merge_viewer_block(text: str, out: dict[str, Any]) -> None:
    """The viewer's managed block: voice -> character edits win; the highest mapped voice is a floor for n_voices."""
    from mvh.stages.viewer.intent_block import parse as parse_block

    vb = parse_block(text).get("voices") or {}
    if not vb:
        return
    v2c = dict(out["voice_to_character"])
    for v, rec in vb.items():
        v2c[v] = rec["character_id"]
    out["voice_to_character"] = dict(sorted(v2c.items(), key=lambda kv: _vkey(kv[0])))
    floor = max(_vkey(v) for v in vb)
    # a FLOOR, not a count (D51, F-R4-VOICE-FLOOR): mapping V1..Vn keeps at least n voices; the stage still estimates
    # the rest. An explicit count below the floor is raised to it.
    out["n_voices_min"] = max(floor, out.get("n_voices_min") or 0)
    if out["n_voices"] is not None and out["n_voices"] < floor:
        out["n_voices"] = floor
