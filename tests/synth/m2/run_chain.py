# ruff: noqa: E501
"""Run the M2 stages on a fixture folder without the runner (dev tool and real-song runs).

    python -m tests.synth.m2.run_chain <slug|synth> [--stages allin1,rhythm,structure,choreo,cues] [--threads 6]
           [--out out/_wip/builder-m2] [--reuse] [--param stage.key=value ...] [--override key=value ...]

Upstream stages not run here are read from tests/contract/<synth|real-slug>; each stage run here becomes an overlay
for the next. Heavy stages take a heavy slot (mvh.testing.heavy). Prints one JSON line per stage (summary, timing,
status, flags; never lyric text) and writes <out>/<slug>/run_chain.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ORDER = ["allin1", "rhythm", "structure", "choreo", "cues"]
HEAVY = {"allin1", "rhythm"}


def fixture_for(slug: str) -> Path:
    return REPO / "tests" / "contract" / ("synth" if slug == "synth" else f"real-{slug}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--stages", default=",".join(ORDER))
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--out", default=str(REPO / "out" / "_wip" / "builder-m2"))
    ap.add_argument("--reuse", action="store_true", help="reuse earlier outputs of stages not listed as overlays")
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--override", action="append", default=[])
    a = ap.parse_args(argv)
    from mvh.testing import apply_threads, heavy

    apply_threads(a.threads)
    from tests.synth.m2.ctx import RECORD, run_stage

    fx = fixture_for(a.slug)
    root = Path(a.out) / a.slug
    stages = [s for s in a.stages.split(",") if s]
    params: dict[str, dict] = {}
    for kv in a.param:
        k, v = kv.split("=", 1)
        st, key = k.split(".", 1)
        params.setdefault(st, {})[key] = json.loads(v) if v[:1] in "[{0123456789-tfn" else v
    overrides = {}
    for kv in a.override:
        k, v = kv.split("=", 1)
        overrides[k] = json.loads(v)
    overlays = {}
    if a.reuse:
        for s in ORDER:
            if (root / s / RECORD).is_file():
                overlays[s] = root / s
    report = {}
    for s in stages:
        t0 = time.perf_counter()
        kw = dict(overlays=dict(overlays), params=params.get(s), overrides=overrides, threads=a.threads, slug=a.slug)
        if s in HEAVY:
            with heavy("builder-m2", threads=a.threads):
                res, ctx, secs = run_stage(s, fx, root / s, **kw)
        else:
            res, ctx, secs = run_stage(s, fx, root / s, **kw)
        overlays[s] = root / s
        rec = {"stage": s, "status": res.status, "seconds": round(secs, 2), "wall": round(time.perf_counter() - t0, 2),
               "summary": res.summary, "fallbacks": res.fallbacks, "warnings": res.warnings[:6], "confidence": res.confidence}
        report[s] = rec
        print(json.dumps(rec, ensure_ascii=False, default=str), flush=True)
    with open(root / "run_chain.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
