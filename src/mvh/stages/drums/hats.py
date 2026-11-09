"""Hi-hat bleed gate (W4A-S19 / W3C-4, owner M3a).

On a distorted rock mix the DrumSep hihat sub-stem carries guitar / cymbal wash: its onset detector then reports
strokes that are not hi-hat strokes (Jeremy: 64 % of the hats with vel >= 0.3 rise < 6 dB and only 20 % of those sit
on the 16th grid, below chance). The mix's own high band confirms the real strokes: of Jeremy's hats confirmed by a
spectral ``hits.high`` / ``onsets.high`` onset within 20 ms, 84 % are on the grid.

The gate is per song: when the share of hat rows that the mix high band confirms is below ``confirm_min`` (Jeremy 0.17;
Newton, MEGAFAUNA, Versatile and the synthetic song 0.59-0.69), the stem is "bleed-heavy" and a hat row is kept only
when the mix confirms it or its onset rises >= ``rise_keep_db`` (a stroke well above the wash). On the other songs the
hat rows are left as they are (the synthetic song's quiet closed hats under an open-hat wash rise < 6 dB and are real).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True)
class HatGateParams:
    confirm_ms: float = 20.0       # a mix high-band onset within this confirms a hat row
    confirm_min: float = 0.4       # the stem is bleed-heavy when fewer hat rows than this share are confirmed
    rise_keep_db: float = 10.0     # on a bleed-heavy stem, unconfirmed hats need an onset rise >= this


def _near(sorted_t: np.ndarray, t: float, tol: float) -> bool:
    if sorted_t.size == 0:
        return False
    j = int(np.searchsorted(sorted_t, t))
    return any(0 <= k < sorted_t.size and abs(float(sorted_t[k]) - t) <= tol for k in (j - 1, j))


def gate_hats(hits: list, mix_high: Sequence[float] | None, prm: HatGateParams = HatGateParams()) -> tuple[list, dict[str, Any]]:
    """(hits with the bleed hats removed, stats). ``mix_high``: times of spectral hits.high + onsets.high (None: no gate)."""
    hats = [h for h in hits if h.drum == "hat"]
    stats: dict[str, Any] = {"n": len(hats), "applied": False}
    if mix_high is None or not hats:
        stats["reason"] = "no mix high-band onsets" if mix_high is None else "no hats"
        return hits, stats
    mt = np.sort(np.asarray(list(mix_high), dtype=np.float64))
    tol = prm.confirm_ms / 1000.0
    conf = {id(h): _near(mt, h.t, tol) for h in hats}
    share = float(np.mean(list(conf.values())))
    stats.update({"confirmed_share": round(share, 3), "confirm_min": prm.confirm_min})
    if share >= prm.confirm_min:
        return hits, stats
    keep_ids = set()
    for h in hats:
        if conf[id(h)]:
            h.evidence.append("mix_high_confirms")
            keep_ids.add(id(h))
        elif float(h.rise_db) >= prm.rise_keep_db:
            keep_ids.add(id(h))
    out = [h for h in hits if h.drum != "hat" or id(h) in keep_ids]
    stats.update({"applied": True, "kept": len(keep_ids), "dropped": len(hats) - len(keep_ids), "rise_keep_db": prm.rise_keep_db})
    return out, stats
