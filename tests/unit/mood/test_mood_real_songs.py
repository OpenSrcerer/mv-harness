# ruff: noqa: E501  (long literals and docstrings)
"""Snapshots of the mood heads on the four real W0 songs (no ground truth: tolerances and orderings only).

W0 (docs/spike/bench-music.md section 5) measured emoMusic [valence, arousal] on the 1..9 scale: megafauna [3.98, 4.82], versatile [4.60, 5.71],
jeremy [5.13, 6.06], newton-vs-nye [4.40, 6.44]. Run explicitly: pytest -m real tests/unit/mood/test_real_songs.py
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mvh.stages.mood import core as M  # noqa: E402

pytestmark = [pytest.mark.real, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[3]
SONGS = {
    "megafauna": ROOT.parent / "viz" / "MEGAFAUNA.flac",
    "versatile": ROOT.parent / "viz" / "Versatile.flac",
    "jeremy": ROOT / "songs" / "Jeremy (Redux Version).flac",
    "newton-vs-nye": ROOT / "songs" / "Sir Isaac Newton vs Bill Nye.flac",
}
W0_EMO = {"megafauna": (3.98, 4.82), "versatile": (4.60, 5.71), "jeremy": (5.13, 6.06), "newton-vs-nye": (4.40, 6.44)}


@pytest.fixture(scope="module")
def results(heads):
    from mvh.io import audio as aio
    from mvh.testing import heavy

    out = {}
    with heavy("m4-test"):
        for slug, p in SONGS.items():
            if not p.exists():
                continue
            y = np.asarray(aio.decode(p, sr=16000, mono=True).samples, np.float32).reshape(-1)
            n = math.ceil(len(y) / 16000)
            raw = heads.run(y)
            cur = M.to_curves(raw, n, M.silence_mask(y, n))
            out[slug] = (raw, cur, M.global_summary(cur))
    if len(out) < 4:
        pytest.skip("real songs missing")
    return out


def test_emomusic_means_match_the_w0_snapshot(results):
    for slug, (raw, _cur, _g) in results.items():
        v, a = raw.emo.mean(axis=0)
        assert abs(v - W0_EMO[slug][0]) < 0.35 and abs(a - W0_EMO[slug][1]) < 0.35, (slug, v, a)


def test_arousal_ordering_and_confidences(results):
    g = {k: v[2] for k, v in results.items()}
    assert g["megafauna"]["arousal"] < g["newton-vs-nye"]["arousal"] and g["megafauna"]["arousal"] < g["jeremy"]["arousal"]
    for k, x in g.items():
        assert x["valence_conf"] <= M.VALENCE_CONF_CAP and x["arousal_conf"] > x["valence_conf"], (k, x["arousal_conf"], x["valence_conf"])
        assert len(x["tags"]) == 8 and all(0 <= p <= 1 for p in x["tag_p"])


def test_curves_are_finite_and_in_range(results):
    for slug, (_raw, cur, _g) in results.items():
        for arr in (cur.valence, cur.arousal):
            assert np.isfinite(arr).all() and 0.0 <= arr.min() and arr.max() <= 1.0
        assert cur.tags.shape == (56, cur.valence.shape[0]) and 0.0 <= cur.tags.min() and cur.tags.max() <= 1.0
        assert float(cur.arousal.std()) > 0.01, slug               # it moves over the song
