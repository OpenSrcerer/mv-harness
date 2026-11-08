"""``mvh validate``: schema-validate a song folder (PLAN §4.6). Also run on each stage's outputs after it
finishes.

Checks: manifest.json, run.json, curves/index.json (and the byte layout of every curve file), every JSON
file the
manifest lists (events by their ``schema`` field, documents by the catalogue), the tables (rows coerced and
validated),
overrides.json and meaning/authored.json when present, and the token caps (manifest <= 3k, brief.md <= 4k
tokens,
estimated as characters / 4).
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from mvh.contract import catalog, schemas

__all__ = [
    "Report",
    "validate_files",
    "validate_folder",
    "schema_for",
    "MANIFEST_TOKEN_CAP",
    "BRIEF_TOKEN_CAP",
]

MANIFEST_TOKEN_CAP = 3000
BRIEF_TOKEN_CAP = 4000


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _pattern(path: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\\\{[a-z]+\\\}", r"[A-Za-z0-9_.-]+", re.escape(path)) + "$")


def schema_for(rel: str, obj: object = None) -> str | None:
    """The contract schema id of a song-folder JSON file (None when it has none)."""
    if isinstance(obj, dict):
        s = obj.get("schema")
        if isinstance(s, str) and s.startswith("mvh/events/"):
            return s
    for f in catalog.FILES + catalog.RUNNER_FILES:
        if f.schema and (f.path == rel or ("{" in f.path and _pattern(f.path).match(rel))):
            return "mvh/" + f.schema
    for e in catalog.EVENTS:
        if e.file == rel or ("{" in e.file and _pattern(e.file).match(rel)):
            return "mvh/" + e.schema_id
    return None


def _table_def(rel: str):
    for t in catalog.TABLES:
        if t.path == rel or ("{" in t.path and _pattern(t.path).match(rel)):
            return t
    return None


def _validate_table(p: Path, rel: str, tdef) -> list[str]:
    sch = schemas.load(tdef.schema)
    errs: list[str] = []
    with open(p, encoding="utf-8", newline="") as fh:
        text = fh.read()
    if text.startswith("﻿"):
        errs.append(f"{rel}: has a BOM")
    if "\r" in text:
        errs.append(f"{rel}: CRLF line endings")
    if tdef.sep == "\t":
        lines = [ln for ln in text.split("\n") if ln]
        head = lines[0].split("\t") if lines else []
        rows = [dict(zip(head, ln.split("\t"))) for ln in lines[1:]]
    else:
        rd = csv.DictReader(text.splitlines())
        head = list(rd.fieldnames or [])
        rows = list(rd)
    want = [c.name for c in tdef.columns]
    if head[: len(want)] != want:
        errs.append(f"{rel}: columns {head[: len(want)]} != {want}")
    for i, r in enumerate(rows[:100000]):
        e = schemas.validate(schemas.coerce_row(r, sch), tdef.schema)
        if e:
            errs.append(f"{rel} row {i + 1}: {e[0]}")
            if len(errs) > 5:
                break
    return errs


def validate_files(song_dir: Path, rels: Iterable[str]) -> list[str]:
    """Validate the given song-folder files; returns error strings."""
    song_dir = Path(song_dir)
    errs: list[str] = []
    for rel in rels:
        p = song_dir / rel
        if not p.is_file():
            errs.append(f"{rel}: missing")
            continue
        if rel.endswith(".json"):
            try:
                with open(p, encoding="utf-8") as fh:
                    obj = json.load(fh)
            except ValueError as e:
                errs.append(f"{rel}: invalid JSON ({e})")
                continue
            sid = schema_for(rel, obj)
            if sid:
                e = schemas.validate(obj, sid)
                errs += [f"{rel}: {m}" for m in e[:5]]
        elif rel.endswith((".csv", ".tsv")):
            t = _table_def(rel)
            if t is not None:
                errs += _validate_table(p, rel, t)
    return errs


def _check_curves(song_dir: Path, rep: Report) -> None:
    p = song_dir / "curves" / "index.json"
    if not p.is_file():
        rep.warnings.append("curves/index.json missing")
        return
    with open(p, encoding="utf-8") as fh:
        idx = json.load(fh)
    rep.errors += [f"curves/index.json: {m}" for m in schemas.validate(idx, "mvh/envelope/curves_index")[:5]]
    for fid, f in idx.get("files", {}).items():
        fp = song_dir / f["path"]
        if not fp.is_file():
            rep.errors.append(f"{f['path']}: missing")
            continue
        item = 1 if f["dtype"] == "u8" else 4
        want = f["n_frames"] * f["n_channels"] * item
        if fp.stat().st_size != want:
            rep.errors.append(f"{f['path']}: {fp.stat().st_size} bytes, index says {want}")
        rep.checked += 1
    for c in idx.get("channels", []):
        f = idx["files"].get(c["file"])
        if f is None:
            rep.errors.append(f"curve {c['id']}: unknown file {c['file']}")
            continue
        if (
            f["layout"] == "column-major"
            and c["offset_bytes"] + 4 * c["n"] > 4 * f["n_frames"] * f["n_channels"]
        ):
            rep.errors.append(f"curve {c['id']}: offset beyond the file")


def validate_folder(song_dir: Path | str) -> Report:
    song_dir = Path(song_dir)
    rep = Report()
    mp = song_dir / "manifest.json"
    files: list[str] = []
    if not mp.is_file():
        rep.errors.append("manifest.json missing")
    else:
        with open(mp, encoding="utf-8") as fh:
            txt = fh.read()
        man = json.loads(txt)
        rep.errors += [f"manifest.json: {m}" for m in schemas.validate(man, "mvh/envelope/manifest")[:10]]
        if len(txt) / 4 > MANIFEST_TOKEN_CAP:
            rep.errors.append(f"manifest.json: ~{len(txt) // 4} tokens > {MANIFEST_TOKEN_CAP}")
        files = [f["path"] for f in man.get("files", []) if isinstance(f, dict) and "path" in f]
        rep.checked += 1
    rp = song_dir / "run.json"
    if rp.is_file():
        with open(rp, encoding="utf-8") as fh:
            rep.errors += [f"run.json: {m}" for m in schemas.validate(json.load(fh), "mvh/envelope/run")[:5]]
        rep.checked += 1
    else:
        rep.warnings.append("run.json missing")
    _check_curves(song_dir, rep)
    skip = {"manifest.json", "run.json", "curves/index.json"}
    todo = [f for f in files if f not in skip and not f.startswith("schema/")]
    rep.errors += validate_files(song_dir, todo)
    rep.checked += len(todo)
    for extra, sid in (
        ("overrides.json", "mvh/envelope/overrides"),
        ("meaning/authored.json", "mvh/files/meaning"),
    ):
        p = song_dir / extra
        if p.is_file() and extra not in files:
            try:
                with open(p, encoding="utf-8-sig") as fh:
                    rep.errors += [f"{extra}: {m}" for m in schemas.validate(json.load(fh), sid)[:5]]
            except ValueError as e:
                rep.errors.append(f"{extra}: invalid JSON ({e})")
            rep.checked += 1
    bp = song_dir / "brief.md"
    if bp.is_file():
        with open(bp, encoding="utf-8") as fh:
            n = len(fh.read()) / 4
        if n > BRIEF_TOKEN_CAP:
            rep.errors.append(f"brief.md: ~{int(n)} tokens > {BRIEF_TOKEN_CAP}")
    return rep
