# ruff: noqa: E501
"""allin1: layout helpers, the reader (real record and stub copies) and, opt-in (slow), the real 8-fold inference on
the synthetic song's separate_fast stems."""
import numpy as np
import pytest
from tests.synth.m2.ctx import FixtureUpstream, run_stage
from tests.synth.m2.testing import doc, synth_ready, truth

from mvh.stages.allin1 import HARMONIX, activation_matrix, bpm_from_beats, pool_embeddings
from mvh.stages.allin1.read import load_allin1


def test_pool_embeddings_concat_and_mean():
    e = np.zeros((4, 25, 24, 8), np.float32)
    for s in range(4):
        e[s, :, :, :] = s + np.arange(25)[:, None, None]
    out = pool_embeddings(e, 10)
    assert out.shape == (3, 4 * 192)
    assert np.allclose(out[0, :192], np.mean(np.arange(10)))            # bass block, frames 0..9
    assert np.allclose(out[0, 192 * 3:], 3 + np.mean(np.arange(10)))    # vocals block
    assert np.allclose(out[2, :192], np.mean(np.r_[np.arange(20, 25), [24] * 5]))   # last block padded by repetition


def test_activation_matrix_columns():
    T = 50
    acts = {"beat": np.ones(T), "downbeat": np.zeros(T), "segment": np.full(T, 0.5), "label": np.full((10, T), 0.1)}
    m = activation_matrix(acts)
    assert m.shape == (T, 13) and m.dtype == np.dtype("<f4")
    assert np.allclose(m[:, 2], 0.5) and np.allclose(m[:, 3:].sum(axis=1), 1.0)


def test_bpm_from_beats():
    assert bpm_from_beats(np.arange(0, 30, 0.5)) == pytest.approx(120.0)
    assert bpm_from_beats([1.0]) is None


def test_reader_on_stub_fixture_copy():
    fx = synth_ready()
    a = load_allin1(FixtureUpstream("allin1", fx))
    assert a.act is not None and a.columns[:3] == ["beat", "downbeat", "boundary"]
    assert a.label_names == HARMONIX and a.label_probs().shape[1] == 10
    n = -(-truth()["n_samples"] * 100 // truth()["sr"])
    assert abs(a.act.shape[0] - n) <= 2
    assert a.emb is not None and a.emb.shape[1] == a.doc["embeddings"]["dim"]


@pytest.mark.slow
@pytest.mark.timeout(5400)
def test_real_inference_on_synth_stems(tmp_path):
    from mvh.testing import heavy

    with heavy("pytest-m2-allin1"):
        res, ctx, secs = run_stage("allin1", synth_ready(), tmp_path / "a", threads=6)
    d = doc(tmp_path / "a", "allin1.json")
    assert res.status == "ok"
    assert abs(d["bpm_from_beats"] - 120.0) < 1.0
    assert d["activations"]["columns"] == ["beat", "downbeat", "boundary", *HARMONIX]
    assert d["embeddings"]["dim"] == 768 and d["embeddings"]["rate_hz"] == 10.0
    import json

    from tests.synth.m2.ctx import RECORD
    with open(tmp_path / "a" / RECORD, encoding="utf-8") as fh:
        rec = json.load(fh)
    from mvh.runner.ctx import CacheUpstream
    a = load_allin1(CacheUpstream("allin1", tmp_path / "a", rec))
    assert a.act.shape == (d["activations"]["frames"], 13)
    tr = [b["t"] for b in truth()["beats"] if b["in_pulse"]]
    from mvh.stages.rhythm.fusion import f_measure
    assert f_measure(d["beats"], tr, 0.07) >= 0.9
