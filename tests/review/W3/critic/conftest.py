"""W3 completeness critic (R-CONTRACT lens, "the video agent"). These tests read the integrator's real-song output
folders out/_wip/integrator/<slug> (mvh analyze --profile max, docs/SEAMS.md) and skip when a folder is absent.
They use only the folder itself (events, meta, curves through lib/mvh_load.py), print numbers only and never lyric
text. Each test is the evidence of one finding in docs/review/W3-completeness.md."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
RUNS = REPO / "out" / "_wip" / "integrator"


class Folder:
    def __init__(self, path: Path):
        self.path = path
        self._lib = None

    def json(self, rel: str):
        with open(self.path / rel, encoding="utf-8") as fh:
            return json.load(fh)

    def events(self, name: str) -> list[dict]:
        for rel in (f"events/{name}.json", f"lipsync/{name}.json"):
            if (self.path / rel).is_file():
                return self.json(rel)["items"]
        return []

    def song(self):
        """The folder's own copy of lib/mvh_load.py, loaded under a private module name."""
        if self._lib is None:
            name = f"_w3c_mvh_load_{self.path.name.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(name, self.path / "lib" / "mvh_load.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            self._lib = mod.load(str(self.path))
        return self._lib


@pytest.fixture
def real_folder():
    def get(slug: str) -> Folder:
        f = RUNS / slug
        if not (f / "manifest.json").is_file():
            pytest.skip(f"no integrator run for {slug} in {RUNS}")
        return Folder(f)

    return get
