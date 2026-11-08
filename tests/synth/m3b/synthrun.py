# ruff: noqa: E501  (long numeric tables / docstrings)
"""Run instruments -> notes -> vocals once on the synthetic fixture and cache the outputs (owner builder-m3b).

The cache key hashes the M3b stage sources and the fixture's .done.json, so the three unit-test folders (which the gate runs
as separate pytest processes) share one run. Real inference runs inside one machine-wide heavy slot.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests" / "contract" / "synth"
CACHE = REPO / "tests" / ".cache" / "m3b"
STAGES = ("instruments", "notes", "vocals")


def _key() -> str:
    h = hashlib.sha256()
    for st in STAGES:
        for p in sorted((REPO / "src" / "mvh" / "stages" / st).glob("*.py")):
            h.update(p.name.encode())
            h.update(p.read_bytes())
    for p in sorted(Path(__file__).parent.glob("*.py")):
        h.update(p.read_bytes())
    done = FIXTURE / ".done.json"
    if done.is_file():
        h.update(done.read_bytes())
    return h.hexdigest()[:16]


def synth_outputs() -> Path:
    """Folder with the three stages' outputs on tests/contract/synth (computed on first use)."""
    out = CACHE / f"synth-{_key()}"
    if (out / "_done.json").is_file():
        return out
    from mvh.testing import heavy

    from .fxctx import run_stage

    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    results = {}
    with heavy("builder-m3b:pytest", threads=3):
        for st in STAGES:
            res, _ctx = run_stage(importlib.import_module(f"mvh.stages.{st}"), FIXTURE, tmp, roots=[tmp])
            results[st] = {"status": res.status, "summary": res.summary, "warnings": res.warnings,
                           "fallbacks": res.fallbacks}
    with open(tmp / "_done.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    for old in CACHE.glob("synth-*"):
        if old != tmp:
            shutil.rmtree(old, ignore_errors=True)
    tmp.rename(out)
    return out


def truth() -> dict:
    with open(FIXTURE / "_truth" / "truth.json", encoding="utf-8") as fh:
        return json.load(fh)
