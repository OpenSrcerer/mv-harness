# ruff: noqa: E501  (long literals and docstrings)
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.synth import m4  # noqa: E402

from mvh.stages.mood import core as M  # noqa: E402

CLASSES = [f"tag{i}" for i in range(56)]


def _raw(n1=20, n2=30, emo=(5.0, 5.0), deam=(5.0, 5.0)):
    t1 = np.arange(n1) * 1.488 + 1.504
    t2 = np.arange(n2) * 0.992 + 1.04
    tags = np.zeros((n2, 56), np.float32)
    tags[:, 3] = 0.6
    tags[:, 7] = 0.3
    tags[:, 11] = 0.05
    return M.Raw(np.tile(np.array(emo, np.float32), (n1, 1)), np.tile(np.array(deam, np.float32), (n1, 1)), t1, tags, t2, CLASSES)


def test_scale01_maps_the_1_to_9_scale():
    assert np.allclose(M.scale01([1, 5, 9, 0, 12]), [0, 0.5, 1, 0, 1])


def test_curves_interpolate_and_hold_edges():
    raw = _raw()
    raw.emo[:, 1] = np.linspace(1, 9, 20)             # arousal ramps over the patches
    cur = M.to_curves(raw, 30, np.zeros(30, bool))
    assert cur.valence.shape == (30,) and cur.tags.shape == (56, 30) and cur.arousal.dtype == np.float32
    a = cur.aro_emo
    assert np.all(np.diff(a[3:25]) > 0)               # monotone through the interior
    assert abs(a[0] - M.scale01(1.0)) < 1e-6          # held before the first patch centre (1.5 s)
    # fused value is the mean of the two heads
    assert np.allclose(cur.arousal, 0.5 * (cur.aro_emo + cur.aro_deam), atol=1e-6)
    assert np.allclose(cur.tags[3], 0.6, atol=1e-6) and cur.tags.max() <= 1.0


def test_silent_seconds_read_neutral_with_zero_confidence():
    raw = _raw(emo=(8.0, 8.0), deam=(8.0, 8.0))
    silent = np.zeros(30, bool)
    silent[10:20] = True
    cur = M.to_curves(raw, 30, silent)
    assert np.all(cur.valence[10:20] == 0.5) and np.all(cur.arousal[10:20] == 0.5) and cur.tags[:, 10:20].max() == 0.0
    s = M.summarise(cur, 10.0, 10.0)
    assert s["silent"] and s["valence_conf"] == 0.0 and s["arousal_conf"] == 0.0 and s["tags"] == []
    s2 = M.summarise(cur, 0.0, 30.0)                  # mixed span: silent seconds are excluded from the mean
    assert abs(s2["arousal"] - M.scale01(8.0)) < 1e-6


def test_silence_mask_uses_rms():
    y = np.concatenate([np.zeros(16000 * 2), 0.1 * np.sin(np.arange(16000 * 2) / 5)]).astype(np.float32)
    m = M.silence_mask(y, 4)
    assert list(m) == [True, True, False, False]


def test_valence_confidence_is_capped_and_falls_with_head_disagreement():
    agree = M.summarise(M.to_curves(_raw(emo=(6, 7), deam=(6, 7)), 30, np.zeros(30, bool)), 0, 30)
    split = M.summarise(M.to_curves(_raw(emo=(3, 7), deam=(7, 7)), 30, np.zeros(30, bool)), 0, 30)
    assert agree["valence_conf"] <= M.VALENCE_CONF_CAP < agree["arousal_conf"]
    assert split["valence_conf"] < agree["valence_conf"] and split["valence_conf"] <= 0.05 + 1e-9
    # arousal heads agree in both cases: arousal confidence is unchanged and high
    assert abs(split["arousal_conf"] - agree["arousal_conf"]) < 1e-9 and agree["arousal_conf"] >= 0.75
    # per-head values are exposed
    assert abs(split["valence_emomusic"] - M.scale01(3.0)) < 1e-6 and abs(split["valence_deam"] - M.scale01(7.0)) < 1e-6


def test_section_tags_are_ranked_and_thresholded():
    s = M.summarise(M.to_curves(_raw(), 30, np.zeros(30, bool)), 5.0, 10.0, top_tags=3, min_tag_p=0.08)
    assert s["tags"] == ["tag3", "tag7"] and s["tag_p"] == [0.6, 0.3]        # tag11 (0.05) is below the threshold
    g = M.global_summary(M.to_curves(_raw(), 30, np.zeros(30, bool)), n_tags=3)
    assert g["tags"][:3] == ["tag3", "tag7", "tag11"]


def test_short_section_uses_the_nearest_sample():
    cur = M.to_curves(_raw(emo=(2, 2), deam=(2, 2)), 30, np.zeros(30, bool))
    s = M.summarise(cur, 10.2, 0.3)
    assert abs(s["arousal"] - M.scale01(2.0)) < 1e-6 and s["arousal_conf"] <= 0.8 * 0.9 + 1e-9


@pytest.mark.real
def test_arousal_orders_calm_below_energetic_and_silence_is_neutral(heads):
    from mvh.testing import heavy

    out = {}
    with heavy("m4-test"):
        for name, x in (("calm", m4.calm_pad(30)), ("energetic", m4.energetic_beat(30)), ("silence", np.zeros(44100 * 20))):
            y = m4.resample(x, 44100, 16000)
            n = math.ceil(len(x) / 44100)
            out[name] = M.global_summary(M.to_curves(heads.run(y), n, M.silence_mask(y, n)))
    assert out["energetic"]["arousal"] > out["calm"]["arousal"] + 0.08, out           # measured 0.507 vs 0.385
    assert "relaxing" in out["calm"]["tags"][:3] or "meditative" in out["calm"]["tags"][:3]
    assert out["silence"]["valence"] == 0.5 and out["silence"]["arousal"] == 0.5 and out["silence"]["tags"] == []
    for k in ("calm", "energetic"):
        assert out[k]["valence_conf"] <= M.VALENCE_CONF_CAP and out[k]["arousal_conf"] >= out[k]["valence_conf"] - 0.4


@pytest.mark.real
def test_heads_shapes_and_determinism(heads):
    from mvh.testing import heavy

    y = m4.resample(m4.calm_pad(20), 44100, 16000)
    with heavy("m4-test"):
        a, b = heads.run(y), heads.run(y)
    n_frames = 1 + (len(y) - 512) // 256
    assert a.emo.shape == (len(M.F.patch_starts(n_frames, 187, 93)), 2) and a.tags.shape[1] == 56 and len(a.classes) == 56
    assert np.array_equal(a.emo, b.emo) and np.array_equal(a.deam, b.deam) and np.array_equal(a.tags, b.tags)
    assert 1.0 <= a.emo.min() and a.emo.max() <= 9.0 and 0.0 <= a.tags.min() and a.tags.max() <= 1.0
    assert a.t1[0] < a.t1[-1] <= len(y) / 16000
