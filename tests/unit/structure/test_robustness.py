"""fixer-m2-r3 (F4-r3): the structure evidence must not flip on a frame or two of downbeat jitter, and a phrase-breaking
short section needs a clear margin over the section cost."""
import numpy as np
import pytest

from mvh.stages.structure import features as fx
from mvh.stages.structure import segment_dp


def _drum_bars(n_bars=8, period=200, start=100):
    n = period * (n_bars + 1) + 50
    kick, ons, hat = np.zeros(n), np.zeros(n), np.zeros(n)
    for b in range(n_bars):
        t0 = start + period * b
        for q in (0, 8):
            kick[int(round(t0 + period / 16 * q))] = 1.0
        for q in range(0, 16, 2):
            hat[int(round(t0 + period / 16 * q))] = 0.6
        for q in (0, 4, 12):
            ons[int(round(t0 + period / 16 * q))] = 1.0
    return [kick, ons, hat], n


@pytest.mark.parametrize("late", [-5, -2, -1, 1, 2, 5])
def test_bar_pattern_tolerates_downbeat_jitter_up_to_half_a_slot(late):
    envs, n = _drum_bars()
    bars = [{"t": (100 + 200 * b + (late if b % 2 else 0)) / 100.0, "d": 2.0} for b in range(8)]
    P = fx.bar_pattern(envs, fx.bar_frames(bars, n))
    for a, b in ((2, 3), (4, 5)):
        cos = float(P[a] @ P[b] / (np.linalg.norm(P[a]) * np.linalg.norm(P[b])))
        assert cos >= 0.95, (late, cos)


def test_bar_pattern_still_separates_grooves():
    envs, n = _drum_bars()
    kick2 = envs[0].copy()
    for b in range(4, 8):                       # bars 4..7: kick on every quarter (four on the floor)
        for q in (4, 12):
            kick2[int(round(100 + 200 * b + 12.5 * q))] = 1.0
    bars = [{"t": (100 + 200 * b) / 100.0, "d": 2.0} for b in range(8)]
    P = fx.bar_pattern([kick2, envs[1], envs[2]], fx.bar_frames(bars, n))
    cos_same = float(P[1] @ P[2] / (np.linalg.norm(P[1]) * np.linalg.norm(P[2])))
    cos_diff = float(P[2] @ P[5] / (np.linalg.norm(P[2]) * np.linalg.norm(P[5])))
    assert cos_same > cos_diff + 0.05


def test_short_section_needs_a_margin_over_the_cost():
    """A 5-bar section with a marginal peak (cost + 0.35) after 2 bars: without the short-section margin the DP cuts it
    2 + 3 (a knife edge that flips with bar jitter); with it the section stays whole. A strong peak still cuts."""
    score = np.zeros(9)
    score[4] = 3.0
    score[6] = 1.35
    assert segment_dp(score, 9, 2, 1.0, set(), set(), 0.0) == [0, 4, 6]
    assert segment_dp(score, 9, 2, 1.0, set(), set(), 0.25) == [0, 4]
    score[6] = 2.0
    assert segment_dp(score, 9, 2, 1.0, set(), set(), 0.25) == [0, 4, 6]
