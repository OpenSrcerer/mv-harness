"""Shared fixtures for the meaning tests. Real-song tests are marked ``real`` and run only with ``-m real`` or
MVH_REAL_TESTS=1 (they read tests/contract/real-<slug>/, gitignored, and never print lyric text)."""
from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from mvh.stages.meaning.source import Source

ROOT = Path(__file__).resolve().parents[3]
SYNTH = ROOT / "tests" / "contract" / "synth"
REAL = {s: ROOT / "tests" / "contract" / f"real-{s}" for s in ("megafauna", "versatile", "jeremy", "newton-vs-nye")}


def pytest_configure(config):
    config.addinivalue_line("markers", "real: reads the real-song contract fixtures (opt-in: -m real or MVH_REAL_TESTS=1)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MVH_REAL_TESTS") == "1" or "real" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="real-song test: run with -m real or MVH_REAL_TESTS=1")
    for it in items:
        if "real" in it.keywords:
            it.add_marker(skip)


class DictSource(Source):
    """An in-memory Source: files {rel: obj}, events {name: items}."""

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


@pytest.fixture(scope="session")
def synth_source_parts() -> tuple[dict, dict]:
    if not (SYNTH / ".done.json").is_file():
        pytest.skip("tests/contract/synth is not built")
    files = {r: _load(r) for r in ("meta/identity.json", "lyrics/lyrics.json", "meta/mood.json", "meta/vocal_range.json",
                                   "meta/instruments.json", "meta/voices.json")}
    events = {n: _load(f"events/{n}.json")["items"] for n in ("sections", "edm_roles", "mood", "voice_spans", "moments", "cues")}
    return files, events


@pytest.fixture
def synth_source(synth_source_parts):
    files, events = synth_source_parts
    return lambda **over: DictSource({**files, **over.get("files", {})}, {**events, **over.get("events", {})})


@pytest.fixture(scope="session")
def truth() -> dict:
    if not (SYNTH / "_truth" / "truth.json").is_file():
        pytest.skip("synthetic truth missing")
    with open(SYNTH / "_truth" / "truth.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def synth_intent() -> str:
    with open(SYNTH / "meaning" / "intent.md", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="session")
def synth_authored() -> dict:
    return _load("meaning/authored.json")


def devrun(tmp: Path, fixture: Path, intent: bool = False, authored: bool = False):
    from mvh.stages.meaning.devrun import DevRun

    dr = DevRun(fixture, tmp)
    (dr.song_dir / "meaning").mkdir(parents=True, exist_ok=True)
    if intent:
        shutil.copyfile(fixture / "meaning" / "intent.md", dr.song_dir / "meaning" / "intent.md")
    if authored:
        shutil.copyfile(fixture / "meaning" / "authored.json", dr.song_dir / "meaning" / "authored.json")
    return dr


@pytest.fixture
def make_devrun(tmp_path):
    return lambda fixture=SYNTH, intent=False, authored=False: devrun(tmp_path / "dev", Path(fixture), intent, authored)
