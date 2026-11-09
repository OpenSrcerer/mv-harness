"""loudness stage: run(ctx). Measurements live in ``r128.py``."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from mvh.runner.spec import StageResult

from . import r128


def _pnorm(v: np.ndarray, floor: float) -> tuple[np.ndarray, float, float]:
    live = v > floor + 1e-6
    pool = v[live] if live.sum() >= max(10, 0.01 * v.size) else v
    lo, hi = float(np.percentile(pool, 2.0)), float(np.percentile(pool, 99.5))
    if hi - lo < 1e-9:
        return np.zeros_like(v), lo, hi
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0), lo, hi


def _rd(x: float, nd: int = 3) -> float:
    return float(round(float(x), nd))


def run(ctx) -> StageResult:
    p = dict(ctx.params)
    audio = ctx.audio("mix")
    x = np.asarray(audio.samples, dtype=np.float64)
    if x.ndim == 1:
        x = x[None, :]
    sr = int(audio.sr)
    n = x.shape[1]
    warnings: list[str] = []
    fallbacks: list[str] = []
    qa: list[str] = []

    ctx.log.info("loudness: K-weighting %d channel(s) at %d Hz", x.shape[0], sr)
    xk = r128.k_weight(x, sr)
    z = r128.weighted_power(xk)
    del xk
    curves = r128.loudness_curves(z, sr, n)
    integ = r128.integrated(x, sr)
    lra = r128.loudness_range(z, sr)
    win = int(p.get("rms_window", 0)) or _fft_size(sr)
    lv = r128.level_curves(x, sr, win)
    tp_lin = r128.true_peak(x, sr)
    sp_lin = float(np.max(np.abs(x))) if x.size else 0.0
    tp_db = r128.db(max(tp_lin, sp_lin))
    sp_db = r128.db(sp_lin)
    clipped = r128.clipped_samples(x)

    # ---------------------------------------------------------------- ffmpeg ebur128 cross-check
    eb: dict[str, Any] = {}
    tol = float(p["crosscheck_tol_lu"])
    try:
        src = audio.path
        if src is None:
            raise RuntimeError("the canonical mix has no file path")
        e = r128.ffmpeg_ebur128(src)
        if "integrated_lufs" in e and math.isfinite(e["integrated_lufs"]):
            eb["integrated_lufs"] = _rd(e["integrated_lufs"], 1)
            eb["diff_lu"] = _rd(integ - e["integrated_lufs"], 2)
            if abs(eb["diff_lu"]) > tol:
                warnings.append(f"integrated loudness differs from ffmpeg ebur128 by {eb['diff_lu']:+.2f} LU (> {tol} LU)")
                qa.append("loudness:ebur128_mismatch")
        if "lra_lu" in e:
            eb["lra_lu"] = _rd(e["lra_lu"], 1)
        if "true_peak_dbtp" in e and math.isfinite(e["true_peak_dbtp"]):
            eb["true_peak_dbtp"] = _rd(e["true_peak_dbtp"], 1)
            if abs(e["true_peak_dbtp"] - tp_db) > float(p["true_peak_tol_db"]):
                warnings.append(f"true peak differs from ffmpeg ebur128 by {tp_db - e['true_peak_dbtp']:+.2f} dB")
    except Exception as exc:  # noqa: BLE001 - the cross-check is optional; the measurement stands without it
        warnings.append(f"ffmpeg ebur128 cross-check unavailable: {type(exc).__name__}")
        fallbacks.append("loudness:no_ebur128_crosscheck")

    # ---------------------------------------------------------------- curves
    ch: dict[str, np.ndarray] = {}
    meta: dict[str, dict[str, Any]] = {}
    for name in ("momentary", "short_term"):
        v = curves[name]
        ch[f"loud.{name}_lufs"] = v
        nv, lo, hi = _pnorm(v, r128.LUFS_FLOOR)
        ch[f"loud.{name}"] = nv
        meta[f"loud.{name}"] = {"norm": {"lo": lo, "hi": hi}}
    ch["loud.rms_db"] = lv["rms_db"]
    nv, lo, hi = _pnorm(lv["rms_db"], r128.DB_FLOOR)
    ch["loud.rms"] = nv
    meta["loud.rms"] = {"norm": {"lo": lo, "hi": hi}}
    ch["loud.peak_db"] = lv["peak_db"]
    ch["loud.crest_db"] = lv["crest_db"]
    nf = ch["loud.rms_db"].size
    for k in list(ch):
        a = np.asarray(ch[k], dtype=np.float64)
        if a.size != nf or not np.all(np.isfinite(a)):
            raise ValueError(f"loudness: channel {k} is malformed")
        ch[k] = a.astype(np.float32)
    ctx.writer.curves("core", ch, meta=meta)

    # ---------------------------------------------------------------- meta/loudness.json
    plr = tp_db - integ
    lim = lra["lra_lu"] < float(p["limited_lra_lu"]) and plr < float(p["limited_plr_db"])
    if lim:
        qa.append("loudness:limited_master")
    if clipped > int(p["clip_warn_samples"]):
        qa.append("loudness:clipping")
        warnings.append(f"{clipped} samples at full scale (clipping)")
    if integ <= r128.LUFS_FLOOR + 1e-6:
        qa.append("loudness:silent")
    t = np.arange(nf) / r128.RATE
    stats = r128.summary_stats(curves["short_term"], curves["momentary"], t, integ)
    doc: dict[str, Any] = {
        "integrated_lufs": _rd(integ),
        "lra_lu": _rd(lra["lra_lu"]),
        "lra_low_lufs": _rd(lra["lra_low_lufs"]),
        "lra_high_lufs": _rd(lra["lra_high_lufs"]),
        "true_peak_dbtp": _rd(tp_db),
        "sample_peak_db": _rd(sp_db),
        "plr_db": _rd(plr),
        "clipped_samples": clipped,
        "curve_offsets_s": {"momentary": 0.2, "short_term": 1.5},
        "lra_threshold_lufs": _rd(lra["lra_threshold_lufs"]),
        **stats,
        "limited_master": bool(lim),
        "qa": qa,
        "method": {
            "integrated": "pyloudnorm BS.1770-4 (400 ms blocks, 75 % overlap, -70 / -10 LU gates)",
            "lra": "EBU Tech 3342 (3 s blocks every 0.1 s, -70 / -20 LU gates, P95 - P10)",
            "true_peak": "4x polyphase oversampling (Kaiser beta 10) per channel, max over channels",
            "curves": "centred windows (momentary 0.4 s, short-term 3 s); a trailing spec meter shows curve(t) at "
            "t + curve_offsets_s",
            "rms": f"centred {win}-sample mean square over channels; peak = max |x| in the same window",
        },
    }
    if eb:
        doc["ebur128"] = eb
    ctx.writer.json("meta/loudness.json", doc)

    summary = {
        "integrated_lufs": _rd(integ, 2),
        "lra_lu": _rd(lra["lra_lu"], 2),
        "true_peak_dbtp": _rd(tp_db, 2),
        "plr_db": _rd(plr, 2),
        "ebur128_diff_lu": eb.get("diff_lu"),
        "limited_master": bool(lim),
    }
    conf = 1.0 if eb and abs(eb.get("diff_lu", 0.0)) <= tol else 0.8
    return StageResult(
        status="ok",
        summary=summary,
        warnings=warnings,
        fallbacks=fallbacks,
        provenance={"notes": [f"rms window {win} samples", "true peak: own 4x oversampling; ffmpeg ebur128 is the "
                              "cross-check (0.1 dB resolution)"], "qa": qa},
        confidence=conf,
    )


def _fft_size(sr: int) -> int:
    k = max(0, round(math.log2(max(sr, 1) / 48000.0)))
    return 2048 * (2**k)
