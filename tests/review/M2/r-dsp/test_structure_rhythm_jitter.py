"""R-DSP M2 round 3, finding F4-r3 (major): F4-r2 is fixed only for the fixture's exact (truth) rhythm. The structure
stage's result flips on bar-time jitter of 1-2 frames (10-20 ms), well inside the rhythm tolerance (beats F1 at +-70 ms),
so the full ``mvh analyze`` of the synthetic song still gets the sections wrong.

* ``test_structure_real_upstream.py`` (round 2) passes because it keeps the fixture's rhythm, whose bars ARE the truth
  bars (a third circular input after allin1 and dynamics).
* The real rhythm stage (beats F1 1.0 on this song) puts two downbeats +18 ms late (7.018 s and 50.518 s; the rest within
  5 ms). ``data/synth_real_rhythm.npz`` holds its events from a fresh full ``mvh analyze`` (r-dsp-m2-r3). With them plus the
  recorded real allin1 / harmony / dynamics the stage returns 0.99 / 5.0 / 9.0 / 17.0 / 25.0 / 34.5 / 50.52 s: a spurious
  2 + 2 bar intro split at 5.0 s (both halves group A), boundary F 0.923. The full mvh analyze gives the same.
* Mechanism: ``features.bar_pattern`` max-pools the drum envelopes into 16 slots whose EDGES sit exactly on the 16th-note
  grid, i.e. on the drum hits. A bar that starts one frame late moves every hit into the previous slot: two identical bars
  get orthogonal pattern vectors (cosine 0.0). ``nov_pat`` at 5.0 s rises 0.42 -> 0.59, the bar score to 2.47, just over the
  same-group merge guard 1.4 x cost = 2.41 (harness: 2.34), so the 2-bar split survives. A constant -10 ms shift of the
  truth bars instead splits the bridge (2 + 3 bars at 29.0 s): F 0.923 again."""
import json
import shutil

import numpy as np
import pytest
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import events, synth_ready, truth

from mvh.stages.rhythm.fusion import f_measure
from mvh.stages.structure import features as fx

DATA = __import__("pathlib").Path(__file__).resolve().parent / "data"
DYN_NOVELTY_OFFSET = 1288200


def _harness(root):
    """Recorded real allin1 + real harmony + real dynamics (as test_structure_real_upstream.py, variant 'pipeline')."""
    fx2 = root / "fx"
    shutil.copytree(synth_ready(), fx2, ignore=shutil.ignore_patterns("stems", "frames", "viewer.html", "lyrics", "lipsync"))
    z = np.load(DATA / "synth_real_allin1.npz")
    a1 = fx2 / "_intermediate" / "allin1"
    with open(a1 / "allin1.json", "w", encoding="utf-8") as fh:
        json.dump(json.loads(bytes(z["doc"]).decode("utf-8")), fh)
    z["activations"].astype("<f4").tofile(a1 / "activations.f32")
    z["embeddings"].astype("<f4").tofile(a1 / "embeddings.f32")
    r = np.load(DATA / "synth_real_harmony_dynamics.npz")
    (fx2 / "curves" / "chroma12.f32").unlink()
    r["chroma12"].astype("<f4").tofile(fx2 / "curves" / "chroma12.f32")
    core = np.fromfile(fx2 / "curves" / "core.f32", dtype="<f4")
    k = DYN_NOVELTY_OFFSET // 4
    core[k:k + len(r["dyn_novelty"])] = r["dyn_novelty"]
    (fx2 / "curves" / "core.f32").unlink()
    core.astype("<f4").tofile(fx2 / "curves" / "core.f32")
    for name, text in json.loads(bytes(r["events"]).decode("utf-8")).items():
        (fx2 / "events" / f"{name}.json").unlink()
        with open(fx2 / "events" / f"{name}.json", "w", encoding="utf-8") as fh:
            fh.write(text)
    return fx2


def _write_events(fx2, name, doc):
    (fx2 / "events" / f"{name}.json").unlink()
    with open(fx2 / "events" / f"{name}.json", "w", encoding="utf-8") as fh:
        fh.write(doc if isinstance(doc, str) else json.dumps(doc))


def _show(sections):
    return [(round(s["t"], 2), s["n_bars"], s["repeat_group"]) for s in sections]


def _f(sections):
    return f_measure([s["t"] for s in sections], [s["t"] for s in truth()["sections"]], 0.5)


@pytest.fixture(scope="module")
def sections_full_pipeline(tmp_path_factory):
    root = tmp_path_factory.mktemp("struct_full_rhythm")
    fx2 = _harness(root)
    ev = json.loads(bytes(np.load(DATA / "synth_real_rhythm.npz")["events"]).decode("utf-8"))
    for name, text in ev.items():
        _write_events(fx2, name, text)
    run_stage("structure", fx2, root / "structure")
    return events(root / "structure", "sections")


def test_real_rhythm_is_within_tolerance():
    """Precondition: the recorded real rhythm is correct by the rhythm thresholds (beats F1 1.0 at +-70 ms; every
    downbeat within 20 ms of the truth bar start)."""
    ev = json.loads(bytes(np.load(DATA / "synth_real_rhythm.npz")["events"]).decode("utf-8"))
    beats = [b["t"] for b in json.loads(ev["beats"])["items"]]
    assert f_measure(beats, [b["t"] for b in truth()["beats"]], 0.07) >= 0.98
    tb = np.array([b["t"] for b in truth()["bars"]])
    for b in json.loads(ev["bars"])["items"]:
        assert np.min(np.abs(tb - b["t"])) <= 0.02


def test_boundaries_with_the_real_rhythm(sections_full_pipeline):
    f = _f(sections_full_pipeline)
    assert f >= 0.95, (_show(sections_full_pipeline), round(f, 3))


@pytest.mark.parametrize("dt_ms", [-10, 10])
def test_boundaries_stable_under_a_10ms_bar_shift(tmp_path, dt_ms):
    fx2 = _harness(tmp_path)
    for name in ("beats", "bars"):
        with open(fx2 / "events" / f"{name}.json", encoding="utf-8") as fh:
            d = json.load(fh)
        for it in d["items"]:
            if it["t"] + dt_ms / 1000.0 >= 0:
                it["t"] = round(it["t"] + dt_ms / 1000.0, 6)
        _write_events(fx2, name, d)
    run_stage("structure", fx2, tmp_path / "structure")
    secs = events(tmp_path / "structure", "sections")
    f = _f(secs)
    assert f >= 0.95, (dt_ms, _show(secs), round(f, 3))


def test_bar_pattern_is_robust_to_one_frame_of_downbeat_jitter():
    """Identical drum bars (hits on the 16th grid, 120 BPM, 2 s bars) whose estimated starts differ by one 10 ms frame
    must keep (nearly) the same pattern fingerprint."""
    n = 200 * 11 + 50
    kick, ons, hat = np.zeros(n), np.zeros(n), np.zeros(n)
    for b in range(10):
        t0 = 100 + 200 * b
        for q in (0, 8):
            kick[int(round(t0 + 12.5 * q))] = 1.0
        for q in range(0, 16, 2):
            hat[int(round(t0 + 12.5 * q))] = 0.6
        for q in (0, 4, 12):
            ons[int(round(t0 + 12.5 * q))] = 1.0
    bars = [{"t": (100 + 200 * b + (1 if b % 2 else 0)) / 100.0, "d": 2.0} for b in range(10)]   # every other bar 10 ms late
    P = fx.bar_pattern([kick, ons, hat], fx.bar_frames(bars, n))
    cos = float(P[2] @ P[3] / (np.linalg.norm(P[2]) * np.linalg.norm(P[3])))
    assert cos >= 0.9, round(cos, 3)
