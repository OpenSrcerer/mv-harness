# ruff: noqa: E501  (long catalogue tables / docstrings)
"""Contract schemas: build (from catalog.py), load (from schema/), validate (main env only).

Schema ids are ``mvh/<group>/<name>`` and live at ``src/mvh/contract/schema/<group>/<name>.schema.json``
(copied to ``out/<slug>/schema/`` by the runner). ``$id`` = SCHEMA_BASE + "<group>/<name>.schema.json".
Groups: envelope, events, files, tables, intermediate.

Stdlib only at import time; ``validate`` imports jsonschema lazily (main env).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from . import catalog
from .catalog import CONTRACT_VERSION, ENVELOPE_SCHEMAS, EVENTS, FILE_SCHEMAS, SCHEMA_BASE, TABLES, obj, ref
from .ids import PITCHED_SOURCES

__all__ = ["SCHEMA_DIR", "DRAFT", "build_all", "schema_path", "load", "iter_schema_files", "validate", "registry",
           "coerce_row", "short_id"]

SCHEMA_DIR = Path(__file__).with_name("schema")
DRAFT = "https://json-schema.org/draft/2020-12/schema"


def short_id(schema_id: str) -> str:
    """'mvh/events/beats' -> 'events/beats' (accepts either form)."""
    return schema_id[4:] if schema_id.startswith("mvh/") else schema_id


def _wrap(sid: str, body: dict, title: str, description: str = "") -> dict:
    s = {"$schema": DRAFT, "$id": SCHEMA_BASE + sid + ".schema.json", "title": title, "x-contract-version": CONTRACT_VERSION}
    if description and "description" not in body:
        s["description"] = description
    s.update(copy.deepcopy(body))
    return s


def _events_schema(e: catalog.EventDef) -> dict:
    req = {f.name: f.schema for f in e.fields if f.required}
    opt = {f.name: f.schema for f in e.fields if not f.required}
    item = obj(req, opt)
    if e.name == "notes.{src}" or e.schema_id == "events/notes":
        name = {"type": "string", "pattern": r"^notes\.(" + "|".join(PITCHED_SOURCES) + r")$"}
    else:
        name = {"const": e.name}
    return {"allOf": [ref("envelope/events"),
                      {"properties": {"schema": {"const": "mvh/" + e.schema_id}, "name": name, "kind": {"const": e.kind},
                                      "items": {"type": "array", "items": item}}}]}


def _table_schema(t: catalog.TableDef) -> dict:
    req = {f.name: f.schema for f in t.columns if f.required}
    s = obj(req)
    s["x-columns"] = [f.name for f in t.columns]
    s["x-sep"] = t.sep
    s["x-format"] = "tsv" if t.sep == "\t" else "csv"
    s["description"] = (t.description + ". Row schema after coercion (schemas.coerce_row): empty cell = null, "
                        "booleans 0/1, UTF-8 without BOM, LF, header row first.")
    return s


def build_all() -> dict[str, dict]:
    """Every contract schema, keyed by short id ('events/beats')."""
    out: dict[str, dict] = {}
    for sid, body in ENVELOPE_SCHEMAS.items():
        out[sid] = _wrap(sid, body, "mvh/" + sid)
    seen = set()
    for e in EVENTS:
        if e.schema_id in seen:
            continue
        seen.add(e.schema_id)
        out[e.schema_id] = _wrap(e.schema_id, _events_schema(e), "mvh/" + e.schema_id, e.description)
    for sid, body in FILE_SCHEMAS.items():
        out[sid] = _wrap(sid, body, "mvh/" + sid)
    for t in TABLES:
        out[t.schema] = _wrap(t.schema, _table_schema(t), "mvh/" + t.schema)
    return out


def schema_path(schema_id: str, base: Path = SCHEMA_DIR) -> Path:
    return base / (short_id(schema_id) + ".schema.json")


def load(schema_id: str, base: Path = SCHEMA_DIR) -> dict:
    with open(schema_path(schema_id, base), encoding="utf-8") as fh:
        return json.load(fh)


def iter_schema_files(base: Path = SCHEMA_DIR) -> Iterator[Path]:
    yield from sorted(base.rglob("*.schema.json"))


def registry(base: Path = SCHEMA_DIR):
    """A referencing.Registry with every schema (main env: needs the 'referencing' package)."""
    from referencing import Registry, Resource

    res = []
    for p in iter_schema_files(base):
        with open(p, encoding="utf-8") as fh:
            s = json.load(fh)
        res.append((s["$id"], Resource.from_contents(s)))
    return Registry().with_resources(res)


_VALIDATORS: dict[tuple[str, str], Any] = {}


def validate(instance: Any, schema_id: str, base: Path = SCHEMA_DIR) -> list[str]:
    """Return a list of error messages (empty = valid). Main env only (jsonschema)."""
    from jsonschema import Draft202012Validator

    key = (str(base), short_id(schema_id))
    v = _VALIDATORS.get(key)
    if v is None:
        v = Draft202012Validator(load(schema_id, base), registry=registry(base))
        _VALIDATORS[key] = v
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {safe_message(e)}" for e in v.iter_errors(instance)]


def safe_message(e: Any) -> str:
    """A jsonschema error message that never quotes the offending value (NF5: lyric text must not reach
    errors, logs or reports). Numbers, booleans and null are harmless and keep jsonschema's wording; for
    strings, objects and arrays the message names only the rule."""
    if e.validator in ("required", "additionalProperties") or e.instance is None or isinstance(
            e.instance, (bool, int, float)):
        return e.message
    vv = repr(e.validator_value)
    if len(vv) > 80:
        vv = vv[:77] + "..."
    if e.validator == "type":
        return f"is not of type {vv}"
    return f"violates '{e.validator}' ({vv})"


def coerce_row(row: Mapping[str, str], table_schema: Mapping[str, Any]) -> dict[str, Any]:
    """Turn one CSV/TSV row (strings) into typed values following the table's row schema."""
    out: dict[str, Any] = {}
    props = table_schema.get("properties", {})
    for k, v in row.items():
        p = props.get(k, {})
        t = p.get("type", "string")
        types = t if isinstance(t, list) else [t]
        if v == "" and "null" in types:
            out[k] = None
        elif "boolean" in types:
            out[k] = {"1": True, "0": False, "true": True, "false": False}.get(v, v)
        elif "integer" in types:
            try:
                out[k] = int(v)
            except ValueError:
                out[k] = v
        elif "number" in types:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
        else:
            out[k] = v
    return out
