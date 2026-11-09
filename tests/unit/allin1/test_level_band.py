"""W4A-GAIN: allin1's analysis copy is brought into the commercial-master loudness band (pure gain, timing untouched)."""
from __future__ import annotations

import numpy as np
import pytest

from mvh.stages.allin1 import level_gain_db
from mvh.stages.loudness.r128 import integrated

SR = 44100


def _stems(level: float) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    t = np.arange(10 * SR) / SR
    out = {"bass": 0.3 * np.sin(2 * np.pi * 55 * t), "drums": 0.2 * rng.standard_normal(t.size) * (np.sin(2 * np.pi * 2 * t) > 0.9),
           "other": 0.2 * np.sin(2 * np.pi * 440 * t), "vocals": 0.2 * np.sin(2 * np.pi * 220 * t)}
    return {k: np.vstack([v, v]).astype(np.float32) * level for k, v in out.items()}


def _sum_lufs(stems, gain_db):
    tot = sum(v.astype(np.float64) for v in stems.values()) * 10 ** (gain_db / 20)
    return integrated(tot, SR)


@pytest.mark.parametrize("level", [0.01, 0.05, 0.2, 1.0, 3.0])
def test_quiet_and_hot_masters_land_in_the_band(level):
    st = _stems(level)
    g, lv = level_gain_db(st, SR, [-16.0, -6.0])
    after = _sum_lufs(st, g)
    assert -16.05 <= after <= -5.95, (lv, g, after)
    if -16.0 <= lv <= -6.0:
        assert g == 0.0          # inside the band nothing changes (the four real songs)


def test_the_same_song_at_two_levels_gets_the_same_analysis_level():
    a, b = _stems(0.01), _stems(0.04)      # 12 dB apart, both below the band
    ga, _ = level_gain_db(a, SR, [-16.0, -6.0])
    gb, _ = level_gain_db(b, SR, [-16.0, -6.0])
    assert abs(_sum_lufs(a, ga) - _sum_lufs(b, gb)) < 0.05


def test_disabled_and_silent():
    st = _stems(0.1)
    assert level_gain_db(st, SR, None)[0] == 0.0
    z = {k: np.zeros_like(v) for k, v in st.items()}
    assert level_gain_db(z, SR, [-16.0, -6.0])[0] == 0.0


# ------------------------------------------------------------------ W4V-GAIN-REAL: one fixed analysis level (W4-AN-9)
def _mix(level: float) -> np.ndarray:
    return sum(v.astype(np.float64) for v in _stems(level).values())


@pytest.mark.parametrize("level", [0.05, 0.2, 1.0, 3.0])
def test_fixed_target_puts_every_master_at_minus_10_lufs(level):
    from mvh.stages.loudness.level import ANALYSIS_LUFS, gain_db_for

    x = _mix(level)
    g, lv = gain_db_for(x, SR)
    assert abs(integrated(x * 10 ** (g / 20), SR) - ANALYSIS_LUFS) < 0.05, (lv, g)


def test_a_loud_master_and_its_minus_12db_copy_get_the_same_analysis_input():
    """The case the band missed: a master inside [-16, -6] (here about -9 LUFS) and its -12 dB copy."""
    from mvh.stages.loudness.level import gain_db_for

    a = _mix(1.0)
    b = a * 10 ** (-12 / 20)
    ga, la = gain_db_for(a, SR)
    gb, lb = gain_db_for(b, SR)
    assert -16.0 <= la <= -6.0 and abs((la - lb) - 12.0) < 0.01
    ya, yb = a * 10 ** (ga / 20), b * 10 ** (gb / 20)
    assert np.max(np.abs(ya - yb)) < 1e-6 * np.max(np.abs(ya))


def test_stage_default_is_a_fixed_target():
    from mvh.stages.allin1 import STAGE

    assert STAGE.params["level_target_lufs"] == -10.0
    assert "level_band_lufs" not in STAGE.params
