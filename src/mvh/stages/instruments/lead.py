"""Which stem carries the lead voice (shared by instruments and vocals, owner M3b)."""

from __future__ import annotations

import numpy as np


def p95_db(z: np.ndarray) -> float:
    """p95 of the 100 Hz RMS envelope (16 kHz audio) over ALL frames, dBFS (floor -180).

    F-gain-6: digital-silence frames count. Dropping them made the measure follow the master level: a nearly silent
    lead stem stored as FLAC has its faint bleed quantised to zero at -12 dB, so the p95 of the remaining frames jumped
    to the voice fragments and the karaoke-split rescue (lead -> vocals stem) flipped (Versatile)."""
    z = np.asarray(z, np.float64)
    k = 160
    m = (z.size // k) * k
    if m == 0:
        return -180.0
    e = np.sqrt(np.mean(z[:m].reshape(-1, k) ** 2, axis=1))
    return float(20 * np.log10(max(float(np.percentile(e, 95)), 1e-9)))


def loud_frame_gap_db(lead: np.ndarray, voc: np.ndarray, pct: float = 90.0) -> float:
    """How far (dB) the lead stem sits under the full vocals stem in the vocals stem's loudest 10 % of 10 ms frames
    (energy ratio over those frames). Level invariant: both stems scale together and no frame is dropped by level."""
    k = 160
    m = (min(lead.size, voc.size) // k) * k
    if m == 0:
        return 0.0
    el = np.mean(np.asarray(lead[:m], np.float64).reshape(-1, k) ** 2, axis=1)
    ev = np.mean(np.asarray(voc[:m], np.float64).reshape(-1, k) ** 2, axis=1)
    sel = ev >= np.percentile(ev, pct)
    if not np.any(ev[sel] > 0):
        return 0.0
    return float(10 * np.log10(float(np.sum(ev[sel])) / max(float(np.sum(el[sel])), 1e-30)))


def pick_lead_stem(ctx, min_gap_db: float = 20.0) -> tuple[str, np.ndarray]:
    """(stem name, 16 kHz mono float32): lead_vocals unless it is more than ``min_gap_db`` under the full vocals stem
    where that stem is loudest (MEGAFAUNA: 40 dB, the karaoke split sent the whole voice to backing); then the vocals
    stem. F-gain-6: the old rule compared p95 levels over the non-silent frames, which followed the master level on a
    nearly silent FLAC lead stem and called Versatile's sparse but real lead (1.5 dB under the vocals stem in its loud
    frames) silent. The lyrics stage keeps its own copy of the old rule (change request)."""
    lead = np.asarray(ctx.audio("lead_vocals", sr=16000, mono=True).samples[0], np.float32)
    try:
        voc = np.asarray(ctx.audio("vocals", sr=16000, mono=True).samples[0], np.float32)
    except Exception:  # noqa: BLE001
        return "lead_vocals", lead
    if loud_frame_gap_db(lead, voc) > min_gap_db:
        return "vocals", voc
    return "lead_vocals", lead
