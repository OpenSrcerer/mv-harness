"""R-DSP M2 finding F4 (major): the structure synthetic-truth tests are circular, and with a realistic allin1 the
stage misses a section boundary and the chorus repeat on the synthetic song.

tests/unit/structure/test_structure.py scores the stage against the generator truth with the fixture's allin1
intermediate, whose ``segments`` ARE the truth sections with the truth labels (start/intro/verse/chorus/bridge/
chorus/outro at exactly 1.0, 9.0, 17.0, 25.0, 34.5, 50.5 s), so "sections match truth" passes by copying allin1.

``data/synth_real_allin1.npz`` is the REAL all-in-one-infer output (harmonix-all, 8 folds) of the allin1 stage on
the synthetic song, recorded by r-dsp-m2 from a full ``mvh analyze`` run (activations at 100 Hz, embeddings at 10 Hz,
float16). allin1 calls 0.99-34.49 s one 'verse' segment and 34.49-56.5 s 'chorus'. Everything else upstream stays
the fixture's exact rhythm / harmony / dynamics. With it the stage:
* merges intro and verse (no boundary at 9.0 s, where the swung groove, bass line and the vocals enter): S01 is 8 bars;
* puts chorus#1 (17.0 s) and chorus#2 (34.5 s) in different repeat groups (truth: both C), so the one repeated
  section of the song is not recognised.
In the full ``mvh analyze`` of the synthetic song (real dynamics and harmony too) the sections were
0.99/9.0/25.0/34.5/42.5/52.5 s: chorus#1 at 17.0 s and the outro at 50.5 s were missed (boundary F 0.667)."""
import json
import shutil

import numpy as np
import pytest
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import events, synth_ready, truth

from mvh.stages.rhythm.fusion import f_measure

DATA = __import__("pathlib").Path(__file__).resolve().parent / "data" / "synth_real_allin1.npz"


@pytest.fixture(scope="module")
def sections(tmp_path_factory):
    fx = synth_ready()
    root = tmp_path_factory.mktemp("struct_real_a1")
    fx2 = root / "fx"
    shutil.copytree(fx, fx2, ignore=shutil.ignore_patterns("stems", "audio", "frames", "viewer.html", "lyrics", "lipsync"))
    z = np.load(DATA)
    a1 = fx2 / "_intermediate" / "allin1"
    doc = json.loads(bytes(z["doc"]).decode("utf-8"))
    with open(a1 / "allin1.json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    z["activations"].astype("<f4").tofile(a1 / "activations.f32")
    z["embeddings"].astype("<f4").tofile(a1 / "embeddings.f32")
    run_stage("structure", fx2, root / "structure")
    return events(root / "structure", "sections")


def test_fixture_allin1_is_the_truth(tmp_path):
    """The circularity itself: the fixture allin1 segments reproduce the truth sections and labels exactly."""
    fx = synth_ready()
    with open(fx / "_intermediate" / "allin1" / "allin1.json", encoding="utf-8") as fh:
        segs = json.load(fh)["segments"]
    tr = truth()
    starts = {round(s["start"], 3): s["label"] for s in segs}
    assert all(starts.get(round(s["t"], 3)) == s["label"] for s in tr["sections"])
    # ...so the unit test can only show the stage copies allin1; the real-allin1 tests below show what it does


def test_section_boundaries_with_real_allin1(sections):
    tr = truth()
    f = f_measure([s["t"] for s in sections], [s["t"] for s in tr["sections"]], 0.5)
    assert f >= 0.95, ([(s["t"], s["n_bars"], s["label"]) for s in sections], f)


def test_chorus_repeat_group_with_real_allin1(sections):
    def at(t):
        return next(s for s in sections if s["t"] - 0.05 <= t < s["t"] + s["d"])

    c1, c2 = at(17.5), at(35.0)
    assert c1["id"] != c2["id"]
    assert c1["repeat_group"] == c2["repeat_group"], [(s["t"], s["label"], s["repeat_group"]) for s in sections]
