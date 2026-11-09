"""Vocal-stem envelope helpers shared by lyrics (sustain extension, activity fallback) and lipsync.

All curves are 100 Hz with sample i centred at i/100 s (CONTRACT §2), ``n = ceil(n_samples * 100 / sr)``.
"""

from __future__ import annotations

import numpy as np

__all__ = ["rms_100hz", "one_pole", "activity_from_env", "sustain_end", "frames_for"]


def frames_for(n_samples: int, sr: int, rate: int = 100) -> int:
    return -(-int(n_samples) * rate // int(sr))


def rms_100hz(x: np.ndarray, sr: int, n_frames: int | None = None, win_s: float = 0.02) -> np.ndarray:
    """RMS in a centred window (default 20 ms) at every 10 ms frame centre; float64 array of n_frames."""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    n = frames_for(len(x), sr) if n_frames is None else int(n_frames)
    half = max(1, int(round(win_s * sr / 2)))
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    centres = np.round(np.arange(n) * sr / 100.0).astype(np.int64)
    a = np.clip(centres - half, 0, len(x))
    b = np.clip(centres + half, 0, len(x))
    e = (c[b] - c[a]) / np.maximum(1, b - a)
    return np.sqrt(np.maximum(e, 0.0))


def one_pole(v: np.ndarray, attack_ms: float = 10.0, release_ms: float = 60.0, rate: float = 100.0) -> np.ndarray:
    """Attack/release one-pole follower (the spike's mouth envelope)."""
    aa = 1.0 - np.exp(-1.0 / max(1e-6, attack_ms / 1000.0 * rate))
    ar = 1.0 - np.exp(-1.0 / max(1e-6, release_ms / 1000.0 * rate))
    out = np.zeros(len(v))
    s = 0.0
    for i, x in enumerate(np.asarray(v, dtype=np.float64)):
        s += (aa if x > s else ar) * (x - s)
        out[i] = s
    return out


def activity_from_env(env: np.ndarray, below_p95_db: float = 30.0, floor_db: float = -50.0, on_frames: int = 10,
                      off_frames: int = 30) -> np.ndarray:
    """0/1 vocal activity from an amplitude envelope: above max(p95 - below_p95_db, floor) dBFS with
    hysteresis (on after on_frames, off after off_frames). Used when stem_activity's curve is missing."""
    env = np.asarray(env, dtype=np.float64)
    if not len(env) or not np.any(env > 0):
        return np.zeros(len(env), np.float32)
    db = 20 * np.log10(np.maximum(env, 1e-9))
    thr = max(np.percentile(db[env > 0], 95) - below_p95_db, floor_db)
    raw = db > thr
    act = np.zeros(len(env), np.float32)
    on, run_on, run_off = False, 0, 0
    for i, r in enumerate(raw):
        run_on, run_off = (run_on + 1, 0) if r else (0, run_off + 1)
        if not on and run_on >= on_frames:
            on = True
            act[i - on_frames + 1:i + 1] = 1
        elif on and run_off >= off_frames:
            on = False
            act[i - off_frames + 1:i + 1] = 0
        if on:
            act[i] = 1
    return act


def sustain_end(env: np.ndarray, floor: float, start_t: float, end_t: float, limit_t: float, max_hold_s: float = 1.5,
                rate: float = 100.0) -> float:
    """Extend ``end_t`` while the envelope stays above ``floor`` (e.g. p95 - 20 dB), at most ``max_hold_s`` past
    end_t and never past ``limit_t`` (the next word's start)."""
    b = int(np.ceil(end_t * rate))
    lim = min(len(env) - 1, int(np.floor(min(limit_t, end_t + max_hold_s) * rate)))
    while b < lim and env[b] > floor:
        b += 1
    return max(end_t, min(b / rate, limit_t))


def pick_vocal_stem(ctx, sr: int | None = 16000, min_gap_db: float = 20.0) -> tuple[str, np.ndarray, int]:
    """lead_vocals (the karaoke lead, SPIKE) unless it is essentially empty next to ``vocals``: when the lead's
    p95 envelope is more than ``min_gap_db`` below the vocals stem's (MEGAFAUNA: -74 vs -19 dBFS, the karaoke
    model sent the whole voice to backing), the full vocals stem is used. Returns (name, mono samples, sr)."""
    from mvh.runner.spec import StageError

    lead = ctx.audio("lead_vocals", sr=sr, mono=True)
    x = np.asarray(lead.samples[0], dtype=np.float32)
    try:
        voc = ctx.audio("vocals", sr=sr, mono=True)
    except StageError:
        return "lead_vocals", x, int(lead.sr)
    y = np.asarray(voc.samples[0], dtype=np.float32)

    def p95db(z: np.ndarray, rate: int) -> float:
        e = rms_100hz(z, rate)
        e = e[e > 0]
        return float(20 * np.log10(max(np.percentile(e, 95), 1e-9))) if len(e) else -180.0

    if p95db(x, int(lead.sr)) < p95db(y, int(voc.sr)) - min_gap_db:
        return "vocals", y, int(voc.sr)
    return "lead_vocals", x, int(lead.sr)
