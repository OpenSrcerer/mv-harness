"""Run real stages (no models) on a finished song folder's cached upstreams into a temp dir (w4verify-analysis-r2).

``chain(song_dir, [(stage, params), ...], out_root)`` runs each stage with the runner's child entry point; a stage of the
chain reads the previous chain stages' outputs and every other upstream from the song folder's ``.cache`` (latest key).
Returns {stage: out_dir}.
"""

from __future__ import annotations

import json
from pathlib import Path


def _latest(cache: Path, stage: str) -> dict:
    with open(cache / stage / "latest.json", encoding="utf-8") as fh:
        lj = json.load(fh)
    k = lj["key"]
    if not (cache / stage / k).is_dir() and lj.get("pre_key") and (cache / stage / lj["pre_key"]).is_dir():
        k = lj["pre_key"]
    return {"dir": str(cache / stage / k), "key": k}


def has_cache(song: Path, stages=("drums", "choreo", "ingest")) -> bool:
    return (song / "manifest.json").is_file() and all((song / ".cache" / s / "latest.json").is_file() for s in stages)


def chain(song: Path, steps: list[tuple[str, dict]], out_root: Path, slug: str = "song") -> dict[str, Path]:
    from mvh.contract import catalog
    from mvh.runner.child import run_stage
    from mvh.runner.spec import load_stage_specs

    cache = song / ".cache"
    specs = load_stage_specs()
    with open(song / "meta" / "source.json", encoding="utf-8") as fh:
        src = json.load(fh)
    dev: dict[str, dict] = {}
    outs: dict[str, Path] = {}
    for stage, params in steps:
        spec = specs[stage]
        out = out_root / stage
        job = {
            "stage": stage, "stage_version": spec.version, "contract_version": catalog.CONTRACT_VERSION,
            "key": "0" * 64, "pre_key": "0" * 64, "params": dict(spec.resolved_params("max", params)), "device": "cpu",
            "upstream": {d: dev.get(d) or _latest(cache, d) for d in spec.deps}, "overrides": {},
            "timebase": {"n_samples": int(src["n_samples"]), "sample_rate": int(src["sample_rate"]),
                         "channels": int(src.get("channels", 2))},
            "song_dir": str(out_root / "song"), "http_dir": str(out_root / "http"), "slug": slug, "profile": "max",
            "threads": 3, "scratch": str(out_root / "scratch" / stage), "offline": True, "out_dir": str(out),
            "ingest_dir": _latest(cache, "ingest")["dir"],
        }
        run_stage(job)
        dev[stage] = {"dir": str(out), "key": "d" * 64}
        outs[stage] = out
    return outs


def items(folder: Path, name: str) -> list[dict]:
    p = Path(folder) / "events" / f"{name}.json"
    if not p.is_file():
        return []
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)["items"]
