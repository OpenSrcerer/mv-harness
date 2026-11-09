"""Shared helpers for the W4 R-ADVERSARY tests: where the newest max run of a song is."""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ROOTS = [REPO / "out" / "_wip" / "ud2-kick", REPO / "out" / "_wip" / "integrator"]
PERTURB = REPO / "out" / "_wip" / "r-adversary"
SYNTH_TRUTH = REPO / "tests" / "contract" / "synth" / "_truth" / "truth.json"


def _roots() -> list[Path]:
    extra = [Path(p) for p in os.environ.get("MVH_REVIEW_RUNS", "").split(os.pathsep) if p.strip()]
    return extra + ROOTS


def newest_run(slug: str) -> Path | None:
    cands = [r / slug for r in _roots() if (r / slug / "manifest.json").is_file()]
    if not cands:
        return None
    return max(cands, key=lambda p: (p / "manifest.json").stat().st_mtime)
