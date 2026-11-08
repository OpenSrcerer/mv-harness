"""overrides.json plumbing (PLAN §3.3 "Overrides", R19, CONTRACT D27).

``overrides.json`` (written by the viewer or by hand) is a user input: the runner never writes or deletes
it. Each
stage declares the override keys it reads (``StageSpec.override_keys``, ``"<section>.<field>"``); the subset
that is
set goes into that stage's cache key and into ``ctx.overrides``. The stage applies them at its defined point
and
records the applied ones in provenance (the runner defaults ``overrides_applied`` to every key it handed
over).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

__all__ = ["OverridesError", "load", "subset", "validate", "USER_INPUTS"]

#: song-folder files that are inputs, never written, overwritten or deleted by mvh analyze (PLAN §8,
# CONTRACT §1)
USER_INPUTS = ("overrides.json", "meaning/intent.md", "meaning/authored.json")


class OverridesError(ValueError):
    pass


def load(song_dir: Path) -> dict[str, Any]:
    p = Path(song_dir) / "overrides.json"
    if not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8-sig") as fh:
            d = json.load(fh)
    except ValueError as e:
        raise OverridesError(f"overrides.json is not valid JSON: {e}") from e
    if not isinstance(d, dict):
        raise OverridesError("overrides.json must be a JSON object")
    return d


def validate(d: Mapping[str, Any]) -> list[str]:
    from mvh.contract import schemas

    return schemas.validate(dict(d), "mvh/envelope/overrides")


def subset(d: Mapping[str, Any], keys: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """{'rhythm.bpm': 123.0, ...} for the declared keys that are set (absent = not set)."""
    out: dict[str, Any] = {}
    for k in keys:
        section, _, field = k.partition(".")
        sec = d.get(section)
        if isinstance(sec, Mapping) and field in sec and sec[field] is not None:
            out[k] = sec[field]
    return dict(sorted(out.items()))
