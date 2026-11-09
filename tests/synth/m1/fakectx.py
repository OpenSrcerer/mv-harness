"""A minimal in-process ``Ctx`` for the M1 stages: real ``StageWriter`` (declared outputs, schema validation, atomic
writes into a temp folder) and upstream data handed in as arrays / item lists. Lets unit tests and the real-song
harness run ``run(ctx)`` without the runner, the cache or other modules' stages."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from mvh.contract import registry
from mvh.contract.catalog import CONTRACT_VERSION
from mvh.contract.events import EventFile
from mvh.runner.ctx import StageWriter
from mvh.runner.spec import Audio, Curve, StageError, StageSpec, UndeclaredDependency


class _Up:
    def __init__(self, stage: str, docs: Mapping[str, Any]):
        self.stage = stage
        self._docs = dict(docs)

    def json(self, rel: str) -> Any:
        if rel not in self._docs:
            raise StageError(f"upstream {self.stage} has no {rel}")
        return self._docs[rel]

    def exists(self, rel: str) -> bool:
        return rel in self._docs


class FakeCtx:
    def __init__(self, spec: StageSpec, out: Path, *, samples: np.ndarray, sr: int, audio_path: Path | None = None,
                 curves: Mapping[str, np.ndarray] | None = None, events: Mapping[str, list[dict]] | None = None,
                 docs: Mapping[str, Mapping[str, Any]] | None = None, params: Mapping[str, Any] | None = None,
                 profile: str = "max"):
        self.spec = spec
        self.slug = "test"
        self.params = spec.resolved_params(profile, params)
        self.profile = profile
        self.threads = 3
        self.device = "cpu"
        self.offline = True
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        self.scratch = out / "_scratch"
        self.scratch.mkdir(exist_ok=True)
        self.log = logging.getLogger(f"mvh.test.{spec.name}")
        self.overrides: dict[str, Any] = {}
        x = np.asarray(samples, dtype=np.float32)
        if x.ndim == 1:
            x = x[None, :]
        self._audio = Audio(x, int(sr), audio_path)
        self.job = {
            "stage": spec.name,
            "stage_version": spec.version,
            "contract_version": CONTRACT_VERSION,
            "key": "0" * 64,
            "params": dict(self.params),
            "timebase": {"n_samples": int(x.shape[1]), "sample_rate": int(sr)},
            "upstream": {},
        }
        self.writer = StageWriter(spec, out, self.job)
        self.out = out
        self._curves = {k: np.asarray(v, dtype=np.float32) for k, v in (curves or {}).items()}
        self._events = {k: list(v) for k, v in (events or {}).items()}
        self._docs = {k: dict(v) for k, v in (docs or {}).items()}  # stage -> {rel: obj}

    # ---------------------------------------------------------------- reads
    def audio(self, name: str = "mix", *, sr: int | None = None, mono: bool = False) -> Audio:
        if name != "mix" or sr is not None:
            raise StageError(f"FakeCtx serves only the native-rate mix (asked {name!r}, sr={sr})")
        if mono:
            return Audio(self._audio.samples.mean(axis=0, keepdims=True), self._audio.sr, self._audio.path)
        return self._audio

    def curve(self, cid: str) -> Curve:
        c = registry.match_channel(cid)
        if c is None or c.stage not in self.spec.deps:
            raise UndeclaredDependency(f"{self.spec.name} cannot read curve {cid}")
        if cid not in self._curves:
            raise StageError(f"no curve {cid}")
        return Curve(cid, self._curves[cid], 100.0, registry.index_entry(c, cid))

    def events(self, name: str) -> EventFile:
        if name not in self._events:
            raise StageError(f"no events {name}")
        return EventFile(name, "event", {}, self._events[name])

    def upstream(self, stage: str) -> _Up:
        if stage not in self.spec.deps:
            raise UndeclaredDependency(f"{self.spec.name} reads {stage!r} but does not declare it in deps")
        return _Up(stage, self._docs.get(stage, {}))

    def model(self, model_id: str):
        raise UndeclaredDependency(model_id)

    def external(self, name: str):
        return None

    def ffmpeg(self):
        from mvh.io.ffmpeg import resolve_ffmpeg

        return resolve_ffmpeg()

    # ---------------------------------------------------------------- written outputs
    def written_events(self, name: str) -> dict[str, Any]:
        for rel, info in self.writer.written.items():
            if info.get("events") and rel.endswith(f"{name}.json") and ("/" + name + ".json") in ("/" + rel):
                with open(self.out / rel, encoding="utf-8") as fh:
                    return json.load(fh)
        raise KeyError(name)

    def written_json(self, rel: str) -> dict[str, Any]:
        with open(self.out / rel, encoding="utf-8") as fh:
            return json.load(fh)

    def written_curves(self) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        for fid, chans in self.writer.curves_meta.items():
            for cid in chans:
                out[cid] = np.fromfile(self.out / "_mvh" / "curves" / fid / f"{cid}.f32", dtype="<f4")
        return out

    def written_curve_meta(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for fid, chans in self.writer.curves_meta.items():
            for cid, info in chans.items():
                out[cid] = info
        return out

    def written_matrix(self, fid: str) -> np.ndarray:
        info = self.writer.matrices[fid]
        dt = np.uint8 if info["dtype"] == "u8" else "<f4"
        return np.fromfile(self.out / "_mvh" / "matrices" / f"{fid}.bin", dtype=dt).reshape(info["shape"])


def write_audio_wav(path: Path, samples: np.ndarray, sr: int) -> Path:
    """Our own float32 WAV (for stages that hand the mix path to ffmpeg)."""
    from mvh.io.wav import write_wav

    return write_wav(path, np.asarray(samples, dtype=np.float32), sr)
