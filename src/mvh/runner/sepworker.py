"""Launching the sep worker (PLAN §3.3 "Worker protocol", docs/spike/sep.md §6, CONTRACT D29).

``envs/sep/.venv-<variant>/Scripts/python.exe -X utf8 -m mvh.worker <stage> job.json`` with
``PYTHONPATH=<repo>/src``,
the ffmpeg bin first on PATH, the thread variables and ``HF_HUB_OFFLINE=1``. The process runs in the
kill-on-close
Job Object. The default variant order is ``rocm`` then ``cpu`` (``MVH_SEP_VARIANTS=cpu`` or config.json
``"sep_variants": ["cpu"]`` or the stage param ``variant_order`` change it); a variant whose venv is missing
is skipped.

job.json (schema ``mvh/worker_job``, informal):
  {schema, stage, stage_version, variant, device, threads, params, inputs{name: abs wav path},
   models{id: {lock path: abs path}}, out_dir, scratch, offline}
The worker writes float32 WAVs (and any JSON) into ``out_dir`` plus ``result.json`` (``mvh/stage_result``).
The parent (the stage's ``run`` through ``ctx.worker``) does the FLAC encoding, validation, provenance and
caching.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from mvh.io import proc
from mvh.io.ffmpeg import child_env
from mvh.io.paths import config, repo_root
from mvh.io.wav import read_wav, write_wav

from . import locks
from .spec import Audio, StageError
from .threads import thread_env

__all__ = ["WorkerResult", "sep_python", "variant_order", "run_worker", "DEFAULT_VARIANTS"]

DEFAULT_VARIANTS = ("rocm", "cpu")


def sep_python(variant: str, root: Path | None = None) -> Path | None:
    """The sep venv interpreter of a variant. W0 built ``envs/sep/.venv-<variant>``;
    ``envs/sep/<variant>/.venv`` is
    also accepted (PLAN wording). None when neither exists."""
    r = root or repo_root()
    for p in (
        r / "envs" / "sep" / f".venv-{variant}" / "Scripts" / "python.exe",
        r / "envs" / "sep" / variant / ".venv" / "Scripts" / "python.exe",
        r / "envs" / "sep" / f".venv-{variant}" / "bin" / "python",
    ):
        if p.is_file():
            return p
    return None


def variant_order(param: Sequence[str] | None = None) -> list[str]:
    env = os.environ.get("MVH_SEP_VARIANTS")
    if env:
        order = [v.strip() for v in env.split(",") if v.strip()]
    elif isinstance(config().get("sep_variants"), list):
        order = [str(v) for v in config()["sep_variants"]]
    elif param:
        order = list(param)
    else:
        order = list(DEFAULT_VARIANTS)
    return [
        v for v in order if v in DEFAULT_VARIANTS
    ]  # 'htdemucs' etc. are stage-level fallbacks, not workers


@dataclass
class WorkerResult:
    variant: str
    device: str
    out_dir: Path
    result: dict[str, Any]
    fallbacks: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def outputs(self) -> dict[str, Path]:
        return {o["path"]: self.out_dir / o["path"] for o in self.result.get("outputs", [])}

    def read(self, rel: str) -> Audio:
        x, sr = read_wav(self.out_dir / rel)
        return Audio(x, sr, self.out_dir / rel)


def _validate_result(res: Any) -> list[str]:
    try:
        from mvh.contract import schemas

        return schemas.validate(res, "mvh/envelope/stage_result")
    except ImportError:  # jsonschema missing: minimal check
        return (
            [] if isinstance(res, dict) and res.get("schema") == "mvh/stage_result" else ["bad result.json"]
        )


def _materialise_inputs(inputs: Mapping[str, Any], folder: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    folder.mkdir(parents=True, exist_ok=True)
    for name, v in inputs.items():
        if isinstance(v, (str, os.PathLike)):
            out[name] = str(Path(v).resolve())
            continue
        if isinstance(v, Audio):
            samples, sr = v.samples, v.sr
        elif isinstance(v, tuple) and len(v) == 2:
            samples, sr = v
        else:
            raise StageError(f"worker input {name!r} must be a path, an Audio or (samples, sr)")
        p = folder / f"{name}.wav"
        write_wav(p, np.asarray(samples, dtype=np.float32), int(sr))
        out[name] = str(p)
    return out


def run_worker(
    stage: str,
    *,
    stage_version: str,
    params: Mapping[str, Any],
    inputs: Mapping[str, Any],
    scratch: Path,
    threads: int,
    models: Mapping[str, Mapping[str, str]] | None = None,
    variants: Sequence[str] | None = None,
    offline: bool = True,
    timeout: float | None = None,
    hold_slot: bool = True,
    log: Callable[[str], None] | None = None,
    root: Path | None = None,
) -> WorkerResult:
    """Run ``mvh.worker <stage>`` in the first sep variant that succeeds (rocm, then cpu)."""
    log = log or (lambda s: None)
    order = list(variants) if variants else variant_order(params.get("variant_order"))
    if not order:
        raise StageError("no sep worker variant configured")
    scratch = Path(scratch)
    in_paths = _materialise_inputs(inputs, scratch / "worker-in")
    attempts: list[dict[str, Any]] = []
    t0 = time.time()
    for i, variant in enumerate(order):
        py = sep_python(variant, root)
        if py is None:
            attempts.append({"variant": variant, "error": "venv missing"})
            log(f"sep worker: variant {variant} has no venv, skipped")
            continue
        wdir = scratch / f"worker-{variant}"
        out_dir = wdir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        n = max(1, min(int(threads), locks.MAX_THREADS))
        job = {
            "schema": "mvh/worker_job",
            "stage": stage,
            "stage_version": stage_version,
            "variant": variant,
            "device": "rocm" if variant == "rocm" else "cpu",
            "threads": n,
            "params": dict(params),
            "inputs": in_paths,
            "models": {k: dict(v) for k, v in (models or {}).items()},
            "out_dir": str(out_dir),
            "scratch": str(wdir),
            "offline": bool(offline),
        }
        job_path = wdir / "job.json"
        with open(job_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(job, fh, ensure_ascii=False, indent=1)
        env = child_env(None, **thread_env(n))
        env["PYTHONPATH"] = str((root or repo_root()) / "src")
        env["HF_HUB_OFFLINE"] = "1"
        from . import models as _models

        env["AUDIO_SEPARATOR_MODEL_DIR"] = str(_models.separator_dir())  # overrides model_file_dir; set, never inherit
        if variant == "rocm":
            # bit-reproducible rocBLAS GEMMs for every sep-env GPU stage (mvh.sep.determinism; W3 fixer-m3a-r4 CR)
            env.setdefault("ROCBLAS_USE_HIPBLASLT", "0")
        for v in ("VIRTUAL_ENV", "PYTHONHOME", "UV_PROJECT_ENVIRONMENT"):
            env.pop(v, None)
        slot = locks.acquire(f"mvh:{stage}:{variant}", gpu=(variant == "rocm")) if hold_slot else None
        try:
            logf = wdir / "worker.log"
            with open(logf, "w", encoding="utf-8", newline="\n") as lf:
                p = proc.popen(
                    [py, "-X", "utf8", "-m", "mvh.worker", stage, job_path],
                    env=env,
                    cwd=wdir,
                    stdout=lf,
                    stderr=lf,
                    stdin=subprocess.DEVNULL,
                )
                try:
                    rc = p.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                    rc = -9
        finally:
            if slot is not None:
                slot.release()
        res_path = out_dir / "result.json"
        res = None
        if res_path.is_file():
            try:
                with open(res_path, encoding="utf-8") as fh:
                    res = json.load(fh)
            except ValueError:
                res = None
        errs = _validate_result(res) if res is not None else ["no result.json"]
        tail = ""
        try:
            tail = (wdir / "worker.log").read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            pass
        if rc == 0 and not errs and res.get("status") != "failed":
            fb = [f"sep:{variant}"] if i > 0 else []
            return WorkerResult(variant, job["device"], out_dir, res, fb, attempts, time.time() - t0)
        attempts.append(
            {
                "variant": variant,
                "returncode": rc,
                "errors": errs[:5],
                "warnings": (res or {}).get("warnings", [])[:5],
                "log_tail": tail,
            }
        )
        log(f"sep worker: variant {variant} failed (exit {rc}); trying the next variant")
    raise StageError(
        f"sep worker failed in every variant {order}: "
        + "; ".join(
            f"{a['variant']}: {a.get('error') or a.get('errors') or a.get('returncode')}" for a in attempts
        )
    )
