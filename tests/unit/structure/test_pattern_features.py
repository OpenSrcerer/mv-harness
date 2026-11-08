"""Drum / onset pattern fingerprint used as boundary evidence (structure.features.bar_pattern)."""
import numpy as np

from mvh.stages.structure import features as fx


def _env(n, period, offset=0):
    e = np.zeros(n)
    e[offset::period] = 1.0
    return e


def test_same_pattern_same_vector_and_a_groove_change_differs():
    spans = [(i * 100, (i + 1) * 100) for i in range(8)]
    e = np.concatenate([_env(400, 25), _env(400, 20, 5)])      # 4 bars of 4 hits, then 4 bars of 5 hits
    X = fx.bar_pattern([e, e, e], spans)
    assert X.shape == (8, 48)
    assert np.allclose(X[0], X[1]) and np.allclose(X[4], X[5])
    assert not np.allclose(X[3], X[4])
    S = fx.cosine_ssm(X - X.mean(axis=0, keepdims=True))
    assert S[0, 1] > S[3, 4]


def test_bars_beyond_the_curve_do_not_crash():
    e = _env(300, 25)
    spans = [(0, 100), (100, 200), (200, 300), (300, 400), (400, 500)]   # the last two lie past the curve end
    X = fx.bar_pattern([e], spans)
    assert X.shape == (5, 16) and np.isfinite(X).all()
