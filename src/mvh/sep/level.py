"""Analysis level for the separator worker (decision F-gain-1; the W4-AN-9 principle).

DrumSep (MDX23C) is not level invariant: on a -12 dB copy of a master it routes kick energy to the toms stem. The
separate_hq worker therefore runs it on the SW drum stem scaled by ONE pure gain that puts the canonical mix at
``ANALYSIS_LUFS`` (the gain of ``mvh.stages.loudness.level``), and scales the sub-stems back by the inverse gain, so the
sub-stems keep the master's dBFS scale and the DrumSep-sum invariants hold.

The sep env has numpy + scipy but no pyloudnorm, so this module carries its own BS.1770-4 integrated loudness (the same
K-weighting design, 400 ms blocks at 75 % overlap, -70 LUFS absolute and -10 LU relative gates). It agrees with
``mvh.stages.loudness.r128.integrated`` to well under 0.1 dB (tests/unit/drums/test_gain_invariance.py); a pure gain k
moves the result by exactly 20 log10 k, which is all the level invariance needs.
"""

from __future__ import annotations

import math

import numpy as np

ANALYSIS_LUFS = -10.0       # = mvh.stages.loudness.level.ANALYSIS_LUFS
MAX_GAIN_DB = 40.0
LUFS_FLOOR = -70.0


def _biquads(sr: int) -> list[tuple[np.ndarray, np.ndarray]]:
    out = []
    # high shelf (G 4 dB, Q 1/sqrt 2, 1500 Hz) and high pass (Q 0.5, 38 Hz): the pyloudnorm / BS.1770 K-weighting design
    for kind, g, q, fc in (("shelf", 4.0, 1.0 / math.sqrt(2.0), 1500.0), ("hp", 0.0, 0.5, 38.0)):
        a_ = 10.0 ** (g / 40.0)
        w0 = 2.0 * math.pi * fc / sr
        al = math.sin(w0) / (2.0 * q)
        c = math.cos(w0)
        if kind == "shelf":
            b = [a_ * ((a_ + 1) + (a_ - 1) * c + 2 * math.sqrt(a_) * al), -2 * a_ * ((a_ - 1) + (a_ + 1) * c),
                 a_ * ((a_ + 1) + (a_ - 1) * c - 2 * math.sqrt(a_) * al)]
            a = [(a_ + 1) - (a_ - 1) * c + 2 * math.sqrt(a_) * al, 2 * ((a_ - 1) - (a_ + 1) * c),
                 (a_ + 1) - (a_ - 1) * c - 2 * math.sqrt(a_) * al]
        else:
            b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
            a = [1 + al, -2 * c, 1 - al]
        out.append((np.array(b) / a[0], np.array(a) / a[0]))
    return out


def integrated_lufs(x: np.ndarray, sr: int) -> float:
    """BS.1770-4 integrated loudness of ``x`` ([ch, n] or [n]); ``LUFS_FLOOR`` below the absolute gate."""
    from scipy.signal import lfilter

    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 1:
        a = a[None, :]
    a = a[:2] if a.shape[0] <= 3 else a[:3]
    blk, step = int(round(0.4 * sr)), int(round(0.1 * sr))
    if a.shape[1] < blk:
        return LUFS_FLOOR
    z = np.zeros(a.shape[1])
    for ch in a:
        y = ch
        for b, den in _biquads(int(sr)):
            y = lfilter(b, den, y)
        z += y * y
    cs = np.concatenate(([0.0], np.cumsum(z)))
    starts = np.arange(0, a.shape[1] - blk + 1, step)
    ms = (cs[starts + blk] - cs[starts]) / blk
    with np.errstate(divide="ignore"):
        lk = -0.691 + 10.0 * np.log10(ms)
    g1 = ms[lk > LUFS_FLOOR]
    if g1.size == 0:
        return LUFS_FLOOR
    rel = -0.691 + 10.0 * math.log10(float(np.mean(g1))) - 10.0
    g2 = ms[(lk > LUFS_FLOOR) & (lk > rel)]
    if g2.size == 0:
        return LUFS_FLOOR
    return float(-0.691 + 10.0 * math.log10(float(np.mean(g2))))


def analysis_gain_db(mix: np.ndarray, sr: int, target_lufs: float | None = ANALYSIS_LUFS,
                     max_gain_db: float = MAX_GAIN_DB) -> tuple[float, float]:
    """(gain dB, measured LUFS) that brings the mix to ``target_lufs``; 0 for silence or ``target_lufs`` None."""
    lv = integrated_lufs(mix, sr)
    if target_lufs is None or not math.isfinite(lv) or lv <= LUFS_FLOOR + 1e-6:
        return 0.0, lv
    return float(np.clip(float(target_lufs) - lv, -abs(max_gain_db), abs(max_gain_db))), lv
