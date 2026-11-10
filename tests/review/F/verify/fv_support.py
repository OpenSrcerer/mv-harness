"""fverify (final fix pass verifier) helpers: read finished run folders. Numbers only, never lyric text."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
WIP = REPO / "out" / "_wip"
GAIN = WIP / "ffix-gain"  # the gain fixer's re-analyses (current code, separate_hq forced)
W4 = WIP / "w4fix-analysis-r2"  # the W4 reference runs (pre final-fix code)


def events(folder: Path, name: str) -> list[dict]:
    with open(folder / "events" / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)["items"]


def has(folder: Path, name: str) -> bool:
    return (folder / "events" / f"{name}.json").is_file()


def cover_iou(a: list[dict], b: list[dict], step: float = 0.05) -> float:
    dur = max([x["t"] + x["d"] for x in a + b] or [1.0]) + 1.0
    ts = np.arange(0.0, dur, step)

    def m(items):
        out = np.zeros(len(ts), bool)
        for x in items:
            out |= (ts >= x["t"]) & (ts < x["t"] + x["d"])
        return out

    ma, mb = m(a), m(b)
    return float((ma & mb).sum() / max(1, (ma | mb).sum()))
