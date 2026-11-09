"""Unit tests for the no-chord tonal gate in keys.global_confidence."""
from __future__ import annotations

import numpy as np

from mvh.stages.harmony import keys as K


def _ev(peak: float, winner: int = 21) -> K.Evidence:
    ev = K.Evidence()
    def vec(top):
        v = np.full(24, 0.1)
        v[winner] = top
        return v
    for n in ("ks", "temperley", "albrecht"):
        setattr(ev, n, vec(peak))
    p = np.full(24, 0.02)
    p[winner] = 0.6
    ev.skey, ev.skey_probs = np.log(p), p
    return ev


def _score(winner=21):
    s = np.zeros(24)
    s[winner] = 3.0
    return s


def test_flat_profiles_without_chords_are_gated():
    conf, info = K.global_confidence(21, _ev(0.25), [21] * 5, _score(), 1.0)
    assert conf <= 0.3 and "key:no_tonal_evidence" in info["flags"]


def test_peaky_unanimous_chroma_without_chords_keeps_key():
    conf, info = K.global_confidence(21, _ev(0.8), [21] * 5, _score(), 1.0)
    assert conf >= 0.5 and "key:no_tonal_evidence" not in info["flags"]
