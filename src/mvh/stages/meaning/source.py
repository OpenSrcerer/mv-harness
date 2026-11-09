"""Read-only data sources shared by the meaning, brief and frames stages.

Two implementations of one small interface:

* ``CtxSource(ctx)``     inside a stage run: files and events come from the declared upstream stages
                         (``ctx.upstream(producer)``); an upstream that is absent or did not write a file
                         reads as ``None`` (the stages degrade gracefully and flag it).
* ``FolderSource(dir)``  a finished song folder (``mvh brief --section``, ``mvh meaning``, tests).

Never logs file contents (lyrics stay local, NF5).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from mvh.contract import catalog

__all__ = ["Source", "CtxSource", "FolderSource", "producer_of_file"]


def producer_of_file(rel: str) -> str | None:
    """The stage that publishes ``rel`` (catalogue files and tables)."""
    for f in catalog.FILES:
        if f.path == rel:
            return f.stage
    for t in catalog.TABLES:
        if t.path == rel:
            return t.stage
    for e in catalog.EVENTS:
        if e.file == rel:
            return e.stage
    return None


class Source:
    """Interface: ``json(rel)``, ``events(name)`` (items or None), ``text(rel)``, ``table(rel)``,
    ``event_file(name)`` (the whole envelope or None), ``records()`` (stage -> done record), ``missing``."""

    def __init__(self) -> None:
        self.missing: list[str] = []  # what was asked for and absent (for QA flags)

    # ---------------------------------------------------------------- to implement
    def _json(self, rel: str) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    def _event_file(self, name: str) -> Mapping[str, Any] | None:  # pragma: no cover - interface
        raise NotImplementedError

    def _text(self, rel: str) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError

    def records(self) -> dict[str, Mapping[str, Any]]:  # pragma: no cover - interface
        return {}

    # ---------------------------------------------------------------- shared
    def json(self, rel: str) -> Any:
        try:
            v = self._json(rel)
        except (OSError, ValueError, RuntimeError, KeyError):
            v = None
        if v is None and rel not in self.missing:
            self.missing.append(rel)
        return v

    def event_file(self, name: str) -> Mapping[str, Any] | None:
        try:
            v = self._event_file(name)
        except (OSError, ValueError, RuntimeError, KeyError):
            v = None
        if v is None and f"events:{name}" not in self.missing:
            self.missing.append(f"events:{name}")
        return v

    def events(self, name: str) -> list[dict[str, Any]] | None:
        ef = self.event_file(name)
        if ef is None:
            return None
        return [dict(i) for i in ef.get("items", [])]

    def text(self, rel: str) -> str | None:
        try:
            v = self._text(rel)
        except (OSError, ValueError, RuntimeError, KeyError):
            v = None
        if v is None and rel not in self.missing:
            self.missing.append(rel)
        return v

    def table(self, rel: str) -> list[dict[str, str]] | None:
        txt = self.text(rel)
        if txt is None:
            return None
        if rel.endswith(".tsv"):
            lines = [ln for ln in txt.split("\n") if ln]
            head = lines[0].split("\t") if lines else []
            return [dict(zip(head, ln.split("\t"))) for ln in lines[1:]]
        return list(csv.DictReader(txt.splitlines()))


class CtxSource(Source):
    """Reads through a stage ``ctx`` (declared deps only)."""

    def __init__(self, ctx: Any):
        super().__init__()
        self.ctx = ctx

    def _up(self, stage: str | None):
        if stage is None or stage not in self.ctx.spec.deps:
            return None
        try:
            return self.ctx.upstream(stage)
        except Exception:  # noqa: BLE001 - an absent upstream (no cache entry) reads as missing
            return None

    def _json(self, rel: str) -> Any:
        up = self._up(producer_of_file(rel))
        if up is None or not up.exists(rel):
            return None
        return up.json(rel)

    def _text(self, rel: str) -> str | None:
        up = self._up(producer_of_file(rel))
        if up is None or not up.exists(rel):
            return None
        return up.text(rel)

    def _event_file(self, name: str) -> Mapping[str, Any] | None:
        try:
            prod = catalog.producer_of_events(name)
        except KeyError:
            return None
        up = self._up(prod)
        if up is None:
            return None
        try:
            ef = up.events(name)
        except Exception:  # noqa: BLE001 - StageError: the upstream has no such events file
            return None
        return {"name": ef.name, "kind": ef.kind, "fields": ef.fields, "items": ef.items,
                "provenance": ef.provenance}

    def records(self) -> dict[str, Mapping[str, Any]]:
        out: dict[str, Mapping[str, Any]] = {}
        for d in self.ctx.spec.deps:
            up = self._up(d)
            if up is None:
                continue
            try:
                out[d] = up.record
            except (OSError, ValueError):
                continue
        return out


class FolderSource(Source):
    """Reads a finished song folder ``out/<slug>/``."""

    def __init__(self, song_dir: Path | str):
        super().__init__()
        self.dir = Path(song_dir)
        self._manifest: dict[str, Any] | None = None

    def manifest(self) -> dict[str, Any]:
        if self._manifest is None:
            p = self.dir / "manifest.json"
            self._manifest = _read_json(p) if p.is_file() else {}
        return self._manifest or {}

    def _json(self, rel: str) -> Any:
        p = self.dir / rel
        return _read_json(p) if p.is_file() else None

    def _text(self, rel: str) -> str | None:
        p = self.dir / rel
        if not p.is_file():
            return None
        with open(p, encoding="utf-8") as fh:
            return fh.read()

    def _event_file(self, name: str) -> Mapping[str, Any] | None:
        rel = None
        for f in self.manifest().get("files", []):
            if f.get("events") == name:
                rel = f["path"]
        if rel is None:
            try:
                ed = catalog.event_def(name)
                rel = ed.file.replace("{src}", name.split(".", 1)[1]) if "{src}" in ed.file else ed.file
            except KeyError:
                rel = f"events/{name}.json"
        p = self.dir / rel
        return _read_json(p) if p.is_file() else None


def _read_json(p: Path) -> Any:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)
