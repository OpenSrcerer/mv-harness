"""R-ML M4 round 2: the S-KEY p_max gate (fix for F1) crashes the harmony stage when S-KEY is unsure.

``keys.Evidence.methods()`` now drops ``skey`` when ``skey_weight(skey_probs)`` is 0 (top recovered probability under
0.2). ``core.analyse_key`` builds ``methods`` from ``g.methods()`` and then, whenever ``g.skey is not None``, writes
``methods["skey"]["window_agreement"]`` etc. When the song-level S-KEY probability (the mean of the window and whole-song
probabilities) peaks under 0.2, ``methods`` has no ``"skey"`` entry and the stage dies with ``KeyError: 'skey'``.

Hit in the probe (out/_wip/r-ml-m4-r2/probe_synth.log) on 60 s of white noise, 60 s of pink noise and the r1
``synth_noise`` signal, with the real S-KEY model. The same happens on tonal music whenever S-KEY is unsure (a song
whose windows S-KEY reads as different keys averages to a low p_max): the first test drives that with a stub S-KEY so it
runs fast and without models.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from m4rml_signals import SR22, beat_grid, cadence


class _UnsureSKey:
    """Stands in for keys.SKey: a recovered probability that peaks at 0.15 (below the 0.2 vote gate)."""

    def __init__(self):
        from mvh.stages.harmony import theory as T

        self.keymap = [T.key_name(pc, mode) for mode in ("major", "minor") for pc in range(12)]

    def log_scores(self, y22):
        from mvh.stages.harmony import keys as K

        p = np.full(24, 0.85 / 23)
        p[self.keymap.index("C major")] = 0.15
        return K.skey_log(p, self.keymap), p


def _analyse(y, skey):
    from mvh.stages.harmony import core

    dur = len(y) / SR22
    beats, bars = beat_grid(dur)
    return core.analyse(y, dur, math.ceil(dur * 100), beats, bars, None, skey, {})


def test_unsure_skey_does_not_crash_the_stage():
    """A clear A minor cadence; S-KEY unsure everywhere -> the key comes from the other methods, no exception."""
    res = _analyse(cadence(9, "minor", reps=6), _UnsureSKey())
    assert res.key_meta["global"]["key"] == "A minor"


@pytest.mark.real
def test_white_noise_does_not_crash_the_stage(skey):
    from mvh.testing import heavy

    rng = np.random.default_rng(1)
    y = (rng.standard_normal(40 * SR22) * 0.1).astype(np.float32)
    with heavy("r-ml-m4-r2-test", threads=3):
        res = _analyse(y, skey)
    assert res.key_meta["global"]["conf"] < 0.3 or "key:low_confidence" in res.key_meta["flags"]
