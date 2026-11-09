"""voices without models: intent.md parsing and the k estimate / clustering on synthetic embeddings."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mvh.stages.voices import cluster as K
from mvh.stages.voices.intent import parse_intent

REPO = Path(__file__).resolve().parents[3]


def test_parse_intent_fixture():
    it = parse_intent((REPO / "tests" / "contract" / "synth" / "meaning" / "intent.md").read_text(encoding="utf-8"))
    assert it["n_characters"] == 2
    assert it["voice_to_character"] == {"V1": "C1", "V2": "C2"}


def test_parse_intent_forms():
    """UD1 (D78): the voices stage reads intent.md through the meaning stage's parser: the template only."""
    txt = """<!-- C9 is a comment and must not count -->
## Our notes
Free text never maps or counts: C5 is V1, voices: 7, L001: C2.

characters:
- C1 Newton (voice V2)
- C2 Nye = voice V1
- C3 The announcer
voices:
- V4 -> C3
line_singers:
  L012: C1+C2
"""
    it = parse_intent(txt)
    assert it["n_characters"] == 3 and it["n_voices"] is None
    assert it["voice_to_character"] == {"V1": "C2", "V2": "C1", "V4": "C3"}
    assert it["line_voice"] == {} and it["line_characters"] == {"L012": ["C1", "C2"]}
    assert parse_intent("voices: 4\n")["n_voices"] == 4
    assert parse_intent(None)["n_characters"] is None
    # free text (a markdown list of people) is the user's notes, not a character count
    assert parse_intent("## Characters\n- the girl\n- the boy\n")["n_characters"] is None


def _blobs(sizes, dim=64, spread=0.25, seed=0):
    rng = np.random.default_rng(seed)
    E, lab = [], []
    centres = rng.normal(size=(len(sizes), dim))
    for c, n in enumerate(sizes):
        x = centres[c] + spread * rng.normal(size=(n, dim)) * np.linalg.norm(centres[c]) / np.sqrt(dim)
        E.append(x)
        lab += [c] * n
    E = np.concatenate(E)
    return E / np.linalg.norm(E, axis=1, keepdims=True), np.array(lab)


def test_estimate_k_finds_separated_voices():
    E, lab = _blobs([15, 12, 9, 2])
    k, info = K.estimate_k(E, np.ones(len(E)))
    assert k == 4, info
    got = K.agglo(E, k)
    # same partition up to relabelling
    from sklearn.metrics import adjusted_rand_score

    assert adjusted_rand_score(lab, got) > 0.95


def test_estimate_k_small_sample_takes_the_eigengap_bound():
    # M5-D21: 16 items, two real voices plus a few odd lines: no silhouette hunting below small_n items
    E, lab = _blobs([9, 5, 1, 1], spread=0.25, seed=5)
    k, info = K.estimate_k(E, np.ones(len(E)))
    assert info["reason"].startswith("few items") and k == max(2, info["eigengap_k"]) and k <= 3, info
    k_big, info_big = K.estimate_k(E, np.ones(len(E)), small_n=4)
    assert info_big["reason"].startswith("max silhouette")


def test_estimate_k_single_voice():
    rng = np.random.default_rng(3)
    c = rng.normal(size=64)
    E = c + 0.15 * rng.normal(size=(20, 64)) * np.linalg.norm(c) / 8
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    k, info = K.estimate_k(E, np.ones(20))
    assert k == 1 and info["k2_centroid_cos"] >= 0.6


def test_relabel_first_appearance_and_centroids():
    assert K.relabel_first_appearance([5, 5, 2, 9, 2]).tolist() == [0, 0, 1, 2, 1]
    E = np.array([[1.0, 0], [1, 0], [0, 1.0]])
    C = K.centroids(E, np.array([0, 0, 1]))
    assert np.allclose(C, [[1, 0], [0, 1]])
    assert K.estimate_k(E, np.ones(3))[0] == 1          # fewer than 4 items: one voice


def test_merge_minor_folds_scattered_timbre_changes_but_keeps_a_foreign_singleton():
    rng = np.random.default_rng(5)
    a = rng.normal(size=64)
    b = a + 0.9 * rng.normal(size=64)                  # a timbre variant of the same singer (cos ~0.7)
    far = rng.normal(size=64)                          # a different, unrelated voice
    rows, lab = [], []
    for i in range(30):
        c = 1 if i in (7, 18, 26) else 0               # three isolated lines in the variant timbre
        rows.append((b if c else a) + 0.05 * rng.normal(size=64))
        lab.append(c)
    rows.append(far)                                   # one foreign item (an announcer)
    lab.append(2)
    E = np.array(rows)
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    lab = np.array(lab)
    out, merged = K.merge_minor(E, lab, np.ones(len(E)))
    assert len(merged) == 1 and merged[0]["items"] == 3
    assert sorted(set(out.tolist())) == [0, 1] and out[-1] != out[0]      # the foreign singleton survives
    # a real second voice in a consecutive block is never merged
    lab2 = np.array([0] * 20 + [1] * 10)
    E2 = np.concatenate([np.tile(a, (20, 1)), np.tile(far, (10, 1))]) + 0.05 * rng.normal(size=(30, 64))
    E2 = E2 / np.linalg.norm(E2, axis=1, keepdims=True)
    assert K.merge_minor(E2, lab2, np.ones(30))[1] == []
