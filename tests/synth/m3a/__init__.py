"""M3a test helpers: run one stage in-process (``mvh.runner.child.run_stage``) against fixture-shaped upstream folders.

``fixture_upstreams(fx)`` turns a contract fixture folder (tests/contract/synth or real-<slug>) into the upstream
cache dirs the runner would pass: ingest -> ``_intermediate/ingest`` (canonical.wav), separate_fast ->
``_intermediate/separate_fast``, separate_hq -> the fixture root (stems/, meta/separation.json).
``run_stage(stage, tmp, upstream, ingest_dir, params=..., timebase=...)`` returns (out_dir, done record);
the out_dir then serves as an upstream for the next stage (it carries ``_mvh/done.json``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"
TRUTH = SYNTH / "_truth" / "truth.json"


def real_fixture(slug: str) -> Path:
    return REPO / "tests" / "contract" / f"real-{slug}"


def truth() -> dict[str, Any]:
    with open(TRUTH, encoding="utf-8") as fh:
        return json.load(fh)


def fixture_upstreams(fx: Path) -> tuple[dict[str, str], str]:
    fx = Path(fx)
    ups = {
        "ingest": str(fx / "_intermediate" / "ingest"),
        "separate_fast": str(fx / "_intermediate" / "separate_fast"),
        "separate_hq": str(fx),
    }
    return ups, ups["ingest"]


def timebase_of(ingest_dir: str | Path) -> dict[str, int]:
    from mvh.io.wav import wav_info

    info = wav_info(Path(ingest_dir) / "canonical.wav")
    return {"n_samples": int(info["frames"]), "sample_rate": int(info["sample_rate"])}


def run_stage(stage: str, tmp: Path, upstream: Mapping[str, str], ingest_dir: str, *,
              params: Mapping[str, Any] | None = None, profile: str = "max", threads: int = 3,
              heavy_locks: bool = False) -> tuple[Path, dict[str, Any]]:
    import importlib

    from mvh.contract.catalog import CONTRACT_VERSION
    from mvh.runner.child import run_stage as _run

    spec = importlib.import_module(f"mvh.stages.{stage}").STAGE
    out = Path(tmp) / stage
    p = spec.resolved_params(profile, dict(params or {}))
    job = {
        "stage": stage, "stage_version": spec.version, "contract_version": CONTRACT_VERSION,
        "key": "0" * 64, "pre_key": "0" * 64, "slug": "test", "profile": profile, "threads": threads,
        "params": p, "out_dir": str(out), "scratch": str(Path(tmp) / f"{stage}-scratch"),
        "song_dir": str(Path(tmp) / "song"), "offline": True, "heavy_locks": heavy_locks,
        "upstream": {d: {"dir": str(upstream[d]), "key": "0" * 64} for d in spec.deps if d in upstream},
        "ingest_dir": str(ingest_dir), "timebase": timebase_of(ingest_dir), "device": "cpu",
    }
    done = _run(job)
    return out, done
