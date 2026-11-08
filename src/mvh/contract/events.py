# ruff: noqa: E501  (long catalogue tables / docstrings)
"""Reference reader/writer for the event-file envelope (PLAN §4.1 events/*.json). Stdlib only.

Envelope: {schema, schema_version, name, kind: event|segment, fields{name: {unit, type}}, provenance, items[]}.
Writer rules (frozen):
* items sorted by t (stable: ties keep producer order); segments have d > 0 (d = 0 is allowed only for events);
* t and d rounded to 6 decimals (1 us); NaN/inf are invalid JSON: use null;
* UTF-8, ensure_ascii=False, LF line endings; one item per line (diff-friendly, deterministic).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .catalog import CONTRACT_VERSION, event_def

__all__ = ["EventFile", "make_envelope", "dumps_events", "read_events", "dumps_json", "round_time"]


@dataclass
class EventFile:
    name: str
    kind: str
    fields: dict[str, Any]
    items: list[dict[str, Any]]
    provenance: dict[str, Any] = field(default_factory=dict)
    schema: str = ""
    schema_version: str = CONTRACT_VERSION


def round_time(x: float | None) -> float | None:
    if x is None:
        return None
    if isinstance(x, float) and not math.isfinite(x):
        raise ValueError("times must be finite")
    return round(float(x), 6)


def _fields_of(name: str) -> dict[str, Any]:
    ed = event_def(name)
    return {f.name: {"unit": f.unit, "type": f.type} for f in ed.fields}


def make_envelope(name: str, items: Sequence[Mapping[str, Any]], provenance: Mapping[str, Any], *,
                  kind: str | None = None, fields: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a contract envelope for events ``name``; kind/fields default to the catalogue definition
    (extra fields a producer adds should be passed in ``fields`` so they are documented)."""
    ed = event_def(name)
    k = kind or ed.kind
    fl = _fields_of(name)
    fl.update(fields or {})
    out = []
    for it in items:
        d = dict(it)
        d["t"] = round_time(d["t"])
        if "d" in d and d["d"] is not None:
            d["d"] = round_time(d["d"])
        out.append(d)
    out.sort(key=lambda d: d["t"])  # stable
    return {"schema": "mvh/" + ed.schema_id, "schema_version": CONTRACT_VERSION, "name": name, "kind": k,
            "fields": fl, "provenance": dict(provenance), "items": out}


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n"


def dumps_events(env: Mapping[str, Any]) -> str:
    head = {k: v for k, v in env.items() if k != "items"}
    lines = json.dumps(head, ensure_ascii=False, indent=1, allow_nan=False)
    assert lines.endswith("}")
    items = env.get("items", [])
    body = ",\n".join("  " + json.dumps(it, ensure_ascii=False, separators=(",", ":"), allow_nan=False) for it in items)
    return lines[:-1].rstrip() + ',\n "items": [\n' + body + ("\n" if items else "") + " ]\n}\n"


def read_events(path: Path | str) -> EventFile:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return EventFile(d["name"], d["kind"], d.get("fields", {}), d.get("items", []), d.get("provenance", {}),
                     d.get("schema", ""), d.get("schema_version", ""))
