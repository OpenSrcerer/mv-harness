"""F-gain-1: the separate_hq worker's DrumSep analysis level (mvh.sep.level, numpy + scipy only, for the sep env)."""

from __future__ import annotations

import numpy as np
import pytest

from mvh.sep import level


def _music(sr: int = 44100, dur: float = 6.0) -> np.ndarray:
    rng = np.random.default_rng(7)
    t = np.arange(int(sr * dur)) / sr
    env = 0.4 + 0.6 * (np.sin(2 * np.pi * 0.5 * t) > 0)
    x = 0.2 * np.sin(2 * np.pi * 110 * t) * env + 0.05 * rng.standard_normal(t.size) * env
    return np.stack([x, 0.8 * x]).astype(np.float32)


def test_integrated_matches_the_loudness_stage():
    from mvh.stages.loudness.r128 import integrated

    x = _music()
    assert abs(level.integrated_lufs(x, 44100) - integrated(x, 44100)) < 0.1


@pytest.mark.parametrize("g_db", [-20.0, -12.0, -6.0, 6.0])
def test_gain_is_level_invariant(g_db):
    x = _music()
    g0, _ = level.analysis_gain_db(x, 44100)
    g1, _ = level.analysis_gain_db(x * np.float32(10 ** (g_db / 20)), 44100)
    assert abs((g0 - g1) - g_db) < 0.01


def test_silence_and_master_level_keep_gain_zero():
    assert level.analysis_gain_db(np.zeros((2, 44100 * 2), np.float32), 44100)[0] == 0.0
    assert level.analysis_gain_db(_music(), 44100, None)[0] == 0.0


def test_matches_the_w4_an_9_mix_gain():
    from mvh.stages.loudness.level import gain_db_for

    x = _music()
    assert abs(level.analysis_gain_db(x, 44100)[0] - gain_db_for(x, 44100)[0]) < 0.1
