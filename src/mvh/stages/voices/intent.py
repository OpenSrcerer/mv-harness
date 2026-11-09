"""Reading the user's meaning/intent.md for the voices stage.

User decision UD1 (CONTRACT D78): intent.md is read in exactly two ways, plus the viewer's managed block, by ONE
parser: ``mvh.stages.meaning.intent.parse_intent`` (grammar mvh-intent v2, documented there). Structured answers come
only from the interview template; free text is the user's notes and is never parsed (so ``C1 ... voice V1`` or
``voices: 4`` in prose is not a mapping or a count here either, and voices and meaning always agree).

Extracted (all optional):
* ``n_characters``: the characters the TEMPLATE defines (``characters:`` entries and ``voices:`` mappings);
* ``n_voices``: an explicit singer count, ``voices: 3`` in the template;
* ``voice_to_character``: the template's ``characters.*.voices`` lists and its ``voices:`` map (which wins), then the
  viewer block's ``- V2 = C1 Name`` lines, which win over both (the latest edit);
* ``n_voices_min``: the highest voice id the viewer block maps, a FLOOR for the count (D51/D69): mapping V1 and V2 to one
  character must not re-cluster the song into one voice;
* ``line_characters``: the template's ``line_singers``; ``line_voice`` stays empty (per-line voice fixes are
  ``overrides.json voices.lines``).

The text is the user's; nothing from it is logged.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["parse_intent"]


def _vkey(v: str) -> int:
    return int(v[1:])


def parse_intent(text: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"n_characters": None, "n_voices": None, "n_voices_min": None, "voice_to_character": {},
                           "line_voice": {}, "line_characters": {}}
    if not text:
        return out
    from mvh.stages.meaning.intent import parse_intent as meaning_parse
    from mvh.stages.viewer.intent_block import _BLOCK_RE

    try:
        tmpl = meaning_parse(_BLOCK_RE.sub("\n", text))  # the template alone: its characters are a count
    except Exception:  # noqa: BLE001 - a parser problem must not fail the voices stage
        tmpl = None
    if tmpl is not None:
        chars = tmpl.get("characters") or {}
        if chars:
            out["n_characters"] = len(chars)
        if tmpl.get("n_voices"):
            out["n_voices"] = int(tmpl["n_voices"])
        v2c: dict[str, str] = {}
        for cid in sorted(chars, key=_vkey):
            for v in chars[cid].get("voices") or []:
                if isinstance(v, str) and re.fullmatch(r"V[1-9]\d*", v):
                    v2c.setdefault(v, cid)
        v2c.update({v: c for v, c in (tmpl.get("voice_map") or {}).items()})  # 'voices:' wins (one character per voice)
        out["voice_to_character"] = dict(sorted(v2c.items(), key=lambda kv: _vkey(kv[0])))
        for lid, cs in (tmpl.get("line_singers") or {}).items():
            if isinstance(cs, list) and cs:
                out["line_characters"][str(lid)] = [str(c) for c in cs]
    _merge_viewer_block(text, out)
    return out


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
