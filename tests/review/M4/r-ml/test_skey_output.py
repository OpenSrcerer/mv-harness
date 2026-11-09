"""R-ML M4: the S-KEY ONNX export's ``probs`` output is softmax(softmax(logits)), not a flat model.

The pinned community export (musetric/skey-onnx @ 9d90d2a9) appends a second softmax to a head that already
ends in a softmax. With p summing to 1, the exported q_i = exp(p_i) / sum_j exp(p_j) is confined to about
[1 / (23 e + 1), e / (e + 23)] = [0.016, 0.106] whatever the audio is: that is the "flat probability" SPIKE.md and
bench-music §3 report (max .068-.094). The model's own probability is recovered exactly:
p = log q - mean(log q) + 1/24 (sums to 1, all entries in [0, 1]).

Clean synthetic C major cadence: recovered p of the winner 0.87 (exported q 0.094). White noise: p 0.13
(q 0.046). The stage keeps the double-softmaxed q as the "raw probabilities" (``SKey.log_scores``) and z-scores
log q, so the one calibrated confidence the key models give is discarded, and noise or near-silent windows (where
S-KEY is guessing) vote with the same weight as tonal ones.
"""
from __future__ import annotations

import numpy as np
import pytest
from m4rml_signals import cadence

pytestmark = pytest.mark.real


def test_skey_wrapper_returns_the_models_probability_not_a_double_softmax(skey):
    from mvh.testing import heavy

    with heavy("r-ml-m4-test", threads=3):
        _log, p = skey.log_scores(cadence(0, "major"))
    assert p.shape == (24,) and abs(float(p.sum()) - 1.0) < 1e-3
    # a double softmax can never exceed e / (e + 23) = 0.106; the model itself is ~0.87 sure of C major here
    assert float(p.max()) > 0.5, f"S-KEY top probability {p.max():.3f}: the double-softmaxed export output"


def test_skey_probability_separates_tonal_audio_from_noise(skey):
    """The wrapper's probability must be usable as a gate: tonal cadence >> white noise."""
    from mvh.testing import heavy

    rng = np.random.default_rng(0)
    noise = (rng.standard_normal(30 * 22050) * 0.1).astype(np.float32)
    with heavy("r-ml-m4-test", threads=3):
        _l1, p_tonal = skey.log_scores(cadence(9, "minor"))
        _l2, p_noise = skey.log_scores(noise)
    assert float(p_tonal.max()) - float(p_noise.max()) > 0.3, (float(p_tonal.max()), float(p_noise.max()))
