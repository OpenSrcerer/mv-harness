# ruff: noqa: E501  (long docstrings)
"""R-ML M4 round 2: F3 is only half fixed. White noise still gets a confident key with no flag.

The fixer caps the confidence at 0.25 when fewer than two non-anchor methods have evidence (``len(winners) < 2`` in
``keys.global_confidence``). But KS, Temperley and Albrecht are three profiles correlated against the SAME aggregated
chroma (keys.py itself says "together they count about one vote"). On noise the chroma is not masked (the noise has
harmonic-part energy), the three profiles agree with each other on an arbitrary key, lv-chordia returns 100 % N (no chord
evidence) and S-KEY is gated out (recovered p_max ~0.13 < 0.2). ``winners`` then holds ks/temperley/albrecht: method
credit 1.0, agreement "agree", and the cap never fires.

Probe (out/_wip/r-ml-m4-r2/probe_noskey.log, real lv-chordia, S-KEY absent): 60 s of white noise -> "D minor",
conf 0.609, flags [] (no key:low_confidence, no key:no_tonal_evidence), agreement "agree". Drums only -> "C minor"
conf 0.564. This test reproduces it fast: lv-chordia's real output on noise (one N segment) and no S-KEY (the state a
gated S-KEY leaves behind once the KeyError of test_skey_gate_crash.py is fixed).
"""
from __future__ import annotations

import math

import numpy as np
from m4rml_signals import SR22, beat_grid


def test_white_noise_gets_no_confident_key():
    from mvh.stages.harmony import core

    rng = np.random.default_rng(1)
    y = (rng.standard_normal(60 * SR22) * 0.1).astype(np.float32)
    dur = len(y) / SR22
    beats, bars = beat_grid(dur)

    def lv():                       # what lv-chordia returns on noise (probe: no-chord share 1.0)
        return [{"start_time": 0.0, "end_time": dur, "chord": "N"}]

    res = core.analyse(y, dur, math.ceil(dur * 100), beats, bars, lv, None, {})
    g, flags = res.key_meta["global"], res.key_meta["flags"]
    assert g["conf"] < 0.3 or "key:no_tonal_evidence" in flags or "key:low_confidence" in flags, (g, flags, res.key_meta["agreement"])
