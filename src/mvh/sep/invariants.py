# ruff: noqa: E501  (long docstrings and tables)
"""Separator invariants (SPIKE re-baseline, docs/spike/sep.md §8). numpy only.

* ``residual_db(mix, parts)``  10 log10(|mix - sum(parts)|^2 / |mix|^2); gate <= -20 dB for the six SW stems.
* ``ls_gains_db(mix, parts)``  least-squares weights w in mix ~ sum(w_i * part_i), in dB; a stem that a model
  re-levelled would move away from 0 dB. Gate: |g| <= 0.1 dB for stems within 6 dB of the mix RMS and <= 0.5 dB
  within 20 dB; quieter stems are ill-conditioned and not gated.
* ``diff_db(a, b)``  10 log10(|a - b|^2 / |b|^2) (exactness of instrumental = mix - vocals, lead + backing = vocals).
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

__all__ = ["rms_dbfs", "residual_db", "diff_db", "ls_gains", "gain_gate", "SUM_GATE_DB"]

SUM_GATE_DB = -20.0
FLOOR = -150.0


def _energy(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    return float(np.sum(a * a))


def rms_dbfs(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    e = _energy(a) / max(1, a.size)
    return max(FLOOR, 10.0 * math.log10(e)) if e > 0 else FLOOR


def diff_db(a: np.ndarray, b: np.ndarray) -> float:
    eb = _energy(b)
    if eb <= 0:
        return FLOOR
    d = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    ed = _energy(d)
    return max(FLOOR, 10.0 * math.log10(ed / eb)) if ed > 0 else FLOOR


def residual_db(mix: np.ndarray, parts: Sequence[np.ndarray]) -> float:
    acc = np.zeros(np.asarray(mix).shape, dtype=np.float64)
    for p in parts:
        acc += np.asarray(p, dtype=np.float64)
    return diff_db(acc, mix)


def ls_gains(mix: np.ndarray, parts: Mapping[str, np.ndarray], max_samples: int = 4_000_000) -> dict[str, float]:
    """Least-squares weights (linear) of each part, pooled over channels. Long signals are decimated by a fixed
    stride (deterministic) to keep the normal equations small."""
    names = list(parts)
    y = np.asarray(mix, dtype=np.float64).reshape(-1)
    stride = max(1, y.size // max_samples)
    y = y[::stride]
    cols = [np.asarray(parts[k], dtype=np.float64).reshape(-1)[::stride] for k in names]
    A = np.stack(cols, axis=1)
    # normal equations (k x k): deterministic and cheap; lstsq on the small system
    ata = A.T @ A
    aty = A.T @ y
    w, *_ = np.linalg.lstsq(ata, aty, rcond=None)
    return {k: float(v) for k, v in zip(names, w)}


def gain_gate(mix: np.ndarray, parts: Mapping[str, np.ndarray]) -> dict[str, dict[str, float | bool | None]]:
    """Per stem: LS gain dB, level vs the mix, the applicable tolerance and pass/fail (None = not gated)."""
    w = ls_gains(mix, parts)
    mix_db = rms_dbfs(mix)
    out: dict[str, dict[str, float | bool | None]] = {}
    for k, v in w.items():
        rel = rms_dbfs(parts[k]) - mix_db
        g = 20.0 * math.log10(abs(v)) if v != 0 else FLOOR
        tol = 0.1 if rel >= -6.0 else (0.5 if rel >= -20.0 else None)
        out[k] = {"gain_db": round(g, 4), "rel_db": round(rel, 2), "tol_db": tol,
                  "pass": (v > 0 and abs(g) <= tol) if tol is not None else None}   # an inverted stem fails the gate
    return out
