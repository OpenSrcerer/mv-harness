# ruff: noqa: E501
"""A fixture-backed implementation of the stage Ctx for the M2 stages (tests and real-song runs).

* Upstream stages read from a contract fixture folder (``tests/contract/synth`` or ``tests/contract/real-<slug>``):
  public files at the folder root, cache-only files under ``_intermediate/<stage>/``, curves through
  ``curves/index.json``. Missing files raise ``StageError`` exactly like the runner's ``CacheUpstream``, so the
  stages' degraded paths are exercised (the real fixtures have no dynamics/drums/stem_activity outputs).
* ``overlays`` maps a stage name to an output folder written earlier by :func:`run_stage` (e.g. our own allin1 or
  rhythm run): those stages are read through the runner's ``CacheUpstream`` with the recorded writer state, so a
  chain allin1 -> rhythm -> structure -> choreo -> cues can be run without the runner.
* Writes go through the runner's real ``StageWriter`` (schema validation, declared outputs).
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from mvh.contract import catalog, curvefile, registry
from mvh.contract.catalog import CONTRACT_VERSION
from mvh.contract.events import read_events
from mvh.io.wav import read_wav
from mvh.runner.ctx import CacheUpstream, StageWriter
from mvh.runner.spec import Audio, Curve, StageError, UndeclaredDependency, load_stage_specs

__all__ = ["FixtureUpstream", "FixtureCtx", "run_stage", "RECORD"]

RECORD = "_m2_record.json"
_SPECS = None


def specs():
    global _SPECS
    if _SPECS is None:
        _SPECS = load_stage_specs()
    return _SPECS


class FixtureUpstream:
    def __init__(self, stage: str, fx: Path):
        self.stage = stage
        self.fx = Path(fx)
        self._index = None
        self._audio: dict = {}

    def _p(self, rel: str) -> Path:
        pub = self.fx / rel
        if pub.is_file():
            return pub
        return self.fx / "_intermediate" / self.stage / rel

    def path(self, rel: str) -> Path:
        p = self._p(rel)
        if not p.is_file():
            raise StageError(f"upstream {self.stage} has no {rel}")
        return p

    def exists(self, rel: str) -> bool:
        return self._p(rel).is_file()

    def json(self, rel: str) -> Any:
        with open(self.path(rel), encoding="utf-8") as fh:
            return json.load(fh)

    def text(self, rel: str) -> str:
        with open(self.path(rel), encoding="utf-8") as fh:
            return fh.read()

    def table(self, rel: str):
        import csv
        with open(self.path(rel), encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def events(self, name: str):
        try:
            ed = catalog.event_def(name)
        except KeyError as e:
            raise StageError(f"unknown events {name!r}") from e
        rel = ed.file.replace("{src}", name.split(".", 1)[1]) if "{src}" in ed.file else ed.file
        p = self.fx / rel
        if not p.is_file():
            raise StageError(f"upstream {self.stage} has no events {name!r}")
        return read_events(p)

    def _idx(self):
        if self._index is None:
            if not (self.fx / "curves/index.json").is_file():
                raise StageError("fixture has no curves/index.json")
            self._index = curvefile.read_index(self.fx)
        return self._index

    def curve(self, channel_id: str) -> Curve:
        idx = self._idx()
        try:
            v, meta = curvefile.read_channel(self.fx, idx, channel_id)
        except KeyError as e:
            raise StageError(f"upstream {self.stage} has no curve {channel_id!r}") from e
        return Curve(channel_id, v, float(meta.get("rate_hz", 100.0)), meta)

    def matrix(self, file_id: str):
        idx = self._idx()
        if file_id in idx.get("files", {}):
            return curvefile.read_matrix(self.fx, idx, file_id)
        raise StageError(f"upstream {self.stage} has no matrix {file_id!r}")

    def audio(self, rel: str, *, sr: int | None = None, mono: bool = False) -> Audio:
        k = (rel, sr, mono)
        if k in self._audio:
            return self._audio[k]
        p = self.path(rel)
        x = None
        if p.suffix.lower() == ".wav":
            try:
                x, native = read_wav(p)
            except ValueError:
                x = None
        if x is None or (sr is not None and sr != native):
            from mvh.io import audio as aio
            d = aio.decode(p, sr=sr, mono=mono)
            a = Audio(d.samples, d.sr, p)
        else:
            if mono and x.shape[0] > 1:
                x = x.mean(axis=0, dtype=np.float64).astype(np.float32)[None, :]
            a = Audio(x, native, p)
        self._audio[k] = a
        return a


class FixtureCtx:
    def __init__(self, stage: str, fixture: Path, out: Path, *, overlays: Mapping[str, Path] | None = None,
                 params: Mapping[str, Any] | None = None, overrides: Mapping[str, Any] | None = None,
                 threads: int = 3, slug: str = "song", log: logging.Logger | None = None):
        self.spec = specs()[stage]
        self.fixture = Path(fixture)
        self.out = Path(out)
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        self.scratch = self.out.parent / f".scratch-{stage}"
        if self.scratch.exists():
            shutil.rmtree(self.scratch, ignore_errors=True)
        self.scratch.mkdir(parents=True)
        self.overlays = {k: Path(v) for k, v in (overlays or {}).items()}
        self.params = self.spec.resolved_params("max", dict(params or {}))
        self.profile = "max"
        self.threads = threads
        self.device = "cpu"
        self.offline = True
        self.slug = slug
        self.log = log or logging.getLogger(f"m2.{stage}")
        self.overrides = {k: v for k, v in dict(overrides or {}).items() if k in self.spec.override_keys}
        src = self.fixture / "meta/source.json"
        tb = None
        if src.is_file():
            with open(src, encoding="utf-8") as fh:
                s = json.load(fh)
            tb = {"n_samples": int(s["n_samples"]), "sample_rate": int(s["sample_rate"])}
        self.job = {"stage": stage, "stage_version": self.spec.version, "contract_version": CONTRACT_VERSION,
                    "key": "0" * 64, "params": dict(self.params), "timebase": tb, "slug": slug, "profile": "max",
                    "threads": threads, "device": "cpu", "overrides": dict(self.overrides)}
        self.writer = StageWriter(self.spec, self.out, self.job)
        self._ups: dict[str, Any] = {}

    # ---------------------------------------------------------------- reads
    def upstream(self, stage: str):
        if stage not in self.spec.deps:
            raise UndeclaredDependency(f"{self.spec.name} reads {stage!r} but does not declare it in deps")
        return self._upstream(stage)

    def _upstream(self, stage: str):
        if stage not in self._ups:
            ov = self.overlays.get(stage)
            if ov is not None and (ov / RECORD).is_file():
                with open(ov / RECORD, encoding="utf-8") as fh:
                    rec = json.load(fh)
                self._ups[stage] = CacheUpstream(stage, ov, rec)
            else:
                self._ups[stage] = FixtureUpstream(stage, self.fixture)
        return self._ups[stage]

    def events(self, name: str):
        return self.upstream(catalog.producer_of_events(name)).events(name)

    def curve(self, channel_id: str) -> Curve:
        c = registry.match_channel(channel_id)
        if c is None:
            raise StageError(f"unknown curve channel {channel_id!r}")
        return self.upstream(c.stage).curve(channel_id)

    def audio(self, name: str = "mix", *, sr: int | None = None, mono: bool = False) -> Audio:
        if name == "mix":
            return self._upstream("ingest").audio("canonical.wav", sr=sr, mono=mono)
        if name.startswith("fast:"):
            return self.upstream("separate_fast").audio(f"fast/{name[5:]}.wav", sr=sr, mono=mono)
        up = self.upstream("separate_hq")
        base = f"stems/{name}" if not name.startswith("drums_") else f"stems/drums/{name[6:]}"
        rel = base + ".wav" if up.exists(base + ".wav") else base + ".flac"
        return up.audio(rel, sr=sr, mono=mono)

    def model(self, model_id: str):
        if model_id not in self.spec.models:
            raise UndeclaredDependency(f"{self.spec.name} does not list model {model_id!r}")
        from mvh.runner import models
        try:
            return models.handle(model_id)
        except models.ModelError as e:
            raise StageError(str(e)) from e

    def external(self, name: str):
        for e in self.spec.external_inputs:
            if e.name == name:
                if e.path.startswith("overrides.json"):
                    return None
                p = self.fixture / e.path.split("#", 1)[0]
                return p if p.is_file() else None
        raise UndeclaredDependency(name)

    # ---------------------------------------------------------------- record
    def save_record(self, result) -> None:
        rec = {"outputs": self.writer.written, "curves": self.writer.curves_meta, "matrices": self.writer.matrices,
               "result": {"status": result.status, "summary": result.summary, "warnings": result.warnings,
                          "fallbacks": result.fallbacks, "confidence": result.confidence}}
        with open(self.out / RECORD, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=1, default=str)


def run_stage(stage: str, fixture: Path, out: Path, **kw):
    """Run ``mvh.stages.<stage>.run`` against a fixture (+ overlays); returns (StageResult, ctx, seconds)."""
    import importlib

    ctx = FixtureCtx(stage, fixture, out, **kw)
    mod = importlib.import_module(f"mvh.stages.{stage}")
    t0 = time.perf_counter()
    res = mod.run(ctx)
    secs = time.perf_counter() - t0
    ctx.save_record(res)
    shutil.rmtree(ctx.scratch, ignore_errors=True)
    return res, ctx, secs


def load_events(out: Path, name: str) -> dict:
    ed = catalog.event_def(name)
    with open(Path(out) / ed.file, encoding="utf-8") as fh:
        return json.load(fh)


def load_curve(out: Path, cid: str) -> np.ndarray:
    c = registry.match_channel(cid)
    return np.fromfile(Path(out) / "_mvh" / "curves" / c.file / f"{cid}.f32", dtype="<f4")
