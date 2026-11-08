# ruff: noqa: E501  (long assertion messages)
"""R-DSP review (M1 dynamics): drop evidence must survive the downbeat snap.

Parts snap to downbeats (contract: "boundaries snapped to downbeats"); impact boundaries snap within half a bar, but
role_hints() only credits an impact within 0.6 s of the part start. When the rhythm grid's downbeat phase is off (SPIKE:
beat_this / madmom downbeat phase is wrong on 2 of 4 songs), the major impact that created the boundary is up to half a
bar away from it and the drop hint is lost. Real case: Versatile (real-versatile fixture bars), main drop impact at
50.96 s (bass -83 -> -6 dB, +18 LU) snapped to the downbeat at 51.72 s; that part is hinted 'build', not 'drop'."""

from __future__ import annotations

import pytest
from rdsp_m1_support import SR, breakdown_drop_song, run_all


def _bars(offset: float, dur: float = 44.0) -> list[dict]:
    return [{"bar": k + 1, "t": offset + 2.0 * k, "d": 2.0} for k in range(int(dur / 2.0) + 1) if offset + 2.0 * k < dur]


@pytest.mark.parametrize("offset", [0.0, 0.9])
def test_drop_hint_survives_the_downbeat_snap(offset, tmp_path):
    """offset 0.0: the grid is in phase and the drop part (28 s) is hinted 'drop'. offset 0.9 s (a downbeat-phase error
    of less than half a 2 s bar): the boundary moves to 28.9 s and no part is hinted 'drop' any more."""
    x, t_drop = breakdown_drop_song()
    r = run_all(x, SR, tmp_path / "s", bars=_bars(offset))
    dy = r["ctx"]["dynamics"]
    parts = dy.written_events("dynamics")["items"]
    impacts = dy.written_events("impacts")["items"]
    assert any(abs(i["t"] - t_drop) < 0.05 and i["major"] for i in impacts), impacts  # the drop impact itself is found
    drops = [p for p in parts if p.get("role_hint") == "drop" and abs(p["t"] - t_drop) <= 2.0]
    assert drops, f"grid offset {offset}: no 'drop' hint within one bar of the drop at {t_drop} s; parts {[(p['t'], p['d'], p['level'], p.get('role_hint')) for p in parts]}"
