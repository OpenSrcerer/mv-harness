# ruff: noqa: E501
"""Read the allin1 intermediates (cache only) from an Upstream handle.

Works for both the real stage (matrices recorded in done.json) and the walking-skeleton / fixture copies
(raw files without a matrix record): the layout always comes from ``allin1.json``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ["Allin1Data", "load_allin1"]


@dataclass
class Allin1Data:
    doc: dict[str, Any]
    act: np.ndarray | None          # [frames x columns] float32
    columns: list[str]
    rate_hz: float
    emb: np.ndarray | None          # [frames x dim] float32
    emb_rate_hz: float | None

    def col(self, name: str) -> np.ndarray | None:
        if self.act is None or name not in self.columns:
            return None
        return self.act[:, self.columns.index(name)]

    @property
    def label_names(self) -> list[str]:
        return [c for c in self.columns if c not in ("beat", "downbeat", "boundary")]

    def label_probs(self) -> np.ndarray | None:
        if self.act is None:
            return None
        idx = [self.columns.index(c) for c in self.label_names]
        return self.act[:, idx] if idx else None


def _raw(up, rel: str, frames: int | None, width: int | None) -> np.ndarray | None:
    if not up.exists(rel):
        return None
    v = np.fromfile(up.path(rel), dtype="<f4")
    if width and width > 0 and v.size % width == 0:
        return v.reshape(-1, width)
    if frames and frames > 0 and v.size % frames == 0:
        return v.reshape(frames, -1)
    return None


def load_allin1(up) -> Allin1Data:
    doc = up.json("allin1.json")
    a = doc.get("activations") or {}
    cols = list(a.get("columns") or [])
    rate = float(a.get("rate_hz") or 100.0)
    act = None
    try:
        arr, _ = up.matrix("activations")
        act = np.asarray(arr, np.float32)
    except Exception:  # noqa: BLE001 - stub/fixture copies carry no matrix record
        act = _raw(up, a.get("file") or "activations.f32", a.get("frames"), len(cols) or None)
    if act is not None and cols and act.shape[1] != len(cols):
        cols = cols[: act.shape[1]] if act.shape[1] < len(cols) else cols + [f"c{i}" for i in range(len(cols), act.shape[1])]
    e = doc.get("embeddings") or None
    emb, erate = None, None
    if e:
        try:
            arr, _ = up.matrix("embeddings")
            emb = np.asarray(arr, np.float32)
        except Exception:  # noqa: BLE001
            emb = _raw(up, e.get("file") or "embeddings.f32", e.get("frames"), e.get("dim"))
        erate = float(e.get("rate_hz") or 100.0)
    return Allin1Data(doc, act, cols, rate, emb, erate)
