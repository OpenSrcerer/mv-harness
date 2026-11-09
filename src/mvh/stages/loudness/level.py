"""Analysis-level normalisation (W4V-GAIN, decision W4-AN-9).

Model front ends (allin1, beat_this, madmom, the chord model) and DSP features with absolute floors are level dependent:
a -12 dB copy of a real master moved MEGAFAUNA's sections and beat grid. Every level-dependent analysis therefore sees
the audio scaled by ONE pure gain that puts the canonical mix's BS.1770 integrated loudness at ``ANALYSIS_LUFS``
(commercial-master level, the training range of those models). The gain is measured on the stereo mix, so the same
song at any master level reaches the models at the same level; timing is untouched. Silence (below the absolute gate)
keeps gain 0. Measurements that are meant to be absolute (the loudness stage, dBFS curves) never use this.
"""
from __future__ import annotations

import math

import numpy as np

ANALYSIS_LUFS = -10.0
MAX_GAIN_DB = 40.0


def gain_db_for(x: np.ndarray, sr: int, target_lufs: float | None = ANALYSIS_LUFS,
                max_gain_db: float = MAX_GAIN_DB) -> tuple[float, float]:
    """(gain dB, measured integrated LUFS) that brings ``x`` ([channels, n] or [n]) to ``target_lufs``.
    ``target_lufs`` None -> gain 0 (analysis at the master level)."""
    from .r128 import LUFS_FLOOR, integrated

    a = np.asarray(x)
    if a.ndim == 1:
        a = a[None, :]
    lv = integrated(a, int(sr))
    if target_lufs is None or not math.isfinite(lv) or lv <= LUFS_FLOOR + 1e-6:
        return 0.0, lv
    return float(np.clip(float(target_lufs) - lv, -abs(max_gain_db), abs(max_gain_db))), lv


def mix_gain(ctx, target_lufs: float | None = ANALYSIS_LUFS) -> tuple[float, float, float]:
    """(linear gain, gain dB, measured integrated LUFS) for the canonical mix of this stage's song."""
    a = ctx.audio("mix")
    g_db, lv = gain_db_for(np.asarray(a.samples), int(a.sr), target_lufs)
    return float(10.0 ** (g_db / 20.0)), g_db, lv


def apply(x: np.ndarray, gain: float) -> np.ndarray:
    """float32 copy of ``x`` scaled by ``gain`` (no clipping: the analysis copy is float)."""
    y = np.asarray(x, np.float32)
    return y if gain == 1.0 else (y * np.float32(gain)).astype(np.float32)
