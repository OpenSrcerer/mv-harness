"""The sep worker entry point (PLAN §3.3 "Worker protocol", CONTRACT D29).

    <sep venv>/python.exe -X utf8 -m mvh.worker <stage> <job.json>

Imports only the stdlib and numpy at module level (the sep env has no jsonschema, httpx, ...). The worker only
runs inference: it reads the float32 WAVs listed in ``job["inputs"]``, writes float32 WAVs (and small JSON
files)
into ``job["out_dir"]`` and finishes with ``out_dir/result.json`` (schema ``mvh/stage_result``). The parent
encodes,
validates, records provenance and caches.

Handlers: ``mvh.stages.<stage>.worker.run_job(job: dict, out_dir: Path) -> dict`` (status, summary, warnings,
fallbacks, provenance, confidence; all optional), or a built-in one: ``_echo`` (tests: copies each input
scaled by
``params.gain``, optionally reports torch/cuda when ``params.probe_torch``).
Exit codes: 0 ok, 2 handler failed (result.json says why), 3 bad invocation.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

__all__ = ["main", "BUILTIN", "write_result"]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _kind(p: Path) -> str:
    return {".wav": "audio", ".flac": "audio", ".json": "json", ".txt": "text", ".mid": "midi"}.get(
        p.suffix.lower(), "text"
    )


def write_result(job: dict[str, Any], out: dict[str, Any], status: str | None = None) -> dict[str, Any]:
    out_dir = Path(job["out_dir"])
    files = sorted(
        p
        for p in out_dir.rglob("*")
        if p.is_file() and p.name != "result.json" and not p.name.endswith(".tmp")
    )
    res = {
        "schema": "mvh/stage_result",
        "stage": str(job.get("stage", "")),
        "stage_version": str(job.get("stage_version") or "0.0.0"),
        "status": status or str(out.get("status", "ok")),
        "outputs": [
            {
                "path": p.relative_to(out_dir).as_posix(),
                "kind": _kind(p),
                "sha256": _sha(p),
                "bytes": p.stat().st_size,
            }
            for p in files
        ],
        "summary": dict(out.get("summary", {})),
        "warnings": [str(w) for w in out.get("warnings", [])],
        "fallbacks": [str(f) for f in out.get("fallbacks", [])],
    }
    if out.get("confidence") is not None:
        res["confidence"] = float(out["confidence"])
    prov = dict(out.get("provenance", {}))
    prov.setdefault("device", job.get("device"))
    prov.setdefault("variant", job.get("variant"))
    res["provenance"] = prov
    tmp = out_dir / "result.json.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, allow_nan=False)
    os.replace(tmp, out_dir / "result.json")
    return res


# ---------------------------------------------------------------------------------------------- built-ins
def _echo(job: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    import numpy as np

    from mvh.io.wav import read_wav, write_wav

    gain = float(job.get("params", {}).get("gain", 1.0))
    frames = {}
    for name, path in sorted(job.get("inputs", {}).items()):
        x, sr = read_wav(path)
        write_wav(out_dir / f"{name}.wav", (x * np.float32(gain)).astype(np.float32), sr)
        frames[name] = int(x.shape[1])
    summary: dict[str, Any] = {
        "inputs": sorted(frames),
        "frames": frames,
        "threads": int(job.get("threads", 0)),
        "omp": os.environ.get("OMP_NUM_THREADS"),
        "python": sys.version.split()[0],
        "ffmpeg_first_on_path": _ffmpeg_first(),
    }
    if job.get("params", {}).get("probe_torch"):
        import torch  # sep env only

        summary["torch"] = torch.__version__
        summary["cuda"] = bool(torch.cuda.is_available())
        summary["torch_threads"] = int(torch.get_num_threads())
    if job.get("params", {}).get("fail"):
        raise RuntimeError("echo asked to fail")
    return {"status": "ok", "summary": summary}


def _ffmpeg_first() -> bool:
    first = (os.environ.get("PATH", "").split(os.pathsep) or [""])[0]
    return bool(first) and (Path(first) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")).is_file()


BUILTIN: dict[str, Callable[[dict[str, Any], Path], dict[str, Any]]] = {"_echo": _echo}


def _handler(stage: str) -> Callable[[dict[str, Any], Path], dict[str, Any]]:
    if stage in BUILTIN:
        return BUILTIN[stage]
    mod = importlib.import_module(f"mvh.stages.{stage}.worker")
    fn = getattr(mod, "run_job", None)
    if not callable(fn):
        raise RuntimeError(f"mvh.stages.{stage}.worker has no run_job(job, out_dir)")
    return fn


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: python -X utf8 -m mvh.worker <stage> <job.json>", file=sys.stderr)
        return 3
    stage, job_path = argv
    try:
        with open(job_path, encoding="utf-8") as fh:
            job = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"mvh.worker: cannot read {job_path}: {e}", file=sys.stderr)
        return 3
    job.setdefault("stage", stage)
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from mvh.runner import threads

        threads.install(int(job.get("threads") or os.environ.get("MVH_THREADS") or 1))
    except Exception:  # noqa: BLE001
        pass
    t0 = time.time()
    try:
        out = _handler(stage)(job, out_dir) or {}
    except Exception as e:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        write_result(job, {"warnings": [f"{type(e).__name__}: {str(e)[:300]}"]}, status="failed")
        return 2
    out.setdefault("summary", {})
    res = write_result(job, out)
    print(
        f"mvh.worker: {stage} {res['status']} in {time.time() - t0:.2f}s ({len(res['outputs'])} files)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
