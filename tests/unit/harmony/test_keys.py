import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.synth import m4  # noqa: E402

from mvh.stages.harmony import core  # noqa: E402
from mvh.stages.harmony import keys as K  # noqa: E402
from mvh.stages.harmony import theory as T  # noqa: E402

KEYS = [(0, "major"), (9, "minor"), (7, "major"), (2, "minor"), (3, "major"), (6, "minor"), (10, "major"), (4, "minor")]


def test_zscore_and_posterior():
    z = K.zscore(np.arange(24.0))
    assert abs(z.mean()) < 1e-9 and abs(z.std() - 1) < 1e-9 and np.all(K.zscore(np.ones(24)) == 0)
    p = K.posterior(np.arange(24.0))
    assert abs(p.sum() - 1) < 1e-9 and int(np.argmax(p)) == 23


def test_skey_log_maps_keymap_order_to_ours():
    keymap = ["A Major", "Bb Major", "A minor", "C minor"]
    p = np.array([0.1, 0.2, 0.6, 0.1])
    out = K.skey_log(p, keymap)
    assert int(np.argmax(out)) == T.key_index(9, "minor")
    assert out[T.key_index(10, "major")] > out[T.key_index(9, "major")]


def test_chord_evidence_names_the_diatonic_key():
    chords = [{"t": float(i * 2), "d": 2.0, "root_pc": r, "quality": q, "conf": 1.0}
              for i, (r, q) in enumerate([(7, "maj"), (0, "maj"), (2, "maj"), (7, "maj")] * 2)]
    ev = K.chord_evidence(chords, 0, 16)
    assert int(np.argmax(ev)) == T.key_index(7, "major")


def test_viterbi_is_sticky_and_follows_a_sustained_change():
    home, other = T.key_index(0, "major"), T.key_index(6, "major")
    em = np.zeros((40, 24))
    em[:, home] = 3.0
    em[20:23, other] = 4.0                      # a 15 s blip (3 windows) must not switch
    path = K.viterbi_regions(em, home)
    assert set(path) == {home}
    em2 = np.zeros((60, 24))
    em2[:30, home] = 3.0
    em2[30:, T.key_index(7, "major")] = 3.5     # a sustained change does
    path2 = K.viterbi_regions(em2, home)
    assert path2[0] == home and path2[-1] == T.key_index(7, "major")


def test_regions_absorb_short_segments_and_cover():
    grid = [(5.0 * i, 5.0 * i + 30) for i in range(10)]
    path = np.array([0, 0, 0, 7, 0, 0, 0, 0, 0, 0])
    reg = K.regions_from_path(path, grid, 75.0, min_len_s=20.0)
    assert len(reg) == 1 and reg[0][0] == 0.0 and reg[0][2] == 0
    path2 = np.array([0] * 5 + [7] * 5)
    reg2 = K.regions_from_path(path2, grid, 75.0, min_len_s=10.0)
    assert [r[2] for r in reg2] == [0, 7] and abs(reg2[0][1] - reg2[1][0]) < 1e-9 and reg2[-1][1] == 75.0


def test_agreement_labels():
    a_min, a_maj = T.key_index(9, "minor"), T.key_index(9, "major")
    c_maj = T.key_index(0, "major")
    assert K.agreement_label({"a": a_min, "b": a_min}, a_min) == "agree"
    assert K.agreement_label({"a": a_min, "b": c_maj}, a_min) == "relative"
    assert K.agreement_label({"a": a_min, "b": a_maj}, a_min) == "parallel"
    assert K.agreement_label({"a": a_min, "b": T.key_index(1, "major")}, a_min) == "disagree"


def test_windows_cover_short_and_long_songs():
    assert K.window_grid(20.0, 30.0, 5.0) == [(0.0, 20.0)]
    g = K.window_grid(217.0, 30.0, 5.0)
    assert g[0][0] == 0.0 and abs(g[-1][1] - 217.0) < 1e-9 and all(abs((b - a) - 30.0) < 1e-9 for a, b in g)


@pytest.mark.real
@pytest.mark.parametrize("tonic,mode", KEYS)
def test_rendered_cadences_name_their_key(skey, tonic, mode):
    """I-IV-V-I / i-iv-V-i in 8 keys: the exact key, with a confidence a director can use (>= 0.7)."""
    from mvh.testing import heavy

    x, sr, tr = m4.progression(m4.cadence(tonic, mode), repeats=4)
    y = m4.resample(x, sr, 22050)
    with heavy("m4-test"):
        res = core.analyse(y, tr["duration"], math.ceil(tr["duration"] * 100), tr["beats"], tr["bars"], None, skey, {})
    g = res.key_meta["global"]
    assert (g["tonic_pc"], g["mode"]) == (tonic, mode), res.key_meta["methods"]
    assert g["conf"] >= 0.7
    assert len(res.key_regions) == 1 and res.key_regions[0]["key"] == g["key"]


@pytest.mark.real
@pytest.mark.slow
@pytest.mark.parametrize("a,b", [((0, "major"), (4, "major")), ((9, "minor"), (2, "minor"))])
def test_modulation_is_found_near_the_truth(skey, a, b):
    from mvh.testing import heavy

    x, sr, tr = m4.modulating(a, b)
    y = m4.resample(x, sr, 22050)
    with heavy("m4-test"):
        res = core.analyse(y, tr["duration"], math.ceil(tr["duration"] * 100), tr["beats"], tr["bars"], None, skey, {})
    reg = res.key_regions
    assert len(reg) == 2, reg
    assert (reg[0]["tonic_pc"], reg[0]["mode"]) == a and (reg[1]["tonic_pc"], reg[1]["mode"]) == b
    assert abs(reg[1]["t"] - tr["regions"][1]["t"]) <= 6.0          # boundary within 6 s (30 s windows)
    assert "key:modulation" in res.key_meta["flags"]


def test_key_override_forces_the_key():
    x, sr, tr = m4.progression(m4.cadence(0, "major"), repeats=3)
    y = m4.resample(x, sr, 22050)
    res = core.analyse(y, tr["duration"], math.ceil(tr["duration"] * 100), tr["beats"], tr["bars"], None, None,
                       {"key_override": "F# minor"})
    g = res.key_meta["global"]
    assert g["key"] == "F# minor" and g["conf"] == 1.0 and "key:overridden" in res.key_meta["flags"]
