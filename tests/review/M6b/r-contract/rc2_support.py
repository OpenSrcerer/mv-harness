# ruff: noqa: E501
"""Helpers for the R-CONTRACT round-2 review tests of M6b. Synthetic fixture only (tests/contract/synth: invented
lyrics), so nothing here prints real lyric text. The meaning stage's ``build()`` runs in-process on a dict-backed
Source, which lets a test remove upstream files (voices, lyrics) without touching the fixture."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest

from mvh.stages.meaning.source import Source

ROOT = Path(__file__).resolve().parents[4]
SYNTH = ROOT / "tests" / "contract" / "synth"

FILES = ("meta/identity.json", "lyrics/lyrics.json", "meta/mood.json", "meta/vocal_range.json", "meta/instruments.json",
         "meta/voices.json", "meta/source.json", "meta/tempo.json", "meta/key.json", "meta/loudness.json")
EVENTS = ("sections", "edm_roles", "mood", "voice_spans", "moments", "cues", "dynamics", "instruments", "vocal_phrases",
          "hit_points", "counts", "grooves", "holds", "chords")


class DictSource(Source):
    def __init__(self, files: dict[str, Any], events: dict[str, list]):
        super().__init__()
        self.files, self.ev = files, events

    def _json(self, rel):
        return copy.deepcopy(self.files.get(rel))

    def _text(self, rel):
        return None

    def _event_file(self, name):
        if name not in self.ev:
            return None
        return {"name": name, "kind": "segment", "fields": {}, "items": copy.deepcopy(self.ev[name])}


def _load(rel: str) -> Any:
    with open(SYNTH / rel, encoding="utf-8") as fh:
        return json.load(fh)


def source(drop_files: tuple[str, ...] = (), drop_events: tuple[str, ...] = (),
           files_over: dict[str, Any] | None = None, events_over: dict[str, list] | None = None) -> DictSource:
    if not (SYNTH / ".done.json").is_file():
        pytest.skip("tests/contract/synth is not built")
    files = {r: _load(r) for r in FILES if (SYNTH / r).is_file() and r not in drop_files}
    events = {n: _load(f"events/{n}.json")["items"] for n in EVENTS
              if (SYNTH / "events" / f"{n}.json").is_file() and n not in drop_events}
    files.update(files_over or {})
    events.update(events_over or {})
    return DictSource(files, events)


def authored() -> dict[str, Any]:
    return _load("meaning/authored.json")


def template_of(interview: str, fenced: bool = True) -> str:
    """The YAML template block interview.md prints (with or without its markdown fence)."""
    m = re.search(r"```yaml\n(.*?)```", interview, re.S)
    assert m, "interview.md has no ```yaml template"
    return m.group(0) if fenced else m.group(1)
