"""W4A-GAIN / W4A-STABLE: a single silent bar that ends a section (the stop before a drop) is not counted in the
phrase-length prior, so 4 bars + a stop bar is a 4-bar phrase (the synthetic bridge flipped between 25.0 and 27.0 s
on a 0.05 score difference when 4 + 5 and 5 + 4 bars scored the same)."""
from __future__ import annotations

import numpy as np

from mvh.stages.structure import segment_dp


def test_stop_bar_does_not_lengthen_the_phrase():
    n = 13                    # bars 0-3 | 4-7 | 8-12 where bar 12 is a silent stop bar; the next section is the song end
    score = np.full(n, 0.2)
    score[4], score[8], score[9] = 2.0, 1.60, 1.65      # bar 9 slightly stronger than the phrase-grid bar 8
    silent = np.zeros(n, bool)
    silent[12] = True
    with_stop = segment_dp(score, n, 2, 1.0, set(), set(), 0.25, silent)
    assert 8 in with_stop and 9 not in with_stop, with_stop


def test_without_silence_the_old_behaviour_is_kept():
    score = np.zeros(9)
    score[4], score[6] = 3.0, 1.2
    assert segment_dp(score, 9, 2, 1.0, set(), set(), 0.0) == segment_dp(score, 9, 2, 1.0, set(), set(), 0.0, np.zeros(9, bool))


def test_w4_round2_structure_params():
    from mvh.stages.structure import STAGE

    assert STAGE.params["drop_top_min_rise"] == -0.25 and STAGE.params["verse_min_before_chorus"] == 0.25
    assert STAGE.params["analysis_lufs"] == -10.0
