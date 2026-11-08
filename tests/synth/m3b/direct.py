# ruff: noqa: E501  (long numeric tables / docstrings)
"""Run the M3b stages directly (no runner) on the synth fixture or real-song overlays. Owner builder-m3b.

    uv run --frozen --no-sync python -m tests.synth.m3b.direct <stages,comma> <slug> [<slug> ...]

Outputs go to out/_wip/builder-m3b/direct/<slug>/ (instruments first, so vocals can read its outputs). Prints timings.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

from mvh.testing import heavy

from .fxctx import run_stage

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out" / "_wip" / "builder-m3b" / "direct"


def fixture_of(slug: str) -> Path:
    if slug == "synth":
        return REPO / "tests" / "contract" / "synth"
    return REPO / "out" / "_wip" / "builder-m3b" / "fx" / slug


def main(argv: list[str]) -> int:
    stages = argv[0].split(",")
    times = {}
    for slug in argv[1:]:
        out = OUT / slug
        for st in stages:
            mod = importlib.import_module(f"mvh.stages.{st}")
            t0 = time.time()
            with heavy(f"builder-m3b:{st}", threads=3):  # real model inference: one machine-wide heavy slot
                res, _ctx = run_stage(mod, fixture_of(slug), out, roots=[out])
            dt = round(time.time() - t0, 1)
            times[f"{slug}/{st}"] = dt
            print(f"[direct] {slug} {st}: {res.status} {dt}s summary={json.dumps(res.summary)[:300]} "
                  f"warnings={res.warnings} fallbacks={res.fallbacks}", flush=True)
    with open(OUT / "timings.json", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(times) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
