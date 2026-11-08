# ruff: noqa: E501  (long numeric tables / docstrings)
"""Scoring helpers for the M3b unit tests (owner builder-m3b)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np


def note_f1(est: Sequence[dict], ref: Sequence[dict], tol: float = 0.05) -> tuple[float, float, float]:
    """mir_eval onset+pitch note P/R/F1 (offsets ignored), notes as dicts with t, d, midi."""
    import mir_eval

    if not ref or not est:
        return (0.0, 0.0, 0.0) if (ref or est) else (1.0, 1.0, 1.0)

    def arr(ns):
        iv = np.array([[float(n["t"]), float(n["t"]) + max(float(n["d"]), 0.01)] for n in ns])
        hz = 440.0 * 2 ** ((np.array([float(n["midi"]) for n in ns]) - 69) / 12)
        return iv, hz

    ri, rp = arr(ref)
    ei, ep = arr(est)
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=tol, offset_ratio=None)
    return float(p), float(r), float(f)


def as_dicts(notes) -> list[dict]:
    return [{"t": a, "d": b - a, "midi": m} for a, b, m, *_ in notes]


def events(folder: Path, name: str) -> list[dict]:
    with open(Path(folder) / "events" / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)["items"]


def jload(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)
