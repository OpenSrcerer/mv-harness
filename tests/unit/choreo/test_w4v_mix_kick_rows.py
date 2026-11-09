"""W4V-KICKCURVE-CHOREO: under kick_source = mix, choreo's kick rows are the agent kicks (hits.kick), not the drum stem."""
from __future__ import annotations

from mvh.stages.choreo import STAGE, mix_kick_rows


def test_mix_kick_rows_scale_strength_to_the_p98_kick():
    items = [{"t": 0.5 * k, "strength": s} for k, s in enumerate([0.1, 0.5, 1.0, 2.0, 0.02] * 10)]
    rows = mix_kick_rows(items, 0.2)
    assert len(rows) == len(items) and all(r["drum"] == "kick" for r in rows)
    assert [r["t"] for r in rows] == [i["t"] for i in items]
    assert all(0.2 <= r["vel"] <= 1.0 for r in rows)
    assert max(r["vel"] for r in rows) == 1.0 and min(r["vel"] for r in rows) == 0.2


def test_empty_and_param():
    assert mix_kick_rows([], 0.2) == []
    assert STAGE.params["mix_kick_vel_floor"] == 0.2


def test_groove_ghost_floor_param():
    """W4 round 2: bars with only ghost-level hits (bleed) are not groove bars."""
    assert STAGE.params["groove_min_hit_vel"] == 0.15
