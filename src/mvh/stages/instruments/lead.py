"""Which stem carries the lead voice (shared by instruments and vocals, owner M3b)."""

from __future__ import annotations

import numpy as np


def p95_db(z: np.ndarray) -> float:
    """p95 of the 100 Hz RMS envelope (16 kHz audio), dBFS."""
    z = np.asarray(z, np.float64)
    k = 160
    m = (z.size // k) * k
    if m == 0:
        return -180.0
    e = np.sqrt(np.mean(z[:m].reshape(-1, k) ** 2, axis=1))
    e = e[e > 0]
    return float(20 * np.log10(max(np.percentile(e, 95), 1e-9))) if e.size else -180.0


def pick_lead_stem(ctx, min_gap_db: float = 20.0) -> tuple[str, np.ndarray]:
    """(stem name, 16 kHz mono float32): lead_vocals unless its p95 level is more than ``min_gap_db`` below the full
    vocals stem's (MEGAFAUNA: the karaoke split sent the whole voice to backing); then the vocals stem. Same rule as the
    lyrics stage, so both look at the same audio."""
    lead = np.asarray(ctx.audio("lead_vocals", sr=16000, mono=True).samples[0], np.float32)
    try:
        voc = np.asarray(ctx.audio("vocals", sr=16000, mono=True).samples[0], np.float32)
    except Exception:  # noqa: BLE001
        return "lead_vocals", lead
    if p95_db(lead) < p95_db(voc) - min_gap_db:
        return "vocals", voc
    return "lead_vocals", lead
