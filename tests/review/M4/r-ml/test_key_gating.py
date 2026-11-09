"""R-ML M4: key confidence must not come from S-KEY guessing on audio that carries no tonal evidence.

``SKey.log_scores`` peak-normalises every input, so digital silence and near-silent stretches (room tone, a fade
tail, a hidden-track gap) reach the model at full scale and S-KEY returns a guess. The profile, chord and bass
evidence are empty there (the chroma mask drops frames 45 dB under the song's p95), so ``Evidence.methods()`` holds
S-KEY alone; ``zscore`` stretches its near-uniform guess to the full +-3 range and ``global_confidence`` gives a
lone method full "method credit" and full "window agreement" with itself.

20 s of digital silence -> today key "C minor" with conf 0.75 and no flag (probe, out/_wip/r-ml-m4/edge.log).
(Checked and fine: a -60 dBFS noise tail after 64 s of tonal music does not create a confident key region; the
global/neighbour evidence carries it.)
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from m4rml_signals import SR22, beat_grid

pytestmark = pytest.mark.real


def _analyse(y: np.ndarray, skey):
    from mvh.stages.harmony import core
    from mvh.testing import heavy

    dur = len(y) / SR22
    beats, bars = beat_grid(dur)
    with heavy("r-ml-m4-test", threads=3):
        return core.analyse(y, dur, math.ceil(dur * 100), beats, bars, None, skey, {})


def test_digital_silence_has_no_confident_key(skey):
    res = _analyse(np.zeros(20 * SR22, np.float32), skey)
    g = res.key_meta["global"]
    assert g["conf"] < 0.3 or "key:low_confidence" in res.key_meta["flags"], (g, res.key_meta["flags"])

