# ruff: noqa: E501
"""R-DSP M2 finding F3 (major): sections shorter than 2 bars are emitted, against the frozen contract
(``events/sections.json``: "segments shorter than 2 bars are merged"; PLAN §5 structure).

``structure.segment_dp`` deliberately lets the FIRST section be shorter than ``min_len`` ("a short first section (an
intro bar before the phrase grid)"): with only modest boundary evidence on bar 2 it returns a 1-bar section, and the
later same-group merge (``merge_repeat_max_bars`` 8) does not absorb it when the next section is 8 bars long. On the
real songs this happens on 2 of 4: jeremy S01 (0.5 s, 1 bar, intro, group A) + S02 (3.0 s, 8 bars, intro, group A)
and megafauna S01 (1.46 s, 1 bar, intro, A) + S02 (3.46 s, 8 bars, intro, A) - a lone 1-bar "intro" section with its
own tier-1 cue and a 4-beat partial eight-count before the real intro (r-dsp-m2 replay runs)."""
import numpy as np

from mvh.stages.structure import segment_dp


def _lengths(bounds, n):
    edges = list(bounds) + [n]
    return [b - a for a, b in zip(edges, edges[1:])]


def test_segment_dp_never_returns_a_one_bar_first_section():
    score = np.zeros(17)
    score[1] = 1.5            # moderate evidence one bar in (an intro bar / pickup-like bar before the grid)
    score[9] = 2.0            # the real 8-bar boundary
    bounds = segment_dp(score, 17, 2, 1.0, set(), set())
    assert min(_lengths(bounds, 17)) >= 2, bounds


def test_segment_dp_min_len_holds_everywhere_without_forced_boundaries():
    rng = np.random.default_rng(7)
    for _ in range(50):
        n = int(rng.integers(8, 48))
        score = rng.gamma(1.0, 1.0, n)
        bounds = segment_dp(score, n, 2, 1.0, set(), set())
        assert min(_lengths(bounds, n)) >= 2, (n, bounds)
