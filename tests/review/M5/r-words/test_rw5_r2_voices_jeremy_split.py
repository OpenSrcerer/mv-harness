"""R-WORDS M5 round 2 (major): one singer (Jeremy) is now split into 4 voices.

After the alignment fixes the lyrics line spans of Jeremy moved slightly (L033-L040 mostly); the voices stage, whose
code did not change, now estimates 4 voices for a one-singer song (round 1: 1 voice). meta/voices.json of this
round's real-jeremy run: k2 centroid cosine 0.560 (< 0.6) and k2 silhouette 0.112 (>= 0.08), so the "same voice"
test passes through; every silhouette is between 0.087 and 0.141 (no cluster structure), the best is k = 7, and
merge_minor folds only 3 small clusters, leaving V1 85 s / 26 lines, V2 85 s / 14 lines, V3 10 s, V4 33 s. lipsync
then writes 4 mouth channels and 9 backing spans are invented. The k estimate flips on tiny input changes: on
the round-1 spans jittered by +-0.15 s it gives 1 voice 7 times and 2 voices once (probe_voices_k.py).

The spans below are this round's lead voice_spans for real Jeremy (times only, from the stage's own output); the
test embeds them exactly as the stage does (ECAPA on lead_vocals) and runs the stage's estimate_k + merge_minor.
Fix suggestion: require real separation before k > 1 in estimate mode (e.g. best silhouette >= 0.2, or a clear margin
over k = 2 and over a shuffled baseline), keep k = 1 when every silhouette is low, and flag review instead of
splitting.

Opt-in (real song, real model): ``-m real`` or ``MVH_REAL_TESTS=1``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.real

REPO = Path(__file__).resolve().parents[4]
STEM = REPO / "tests" / "contract" / "real-jeremy" / "stems" / "lead_vocals.flac"
SPANS = [(21.98, 24.4), (25.0, 26.92), (27.24, 29.4), (29.82, 31.55), (31.9, 34.69), (33.6, 40.46), (40.98, 44.39),
         (45.54, 51.64), (51.2, 54.61), (55.76, 59.8), (58.34, 64.48), (67.38, 76.92), (77.2, 79.51), (79.84, 81.64),
         (82.26, 85.08), (86.5, 88.93), (89.76, 92.91), (93.2, 95.35), (95.98, 99.22), (99.96, 103.86), (102.82, 104.17),
         (105.1, 107.18), (108.02, 113.47), (113.8, 117.86), (118.3, 124.28), (123.92, 127.34), (128.48, 131.8),
         (131.06, 137.28), (140.22, 146.36), (149.2, 155.68), (166.28, 170.14), (170.16, 174.66), (174.66, 184.96),
         (184.98, 191.16), (194.06, 200.14), (203.08, 205.5), (205.82, 207.27), (207.56, 209.99), (210.76, 213.28),
         (211.94, 220.24)]


def test_one_singer_is_not_split_into_several_voices(tmp_path):
    if not STEM.is_file():
        pytest.skip("real jeremy stem not present")
    from tests.synth.m5.harness import slot

    from mvh.io import audio as aio
    from mvh.runner import models
    from mvh.stages.voices import cluster as K
    from mvh.stages.voices import embed as EM

    lead = aio.decode(STEM, sr=16000, mono=True).samples[0]
    h = models.handle("speechbrain_ecapa_voxceleb")
    with slot("r-words-m5-r2:review-test", threads=6):
        emb = EM._ecapa(next(iter(h.files.values())).parent, tmp_path / "ecapa", 6)
        E = emb.many([lead[int(a * 16000):int(b * 16000)] for a, b in SPANS])
    w = np.array([b - a for a, b in SPANS])
    k, info = K.estimate_k(E, w)              # stage defaults: k_max 8, same_voice_cos 0.6, min_silhouette 0.08
    lab = K.agglo(E, k)
    if k >= 2:
        lab, _merged = K.merge_minor(E, lab, w)
    n_voices = int(lab.max()) + 1
    assert n_voices <= 2, (f"one singer split into {n_voices} voices (k before merge {k}, k2 cos {info.get('k2_centroid_cos')}, "
                           f"k2 silhouette {info.get('k2_silhouette')}, silhouettes {info.get('silhouette')})")
