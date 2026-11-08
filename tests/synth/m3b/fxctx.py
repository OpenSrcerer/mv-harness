# ruff: noqa: E501  (long numeric tables / docstrings)
"""A direct Ctx for running one M3b stage's ``run(ctx)`` on a fixture folder without the runner (owner builder-m3b).

Upstream data are read from ``roots`` in order: output folders of stages run earlier with this harness (their
``_mvh/curves`` and published files), then the fixture folder (tests/contract/synth, or a real-song overlay from
``stem_overlay.py``). Writes go through the runner's own ``StageWriter`` (declared outputs, schema validation, atomic
writes), so the files are exactly what the runner would publish. Used by the unit tests and the real-song scripts; it
isolates M3b from upstream stages that other modules are rewriting at the same time.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from mvh.contract import catalog, curvefile, registry
from mvh.contract.events import read_events
from mvh.runner.ctx import StageWriter
from mvh.runner.spec import Audio, Curve, StageError, UndeclaredDependency


class _Up:
    def __init__(self, stage: str, roots: Sequence[Path]):
        self.stage = stage
        self.roots = list(roots)

    def _find(self, rel: str) -> Path | None:
        for r in self.roots:
            for p in (r / rel, r / "_intermediate" / self.stage / rel):
                if p.is_file():
                    return p
        return None

    def path(self, rel: str) -> Path:
        p = self._find(rel)
        if p is None:
            raise StageError(f"upstream {self.stage} has no {rel}")
        return p

    def exists(self, rel: str) -> bool:
        return self._find(rel) is not None

    def json(self, rel: str) -> Any:
        import json

        with open(self.path(rel), encoding="utf-8") as fh:
            return json.load(fh)


class FixtureCtx:
    def __init__(self, stage_module, fixture: Path, out: Path, *, roots: Sequence[Path] = (),
                 params: Mapping[str, Any] | None = None, threads: int = 3, profile: str = "max"):
        self.mod = stage_module
        self.spec = stage_module.STAGE
        self.fixture = Path(fixture)
        self.out = Path(out)
        self.roots = [Path(r) for r in roots] + [self.fixture]
        self.params = self.spec.resolved_params(profile, dict(params or {}))
        self.profile = profile
        self.threads = int(threads)
        self.device = "cpu"
        self.offline = True
        self.overrides: dict[str, Any] = {}
        self.slug = self.fixture.name
        self.scratch = Path(tempfile.mkdtemp(prefix="m3b-"))
        self.log = logging.getLogger(f"m3b.{self.spec.name}")
        self._audio: dict[tuple, Audio] = {}
        canon = self.fixture / "_intermediate" / "ingest" / "canonical.wav"
        from mvh.io.wav import wav_info

        info = wav_info(canon)
        self.timebase = {"n_samples": int(info["frames"]), "sample_rate": int(info["sample_rate"])}
        job = {"stage": self.spec.name, "stage_version": self.spec.version, "contract_version": catalog.CONTRACT_VERSION,
               "key": "0" * 64, "params": dict(self.params), "timebase": self.timebase,
               "models_prov": [{"id": m, "licence": "", "revision": None} for m in self.spec.models]}
        self.out.mkdir(parents=True, exist_ok=True)
        self.writer = StageWriter(self.spec, self.out, job)

    # ------------------------------------------------------------------ reads
    def upstream(self, stage: str) -> _Up:
        if stage not in self.spec.deps:
            raise UndeclaredDependency(f"{self.spec.name} reads {stage!r} but does not declare it in deps")
        return _Up(stage, self.roots)

    def events(self, name: str):
        prod = catalog.producer_of_events(name)
        if prod not in self.spec.deps:
            raise UndeclaredDependency(f"{self.spec.name} reads events {name} of {prod}")
        ed = catalog.event_def(name)
        rel = ed.file.replace("{src}", name.split(".", 1)[1]) if "{src}" in ed.file else ed.file
        for r in self.roots:
            if (r / rel).is_file():
                return read_events(r / rel)
        raise StageError(f"no events {name}")

    def curve(self, cid: str) -> Curve:
        c = registry.match_channel(cid)
        if c is None:
            raise StageError(f"unknown channel {cid}")
        if c.stage not in self.spec.deps:
            raise UndeclaredDependency(f"{self.spec.name} reads curve {cid} of {c.stage}")
        rate = registry.CURVE_FILES[c.file].rate_hz
        for r in self.roots:
            p = r / "_mvh" / "curves" / c.file / f"{cid}.f32"
            if p.is_file():
                return Curve(cid, np.fromfile(p, dtype="<f4"), float(rate), registry.index_entry(c, cid))
            if (r / "curves" / "index.json").is_file():
                ix = curvefile.read_index(r)
                if any(e["id"] == cid for e in ix["channels"]):
                    v, meta = curvefile.read_channel(r, ix, cid)
                    return Curve(cid, v, float(rate), meta)
        raise StageError(f"no curve {cid}")

    def audio(self, name: str = "mix", *, sr: int | None = None, mono: bool = False) -> Audio:
        from mvh.contract.ids import DRUM_SUBSTEMS, STEM_NAMES
        from mvh.io import audio as aio

        k = (name, sr, mono)
        if k in self._audio:
            return self._audio[k]
        if name == "mix":
            p = self.fixture / "_intermediate" / "ingest" / "canonical.wav"
        elif name in STEM_NAMES or (name.startswith("drums_") and name[6:] in DRUM_SUBSTEMS):
            if "separate_hq" not in self.spec.deps:
                raise UndeclaredDependency(f"{self.spec.name} reads stem {name}")
            base = f"stems/{name}" if name in STEM_NAMES else f"stems/drums/{name[6:]}"
            p = self.fixture / (base + ".wav") if (self.fixture / (base + ".wav")).is_file() else self.fixture / (base + ".flac")
        elif name.startswith("fast:"):
            p = self.fixture / "_intermediate" / "separate_fast" / "fast" / f"{name[5:]}.wav"
        else:
            raise StageError(f"unknown audio {name}")
        d = aio.decode(p, sr=sr, mono=mono)
        a = Audio(d.samples, d.sr, p)
        self._audio[k] = a
        return a

    def model(self, model_id: str):
        if model_id not in self.spec.models:
            raise UndeclaredDependency(f"{self.spec.name} uses model {model_id} not in STAGE.models")
        from mvh.runner import models

        return models.handle(model_id)

    def ffmpeg(self) -> Path:
        from mvh.io.ffmpeg import resolve_ffmpeg

        return resolve_ffmpeg()

    # ------------------------------------------------------------------ run
    def run(self):
        res = self.mod.run(self)
        from mvh.runner.ctx import provenance_block

        prov = provenance_block(self.writer.job, res.provenance, res.fallbacks, res.confidence)
        self.writer.restamp(prov)
        return res


def run_stage(stage_module, fixture: Path, out: Path, roots: Sequence[Path] = (), params=None, threads: int = 3):
    """Run one stage directly; returns (StageResult, FixtureCtx)."""
    ctx = FixtureCtx(stage_module, fixture, out, roots=roots, params=params, threads=threads)
    return ctx.run(), ctx


def read_curve(out: Path, file_id: str, cid: str) -> np.ndarray:
    return np.fromfile(Path(out) / "_mvh" / "curves" / file_id / f"{cid}.f32", dtype="<f4")


def silence_logging() -> None:
    logging.getLogger("m3b").setLevel(logging.WARNING)
