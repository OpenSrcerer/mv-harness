"""Shared helpers for the R-WORDS review tests of M6b (meaning, brief). Synthetic fixture only
(tests/contract/synth, invented lyrics), so nothing here prints real lyric text."""
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


def synth_parts() -> tuple[dict[str, Any], dict[str, list]]:
    if not (SYNTH / ".done.json").is_file():
        pytest.skip("tests/contract/synth is not built")
    files = {r: _load(r) for r in FILES if (SYNTH / r).is_file()}
    events = {n: _load(f"events/{n}.json")["items"] for n in EVENTS if (SYNTH / "events" / f"{n}.json").is_file()}
    return files, events


def source(files_over: dict[str, Any] | None = None, events_over: dict[str, list] | None = None) -> DictSource:
    files, events = synth_parts()
    files = {**copy.deepcopy(files), **(files_over or {})}
    events = {**copy.deepcopy(events), **(events_over or {})}
    return DictSource(files, events)


def authored() -> dict[str, Any]:
    return _load("meaning/authored.json")


def brief_for(meaning_res: dict[str, Any]) -> str:
    """Render brief.md from the synthetic upstream plus the meaning stage's build() result."""
    from mvh.stages.brief.build import gather, render_brief

    over = {"meaning/meaning.json": meaning_res["meaning"], "meaning/orphans.json": {"orphans": meaning_res["orphans"]}}
    ev_over = {"singing": meaning_res["singing"]}
    d = gather(source(over, ev_over))
    text, _info = render_brief(d)
    return text


def ngrams(text: str, n: int) -> set[str]:
    w = re.findall(r"[\w']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}
