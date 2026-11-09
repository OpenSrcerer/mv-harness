"""W4 R-ADVERSARY (PLAN §11: try to refute "it works"). docs/review/W4-adversary.md has the findings.

The real-song tests read the newest finished max-profile folder of a song (``manifest.json`` mtime) among
``$MVH_REVIEW_RUNS`` (os.pathsep-separated roots, checked first), ``out/_wip/ud2-kick`` (the post-UD2 runs) and
``out/_wip/integrator``; they skip when no folder exists. The perturbation tests read ``out/_wip/r-adversary/<name>``
(made by ``out/_wip/r-adversary/run_queue.ps1``) and skip when absent. They read files only (fast), print numbers
only and never lyric text.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from w4a_support import PERTURB, SYNTH_TRUTH, _roots, newest_run


class Folder:
    def __init__(self, path: Path):
        self.path = path
        self._lib = None

    def json(self, rel: str):
        with open(self.path / rel, encoding="utf-8") as fh:
            return json.load(fh)

    def has(self, rel: str) -> bool:
        return (self.path / rel).is_file()

    def events(self, name: str) -> list[dict]:
        for rel in (f"events/{name}.json", f"lipsync/{name}.json"):
            if (self.path / rel).is_file():
                return self.json(rel)["items"]
        return []

    def song(self):
        """The folder's own lib/mvh_load.py, loaded under a private module name."""
        if self._lib is None:
            name = f"_w4adv_mvh_load_{self.path.parent.name}_{self.path.name}".replace("-", "_")
            spec = importlib.util.spec_from_file_location(name, self.path / "lib" / "mvh_load.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            self._lib = mod.load(str(self.path))
        return self._lib


@pytest.fixture
def real_folder():
    def get(slug: str) -> Folder:
        f = newest_run(slug)
        if f is None:
            pytest.skip(f"no max run for {slug} under {[str(r) for r in _roots()]}")
        return Folder(f)

    return get


@pytest.fixture
def perturbed():
    def get(name: str) -> Folder:
        f = PERTURB / name
        if not (f / "manifest.json").is_file():
            pytest.skip(f"no perturbation run {f} (out/_wip/r-adversary/run_queue.ps1)")
        return Folder(f)

    return get


@pytest.fixture(scope="session")
def synth_truth() -> dict:
    with open(SYNTH_TRUTH, encoding="utf-8") as fh:
        return json.load(fh)
