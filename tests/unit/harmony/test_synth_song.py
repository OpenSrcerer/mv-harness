"""The contract synthetic song (A minor, Am-F-C-G loop, exact chord truth) through the real models."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mvh.stages.harmony import core  # noqa: E402

pytestmark = [pytest.mark.real, pytest.mark.slow]


@pytest.fixture(scope="module")
def result(synth_song, skey, tmp_path_factory):
    from scipy.io import wavfile

    from mvh.stages.harmony import chords as C
    from mvh.testing import heavy

    wav = tmp_path_factory.mktemp("lv") / "mix22k.wav"
    wavfile.write(str(wav), 22050, synth_song["y"])
    with heavy("m4-test"):
        return core.analyse(synth_song["y"], synth_song["duration"], synth_song["n_curve"], synth_song["beats"], synth_song["bars"],
                            lambda: C.run_lv_chordia(wav), skey, {})


def _label_accuracy(truth, mine, step=0.01):
    ok = n = 0
    for t in np.arange(0.0, truth[-1]["t"] + truth[-1]["d"] - 1e-6, step):
        a = next(c for c in truth if c["t"] <= t < c["t"] + c["d"])
        b = next(c for c in mine if c["t"] <= t < c["t"] + c["d"])
        n += 1
        ok += a["label"] == b["label"]
    return ok / n


def test_chord_label_accuracy_on_the_synthetic_song(result, synth_song):
    assert result.chord_source == "lv-chordia"
    acc = _label_accuracy(synth_song["chords"], result.chords)
    assert acc >= 0.90, acc                      # measured 1.00


def test_chord_boundaries_land_on_truth_beats(result, synth_song):
    truth_t = np.array([c["t"] for c in synth_song["chords"]])
    mine = [c["t"] for c in result.chords][1:]
    err = [float(np.min(np.abs(truth_t - t))) for t in mine]
    assert np.mean(np.array(err) < 0.06) >= 0.9, err      # snapped to the beat grid = the truth grid


def test_bass_pitch_class_matches_where_a_bass_plays(result, synth_song):
    truth = {round(c["t"], 2): c for c in synth_song["chords"] if c["t"] >= 5.0 and c["label"] != "N"}
    ok = n = 0
    for c in result.chords:
        tc = truth.get(round(c["t"], 2))
        if tc is not None and c["root_pc"] is not None and c["t"] < 50:
            n += 1
            ok += c["bass_pc"] == tc["bass_pc"]
    assert n >= 15 and ok / n >= 0.8


def test_key_is_a_minor_with_alternatives_and_honest_confidence(result):
    g = result.key_meta["global"]
    assert g["key"] == "A minor" and g["tonic_pc"] == 9 and g["mode"] == "minor"
    # vi-IV-I-V reads as C major to S-KEY and the profiles: the stage must say so instead of claiming certainty
    assert g["conf"] < 0.9 and result.key_meta["agreement"] in ("relative", "agree")
    alts = result.key_meta["methods"]["ensemble"]["alternatives"]
    assert any(a["key"] == "C major" and a["relation"] == "relative" for a in alts)
    assert len(result.key_regions) == 1 and abs(result.key_regions[0]["d"] - 56.5) < 0.1


def test_chroma_curve_matches_the_chord_truth(result, synth_song):
    """The 100 Hz chroma curve, averaged over each chord, is closest to the true chord's triad template (24 candidates)."""
    from mvh.stages.harmony import theory as T

    c = result.chroma_curve
    assert c.shape == (12, synth_song["n_curve"]) and c.dtype == np.float32 and 0.0 <= c.min() and c.max() <= 1.0
    bank, ids = T.template_bank()
    hits = n = 0
    for ch in synth_song["chords"]:
        if ch["label"] == "N":
            continue
        a, b = int((ch["t"] + 0.5) * 100), int((ch["t"] + ch["d"] - 0.2) * 100)
        v = c[:, a:b].mean(axis=1)
        n += 1
        hits += ids[int(np.argmax(bank @ (v / np.linalg.norm(v))))] == (ch["root_pc"], ch["quality"])
    assert n == 26 and hits / n >= 0.9          # measured 26 / 26


def test_summary_and_flags(result):
    s = result.summary
    assert 0.0 <= s["no_chord_share"] <= 0.25 and s["distinct_chords"] >= 4 and s["chord_source"] == "lv-chordia"
