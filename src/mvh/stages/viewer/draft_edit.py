"""Remove suggestions from the draft ``meaning/authored.json`` (the viewer's "dismiss").

A draft is a labelled suggestion: agents read it as such until the user answers the field. Dismissing a suggestion
deletes that field from the draft, so it no longer reaches anyone. Pure functions; the server reads and writes the
file. Draft section entries are matched to the current sections the way the meaning stage does (``anchor_claim``).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from mvh.stages.meaning.anchor import anchor_claim, group_of

__all__ = ["dismiss", "DraftError", "SONG_FIELDS", "SECTION_FIELDS"]

#: song-level fields of a draft that can be dismissed
SONG_FIELDS = ("logline", "summary", "setting", "tone", "themes", "palette", "do_not")
#: per-section fields: the viewer's name -> the draft's key
SECTION_FIELDS = {"feel": "feel", "meaning": "meaning", "movement": "movement_hint", "camera": "camera_hint",
                  "palette": "palette_hint", "movement_hint": "movement_hint", "camera_hint": "camera_hint",
                  "palette_hint": "palette_hint"}


class DraftError(ValueError):
    pass


def _clear(doc: dict[str, Any], key: str) -> bool:
    v = doc.get(key)
    if not v:
        return False
    doc[key] = [] if isinstance(v, list) else None
    return True


def dismiss(doc: dict[str, Any], items: Any, sections: Sequence[Mapping[str, Any]],
            roles: Sequence[Mapping[str, Any]] = ()) -> int:
    """Remove the listed suggestions from the draft ``doc`` (in place); returns how many fields were removed.

    An item is ``{scope: 'song', field}`` (with ``value`` to remove one do-not rule or theme),
    ``{scope: 'section', id: 'S04', field}`` or ``{scope: 'group', key: 'all' | <label>, field}``."""
    if not isinstance(items, list) or not items:
        raise DraftError("expected {dismiss: [{scope, field, ...}]}")
    removed = 0
    for it in items:
        if not isinstance(it, dict):
            raise DraftError("a dismiss item must be an object")
        scope, field = it.get("scope"), str(it.get("field") or "")
        if scope == "song":
            if field not in SONG_FIELDS:
                raise DraftError(f"unknown song field {field[:20]!r}")
            value = it.get("value")
            if value is not None and isinstance(doc.get(field), list):
                keep = [x for x in doc[field]
                        if (x.get("text") if isinstance(x, dict) else x) != value]
                removed += int(len(keep) != len(doc[field]))
                doc[field] = keep
            else:
                removed += int(_clear(doc, field))
            continue
        if scope not in ("section", "group"):
            raise DraftError(f"unknown scope {str(scope)[:20]!r}")
        dkey = SECTION_FIELDS.get(field)
        if dkey is None:
            raise DraftError(f"unknown section field {field[:20]!r}")
        if scope == "section":
            target = {str(it.get("id") or "")}
        else:
            key = str(it.get("key") or "").lower()
            target = {s["id"] for s in sections if key == "all" or group_of(s) == key}
        if not target & {s["id"] for s in sections}:
            raise DraftError("no such section or group")
        for ds in doc.get("sections") or []:
            if not isinstance(ds, dict):
                continue
            a = anchor_claim({"key": ds.get("section_id"), "t0": ds.get("t0"), "t1": ds.get("t1")}, sections, roles)
            if target & set(a["section_ids"]):
                removed += int(_clear(ds, dkey))
    return removed
