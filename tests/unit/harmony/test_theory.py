import numpy as np
import pytest

from mvh.stages.harmony import theory as T


@pytest.mark.parametrize("label,exp", [
    ("C:maj", (0, "maj", None)), ("A:min", (9, "min", None)), ("N", (None, "N", None)), ("Bb:maj", (10, "maj", None)),
    ("D:maj/5", (2, "maj", 9)), ("C:min/b3", (0, "min", 3)), ("G:7", (7, "7", None)), ("F#:min7", (6, "min7", None)),
    ("E:hdim7", (4, "hdim7", None)), ("A:sus4(b7)", (9, "sus4", None)), ("C:maj/3", (0, "maj", 4)), ("D:min/b7", (2, "min", 0)),
])
def test_parse_harte(label, exp):
    assert T.parse_harte(label) == exp


def test_harte_label_roundtrip():
    assert T.harte_label(9, "min") == "A:min"
    assert T.harte_label(None, "N") == "N"
    assert T.harte_label(10, "maj", "Bb") == "Bb:maj"


def test_note_pc_and_key_names():
    assert [T.note_pc(n) for n in ("C", "C#", "Db", "B", "Bb", "E#", "Cb")] == [0, 1, 1, 11, 10, 5, 11]
    assert T.key_name(9, "minor") == "A minor" and T.key_name(10, "major") == "Bb major" and T.key_name(3, "minor") == "Eb minor"
    for pc in range(12):
        for mode in ("major", "minor"):
            assert T.key_from_index(T.key_index(pc, mode)) == (pc, mode)
            assert T.parse_key_label(T.key_name(pc, mode)) == (pc, mode)


def test_key_relations():
    a_min, c_maj, a_maj, d_min, f_maj, e_maj = (T.key_index(9, "minor"), T.key_index(0, "major"), T.key_index(9, "major"),
                                                T.key_index(2, "minor"), T.key_index(5, "major"), T.key_index(4, "major"))
    assert T.key_relation(a_min, a_min) == "exact"
    assert T.key_relation(a_min, c_maj) == "relative"
    assert T.key_relation(a_min, a_maj) == "parallel"
    assert T.key_relation(a_min, d_min) == "fifth" and T.key_relation(c_maj, f_maj) == "fifth"
    assert T.key_relation(a_min, f_maj) == "fifth"          # pitch sets one step apart
    assert T.key_relation(c_maj, e_maj) == "other"
    # symmetric
    for i in range(24):
        for j in range(24):
            assert T.key_relation(i, j) == T.key_relation(j, i)


def test_profile_scores_recover_each_key():
    for pc in range(12):
        for mode, prof in (("major", T.KS_MAJ), ("minor", T.KS_MIN)):
            s = T.profile_scores(np.roll(prof, pc), T.KS_MAJ, T.KS_MIN)
            assert int(np.argmax(s)) == T.key_index(pc, mode)
    assert T.profile_scores(np.zeros(12), T.KS_MAJ, T.KS_MIN).max() == 0.0


def test_templates_and_tones():
    assert T.chord_tones(0, "maj") == (0, 4, 7) and T.chord_tones(9, "min7") == (9, 0, 4, 7)
    bank, ids = T.template_bank()
    assert bank.shape == (24, 12) and np.allclose(np.linalg.norm(bank, axis=1), 1)
    v = np.zeros(12)
    v[[9, 0, 4]] = 1.0
    assert ids[int(np.argmax(bank @ v))] == (9, "min")


def test_chord_key_fit_prefers_diatonic_and_tonic():
    a_min = T.key_index(9, "minor")
    assert T.chord_key_fit(9, "min", a_min) > T.chord_key_fit(5, "maj", a_min) > T.chord_key_fit(1, "maj", a_min)
    assert T.chord_key_fit(7, "maj", a_min) >= 1.0                  # harmonic-minor dominant
    assert T.chord_key_fit(None, "N", a_min) == 0.0
    c_maj = T.key_index(0, "major")
    assert T.chord_key_fit(9, "min", c_maj) == 1.0 and T.chord_key_fit(9, "maj", c_maj) == 0.5
