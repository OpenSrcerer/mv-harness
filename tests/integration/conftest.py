"""W3 integration tests. Tests named test_real_* read the integrator's real-song outputs in out/_wip/integrator/<slug>
(made by `mvh analyze --profile max`, see docs/SEAMS.md) and skip when that folder is absent. They print numbers
only, never lyric text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "out" / "_wip" / "integrator"


class Song:
    def __init__(self, folder: Path):
        self.folder = folder

    def json(self, rel: str):
        with open(self.folder / rel, encoding="utf-8") as fh:
            return json.load(fh)

    def events(self, name: str) -> list[dict]:
        for rel in (f"events/{name}.json", f"lipsync/{name}.json"):
            if (self.folder / rel).is_file():
                return self.json(rel)["items"]
        return []


@pytest.fixture
def real_song():
    def get(slug: str) -> Song:
        f = RUNS / slug
        if not (f / "manifest.json").is_file():
            pytest.skip(f"no integrator run for {slug} in {RUNS}")
        return Song(f)

    return get
