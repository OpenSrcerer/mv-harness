from __future__ import annotations

import numpy as np

from mvh.stages.harmony import keys as K


def _ev():
    ev = K.Evidence()
    v = np.zeros(24)
    v[5] = 1.0
    ev.skey = v
    ev.ks = v.copy()
    p = np.full(24, 0.03)
    p[5] = 0.7
    ev.skey_probs = p
    return ev


def test_no_chord_share_in():
    items = [{"t": 0.0, "d": 10.0, "root_pc": 0}, {"t": 10.0, "d": 10.0, "root_pc": None}]
    assert abs(K.no_chord_share_in(items, 0.0, 20.0) - 0.5) < 1e-9
    assert K.no_chord_share_in([], 0.0, 5.0) == 1.0


def test_all_no_chord_caps_confidence():
    ev = _ev()
    conf, info = K.global_confidence(5, ev, [5] * 10, ev.skey, 1.0)
    assert conf <= 0.3 and "key:no_tonal_evidence" in info["flags"]


def test_tonal_share_does_not_cap():
    ev = _ev()
    conf, info = K.global_confidence(5, ev, [5] * 10, ev.skey, 0.1)
    assert "key:no_tonal_evidence" not in info["flags"]
