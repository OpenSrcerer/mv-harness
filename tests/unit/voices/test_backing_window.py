"""S16 (W4): a backing voice span must be backed by backing_vocals stem activity (fast, no models)."""

from __future__ import annotations

import pytest

from mvh.stages.voices.core import backing_window


def test_fully_backed_line_keeps_the_whole_line():
    assert backing_window([(9.0, 13.0)], 10.0, 12.0, 0.5, 1.0) == (10.0, 12.0, 1.0)


def test_no_stem_activity_info_means_no_gating():
    assert backing_window(None, 10.0, 12.0, 0.5, 1.0) == (10.0, 12.0, None)


def test_short_burst_under_a_long_line_is_dropped():
    # Newton L021 shape: a 0.44 s burst under a 1.97 s line
    assert backing_window([(48.3, 48.96)], 48.52, 50.49, 0.5, 1.0) is None


def test_silent_stem_drops_the_span():
    assert backing_window([], 10.0, 12.0, 0.5, 1.0) is None
    assert backing_window([(20.0, 21.0)], 10.0, 12.0, 0.5, 1.0) is None


def test_partly_backed_long_line_is_trimmed_to_the_active_hull():
    a, b, sup = backing_window([(14.0, 15.0), (15.2, 16.5)], 10.0, 20.0, 0.5, 1.0)
    assert (a, b) == (14.0, 16.5)
    assert sup == pytest.approx(2.3 / 2.5)


def test_sparse_hull_is_dropped():
    assert backing_window([(10.0, 10.4), (13.6, 14.0)], 10.0, 18.0, 0.5, 1.0) is None
