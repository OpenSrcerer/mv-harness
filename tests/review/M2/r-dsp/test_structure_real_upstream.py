"""R-DSP M2 round 2, finding F4 again (major, not fixed): the structure stage still misses the synthetic song's
sections when its upstream is realistic. The round-1 fix (melodic fingerprint, keeping strong boundaries) passes
``test_structure_real_allin1.py`` only because that test still uses the fixture's dynamics and harmony, and the fixture's
``events/dynamics.json`` segments ARE the truth sections (1.0 / 9.0 / 17.0 / 25.0 / 34.5 / 50.5 s): a second circular
input.

``data/synth_real_harmony_dynamics.npz`` holds what the real pipeline produced on the synthetic song (r-dsp-m2-r2, a full
``mvh analyze`` of tests/contract/synth/_truth/synth-song.flac re-run --from rhythm): the harmony stage's chroma12 curves,
the dynamics stage's ``dyn.novelty`` curve, and its dynamics / impacts / silences / stops events. With the recorded real
allin1 (``data/synth_real_allin1.npz``) and the fixture's exact rhythm:

* real harmony only (fixture dynamics kept): sections 1.0 / 9.0 (8 bars) / 25.0 / 34.5 / 50.5 s; chorus#1 at 17.0 s is
  missed (boundary F 0.909) and chorus#2 is not in a repeat group with anything that covers chorus#1;
* real harmony + real dynamics (= the full pipeline): 1.0 / 5.0 / 9.0 (8 bars) / 25.0 / 34.5 / 42.5 / 52.5 s,
  boundary F 0.615 (round 1 full analyze: 0.667). Chorus#1 (17.0) and the outro (50.5) are missed, a 2-bar split at 5.0 s
  and a split inside chorus#2 at 42.5 s are added.
The full ``mvh analyze`` of the synthetic song after the fix gives the same 0.615 result."""
import json
import shutil

import numpy as np
import pytest
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import events, synth_ready, truth

from mvh.stages.rhythm.fusion import f_measure

DATA = __import__("pathlib").Path(__file__).resolve().parent / "data"
DYN_NOVELTY_OFFSET = 1288200      # byte offset of dyn.novelty in curves/core.f32 (same in the fixture and the full run)


def _fixture(root, *, harmony: bool, dynamics: bool):
    fx = synth_ready()
    fx2 = root / "fx"
    shutil.copytree(fx, fx2, ignore=shutil.ignore_patterns("stems", "frames", "viewer.html", "lyrics", "lipsync"))
    z = np.load(DATA / "synth_real_allin1.npz")
    a1 = fx2 / "_intermediate" / "allin1"
    with open(a1 / "allin1.json", "w", encoding="utf-8") as fh:
        json.dump(json.loads(bytes(z["doc"]).decode("utf-8")), fh)
    z["activations"].astype("<f4").tofile(a1 / "activations.f32")
    z["embeddings"].astype("<f4").tofile(a1 / "embeddings.f32")
    r = np.load(DATA / "synth_real_harmony_dynamics.npz")
    if harmony:
        (fx2 / "curves" / "chroma12.f32").unlink()          # never write through a (possibly hard-linked) fixture file
        r["chroma12"].astype("<f4").tofile(fx2 / "curves" / "chroma12.f32")
    if dynamics:
        core = np.fromfile(fx2 / "curves" / "core.f32", dtype="<f4")
        k = DYN_NOVELTY_OFFSET // 4
        core[k:k + len(r["dyn_novelty"])] = r["dyn_novelty"]
        (fx2 / "curves" / "core.f32").unlink()
        core.astype("<f4").tofile(fx2 / "curves" / "core.f32")
        ev = json.loads(bytes(r["events"]).decode("utf-8"))
        for name, text in ev.items():
            (fx2 / "events" / f"{name}.json").unlink()
            with open(fx2 / "events" / f"{name}.json", "w", encoding="utf-8") as fh:
                fh.write(text)
    run_stage("structure", fx2, root / "structure")
    return events(root / "structure", "sections")


@pytest.fixture(scope="module")
def sections_real_harmony(tmp_path_factory):
    return _fixture(tmp_path_factory.mktemp("struct_real_h"), harmony=True, dynamics=False)


@pytest.fixture(scope="module")
def sections_real_pipeline(tmp_path_factory):
    return _fixture(tmp_path_factory.mktemp("struct_real_hd"), harmony=True, dynamics=True)


def _show(sections):
    return [(round(s["t"], 2), s["n_bars"], s["label"], s["repeat_group"]) for s in sections]


def _chorus_groups(sections):
    def at(t):
        return next(s for s in sections if s["t"] - 0.05 <= t < s["t"] + s["d"])
    return at(17.5), at(35.0)


def test_fixture_dynamics_segments_are_the_truth_sections():
    """The second circular input: the fixture's dynamics segments start exactly at the truth section starts."""
    fx = synth_ready()
    with open(fx / "events" / "dynamics.json", encoding="utf-8") as fh:
        dyn = {round(d["t"], 3) for d in json.load(fh)["items"]}
    assert {round(s["t"], 3) for s in truth()["sections"]} <= dyn


def test_boundaries_with_real_harmony(sections_real_harmony):
    tr = truth()
    f = f_measure([s["t"] for s in sections_real_harmony], [s["t"] for s in tr["sections"]], 0.5)
    assert f >= 0.95, (_show(sections_real_harmony), round(f, 3))


def test_chorus_repeat_with_real_harmony(sections_real_harmony):
    c1, c2 = _chorus_groups(sections_real_harmony)
    assert c1["id"] != c2["id"] and c1["repeat_group"] == c2["repeat_group"], _show(sections_real_harmony)


def test_boundaries_with_real_pipeline_upstream(sections_real_pipeline):
    tr = truth()
    f = f_measure([s["t"] for s in sections_real_pipeline], [s["t"] for s in tr["sections"]], 0.5)
    assert f >= 0.95, (_show(sections_real_pipeline), round(f, 3))


def test_chorus_repeat_with_real_pipeline_upstream(sections_real_pipeline):
    c1, c2 = _chorus_groups(sections_real_pipeline)
    assert c1["id"] != c2["id"] and c1["repeat_group"] == c2["repeat_group"], _show(sections_real_pipeline)
