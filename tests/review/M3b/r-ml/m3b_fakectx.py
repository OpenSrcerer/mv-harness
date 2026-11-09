"""A minimal in-memory Ctx for running an M3b stage's ``run(ctx)`` on synthetic arrays (reviewer r-ml-m3b).

Only what notes/vocals read is implemented: params, threads, audio(name, sr, mono) (resampled with soxr from the
arrays given), curve(id).values, upstream(stage).json(rel), events(name).items, model(id), and a writer that keeps
everything in dicts. Missing upstream data raise, as the real Ctx does (the stages catch those).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np


class _Writer:
    def __init__(self):
        self.ev: dict[str, list[dict]] = {}
        self.json_docs: dict[str, Any] = {}
        self.midis: dict[str, bytes] = {}
        self.curve_sets: dict[str, dict[str, np.ndarray]] = {}

    def events(self, name, items, kind=None, fields=None, extra=None):
        self.ev[name] = list(items)

    def json(self, rel, obj):
        self.json_docs[rel] = obj

    def midi(self, rel, data):
        self.midis[rel] = data

    def curves(self, file_id, chans, meta=None):
        self.curve_sets[file_id] = {k: np.asarray(v) for k, v in chans.items()}


class _Up:
    def __init__(self, docs: Mapping[str, Any]):
        self.docs = docs

    def json(self, rel):
        if rel not in self.docs:
            raise FileNotFoundError(rel)
        return self.docs[rel]


class FakeCtx:
    def __init__(self, stage_module, audio: Mapping[str, tuple[np.ndarray, int]], *,
                 curves: Mapping[str, np.ndarray] | None = None, upstream: Mapping[str, Mapping[str, Any]] | None = None,
                 events: Mapping[str, list[dict]] | None = None, params: Mapping[str, Any] | None = None,
                 threads: int = 3):
        self.spec = stage_module.STAGE
        self.params = {**dict(self.spec.params), **dict(params or {})}
        self.threads = threads
        self.device = "cpu"
        self.profile = "max"
        self._audio = dict(audio)
        self._curves = dict(curves or {})
        self._up = {k: _Up(v) for k, v in (upstream or {}).items()}
        self._events = dict(events or {})
        self.writer = _Writer()

    def audio(self, name: str = "mix", *, sr: int | None = None, mono: bool = False):
        import soxr

        if name not in self._audio:
            raise KeyError(name)
        x, native = self._audio[name]
        x = np.atleast_2d(np.asarray(x, np.float64))
        if mono:
            x = x.mean(axis=0, keepdims=True)
        if sr is not None and sr != native:
            x = np.stack([soxr.resample(c, native, sr, quality="VHQ") for c in x])
        return SimpleNamespace(samples=x.astype(np.float32), sr=sr or native)

    def curve(self, cid: str):
        if cid not in self._curves:
            raise KeyError(cid)
        return SimpleNamespace(values=np.asarray(self._curves[cid], np.float32))

    def upstream(self, stage: str):
        if stage not in self._up:
            raise KeyError(stage)
        return self._up[stage]

    def events(self, name: str):
        if name not in self._events:
            raise KeyError(name)
        return SimpleNamespace(items=self._events[name])

    def model(self, model_id: str):
        from mvh.runner import models

        if model_id not in self.spec.models:
            raise KeyError(model_id)
        return models.handle(model_id)


def activity(n_100hz: int, spans: list[tuple[float, float]]) -> np.ndarray:
    a = np.zeros(n_100hz, np.float32)
    for t0, t1 in spans:
        a[int(round(t0 * 100)): int(round(t1 * 100))] = 1.0
    return a
