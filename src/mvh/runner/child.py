"""One stage in its own process (PLAN §3.3): ``python -X utf8 -m mvh.runner.child <job.json>``.

The parent sets the thread variables in the child's environment, so they are in place before anything is
imported;
here ``threads.install`` adds the onnxruntime/torch/ctranslate2 post-import hooks, then the stage package is
imported
and ``run(ctx)`` is called. The child writes into the staging dir given by the job and finishes with
``_mvh/done.json`` (success) or ``_mvh/error.json`` (failure, exit 1). Timings are measured by the parent.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

__all__ = ["main", "run_stage"]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _logger(stage: str) -> logging.Logger:
    log = logging.getLogger(f"mvh.stage.{stage}")
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(f"[{stage}] %(levelname)s %(message)s"))
        log.addHandler(h)
    log.setLevel(logging.INFO)
    log.propagate = False
    return log


def _missing_required(
    spec, written: dict[str, Any], curves: dict[str, Any], matrices: dict[str, Any]
) -> list[str]:
    from mvh.contract import registry

    from .ctx import output_regex

    miss = []
    for o in spec.outputs:
        if not o.required:
            continue
        if o.kind == "curve":
            fid = next((k for k, f in registry.CURVE_FILES.items() if f.path == o.path), None)
            have = set(curves.get(fid, {}))
            for ch in o.channels:
                if "{" not in ch and ch not in have:
                    miss.append(f"curve {ch}")
            continue
        if o.kind == "matrix" and o.public:
            fid = next((k for k, f in registry.CURVE_FILES.items() if f.path == o.path), None)
            if fid not in matrices:
                miss.append(f"matrix {o.path}")
            continue
        if o.is_pattern:
            rx = output_regex(o.path, o.restrict)
            if not any(rx.match(r) for r in written):
                miss.append(o.path)
        elif o.path not in written:
            miss.append(o.path)
    return miss


def run_stage(job: dict[str, Any]) -> dict[str, Any]:
    from mvh.contract.catalog import CONTRACT_VERSION  # noqa: F401  (import check)

    from . import threads
    from .cache import canon, sha256_text
    from .ctx import StageCtx, StageWriter, provenance_block
    from .spec import StageError, StageResult

    threads.install(int(job["threads"]))
    stage = job["stage"]
    mod = importlib.import_module(f"mvh.stages.{stage}")
    spec = mod.STAGE
    out = Path(job["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    Path(job["scratch"]).mkdir(parents=True, exist_ok=True)
    log = _logger(stage)
    writer = StageWriter(spec, out, job)
    ctx = StageCtx(spec, job, writer, log)
    if _stubbed(stage):
        # W3 test seam: the runtime tests run the runner on the walking skeleton (every stage copying from
        # MVH_FIXTURE_DIR) now that the stages are real; MVH_STAGE_STUBS = "all" | "all-but-ingest" | a,b,c
        from mvh.contract.fixture import run_stub

        res = run_stub(ctx)
    else:
        res = mod.run(ctx)
    if isinstance(res, dict):
        res = StageResult(**res)
    if not isinstance(res, StageResult):
        raise StageError(f"{stage}.run must return a StageResult, got {type(res).__name__}")
    if res.status == "failed":
        raise StageError(f"{stage} reported status failed: " + "; ".join(res.warnings[:3]))
    miss = _missing_required(spec, writer.written, writer.curves_meta, writer.matrices)
    if miss:
        raise StageError(f"{stage} did not write required outputs: {', '.join(miss[:10])}")
    fallbacks = list(
        dict.fromkeys(list(res.fallbacks) + [f for w in ctx.worker_runs for f in w["fallbacks"]])
    )
    http_used = dict(sorted(ctx._http.used.items())) if ctx._http is not None else {}
    key = (
        job["pre_key"]
        if not (spec.network and http_used)
        else sha256_text(canon({"pre_key": job["pre_key"], "http": http_used}))
    )
    job2 = dict(job)
    job2["key"] = key
    job2["device"] = ctx.device
    prov = provenance_block(job2, res.provenance, fallbacks, res.confidence)
    writer.restamp(prov)
    outputs = {}
    for rel, info in sorted(writer.written.items()):
        p = out / rel
        if not p.is_file():
            continue
        outputs[rel] = {
            **{k: v for k, v in info.items() if v is not None},
            "sha256": _sha(p),
            "bytes": p.stat().st_size,
        }
    done = {
        "schema": "mvh/runner_done",
        "stage": stage,
        "stage_version": spec.version,
        "key": key,
        "pre_key": job["pre_key"],
        "status": res.status,
        "env": spec.env,
        "device": ctx.device,
        "threads": int(job["threads"]),
        "outputs": outputs,
        "curves": writer.curves_meta,
        "matrices": writer.matrices,
        "result": {
            "summary": res.summary,
            "warnings": [str(w) for w in res.warnings],
            "fallbacks": fallbacks,
            "confidence": res.confidence,
        },
        "provenance": prov,
        "http": http_used,
        "worker_runs": ctx.worker_runs,
        "key_inputs": job.get("key_inputs", {}),
    }
    p = out / "_mvh" / "done.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("done.json.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(done, fh, ensure_ascii=False, indent=1, allow_nan=False)
    tmp.replace(p)
    return done


def _stubbed(stage: str) -> bool:
    import os

    v = os.environ.get("MVH_STAGE_STUBS", "").strip()
    if not v:
        return False
    if v == "all":
        return True
    if v == "all-but-ingest":
        return stage != "ingest"
    return stage in {s.strip() for s in v.split(",")}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -X utf8 -m mvh.runner.child <job.json>", file=sys.stderr)
        return 3
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    with open(argv[0], encoding="utf-8") as fh:
        job = json.load(fh)
    try:
        run_stage(job)
        return 0
    except BaseException as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        err = {"type": type(e).__name__, "message": str(e)[:1000]}
        try:
            p = Path(job["out_dir"]) / "_mvh" / "error.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(err, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
