"""Shared helpers for the W4 analysis verifier (w4verify-analysis-r1, round 2: w4verify-analysis-r2): where the runs are.

* ``RUNS`` (``$W4VA_RUNS`` or ``out/_wip/w4verify-analysis-r2``): round 2's fresh max-profile analyses, made from audio by
  ``out/_wip/w4verify-analysis-r2/run_queue.ps1`` from ``inputs/`` (ffmpeg ``volume=`` copies of real songs: MEGAFAUNA
  -20 dB, Versatile -12 dB, Jeremy -6 dB; the synthetic truth flac).
* ``BASE`` (``$W4VA_BASE`` or ``out/_wip/w4fix-analysis-r2``): the fixer's re-analysed folders on the current code: the
  unperturbed reference of each song, plus the fixer's re-analyses of round 1's perturbed inputs (megafauna_gm12,
  jeremy_gm12, synth_tempo110, synth_tempo95, synth_sr32, newton_acap, synth_acap).
  ``run(name)`` looks in RUNS first, then in BASE (round 1's names that round 2 did not re-run from scratch).

Round 1 (``out/_wip/w4verify-analysis-r1`` / ``out/_wip/w4fix-analysis``) ran the pre-fix code; point the variables there
to reproduce its failures. Tests read files only, print numbers only (never lyric text) and skip when a folder is absent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
RUNS = Path(os.environ.get("W4VA_RUNS") or REPO / "out" / "_wip" / "w4verify-analysis-r2")
BASE = Path(os.environ.get("W4VA_BASE") or REPO / "out" / "_wip" / "w4fix-analysis-r2")
SYNTH_TRUTH = REPO / "tests" / "contract" / "synth" / "_truth" / "truth.json"

# (song, perturbed run): round 1's -12 dB copies (re-analysed by the fixer on the current code) and round 2's fresh
# analyses of other gains on three songs (Versatile was never part of the fixer's checks)
GAIN_PAIRS = [("megafauna", "megafauna_gm12"), ("jeremy", "jeremy_gm12"), ("megafauna", "megafauna_gm20"),
              ("versatile", "versatile_gm12"), ("jeremy", "jeremy_gm6")]
GAIN_IDS = [g for _, g in GAIN_PAIRS]

TRUTH_LABELS = ["intro", "verse", "chorus", "bridge", "chorus", "outro"]
TRUTH_T = [1.0, 9.0, 17.0, 25.0, 34.5, 50.5]


class Folder:
    def __init__(self, path: Path):
        self.path = path

    def json(self, rel: str):
        with open(self.path / rel, encoding="utf-8") as fh:
            return json.load(fh)

    def has(self, rel: str) -> bool:
        return (self.path / rel).is_file()

    def events(self, name: str) -> list[dict]:
        p = self.path / "events" / f"{name}.json"
        if not p.is_file():
            return []
        return self.json(f"events/{name}.json")["items"]

    def sections(self) -> list[tuple[str, float]]:
        return [(s["label"], float(s["t"])) for s in self.events("sections")]

    def edm(self) -> list[tuple[str, float]]:
        return [(e["role"], float(e["t"])) for e in self.events("edm_roles")]


def folder(root: Path, name: str) -> Folder:
    f = root / name
    if not (f / "manifest.json").is_file():
        pytest.skip(f"no finished run {f}")
    return Folder(f)


def run(name: str) -> Folder:
    if (RUNS / name / "manifest.json").is_file() or not (BASE / name / "manifest.json").is_file():
        return folder(RUNS, name)
    return folder(BASE, name)


def base(slug: str) -> Folder:
    return folder(BASE, slug)


def truth() -> dict:
    with open(SYNTH_TRUTH, encoding="utf-8") as fh:
        return json.load(fh)
