"""R-DSP M2 round 5, finding F8-r5 (major, synthetic ground truth, fast): the F7-r4 fix (structure
``phrase_layout``, M2-D-phrase-grid) decides where a section's phrase remainder goes by a GLOBAL vote of every other
section start in the song. Sections after the one being phrased vote for "remainder first" and sections before it vote
for "remainder last", so the answer depends on how many sections lie on each side, not on the music of that section.

On the synthetic song the bridge S04 (25.0 s, 5 bars: 4 bars, a 3/4 bar, then a no-pulse stop bar) is truth-phrased
4 + 1 with the remainder at the END (truth P04/P05), and the eight-counts are 25.0 (8), 29.0 (7, partial),
32.5 (4, partial). The default run gets this right. A single ``structure.boundaries`` edit 10 s LATER in the song
(splitting the final chorus at its own phrase boundary 42.5 s, truth P07) adds one "later" start to the vote, so
the bridge flips to 1 + 4 (pickup first) and every bridge eight-count moves: 25.0 (4, partial), 27.0 (8),
31.0 (7, partial). The bridge's music did not change, only the number of sections after it.

The same sec_ranges ambiguity makes a first verse with a trailing extra bar (stop/turnaround bar) indistinguishable from
Jeremy's snapped verse: (0,8),(8,17),(17,25)... always gets the pickup, wherever the extra bar really is.

Upstream: tests/contract/synth fixture (ground truth). No inference."""
import pytest
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import events, synth_ready, truth

BRIDGE = (24.5, 34.4)
SPLIT = {"structure.boundaries": [{"action": "add", "t": 42.5}]}


def _run(root, overrides):
    fx = synth_ready()
    out = {}
    for st in ("structure", "choreo"):
        kw = {"overrides": overrides} if (overrides and st == "structure") else {}
        run_stage(st, fx, root / st, overlays=dict(out), **kw)
        out[st] = root / st
    secs = events(out["structure"], "sections")
    counts = [c for c in events(out["choreo"], "counts") if not c["lead_in"]]
    return secs, counts


def _bridge_counts(counts):
    return [(round(c["t"], 2), c["len"], c["partial"]) for c in counts if BRIDGE[0] <= c["t"] < BRIDGE[1]]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("phrase_grid_nonlocal")
    return {"base": _run(root / "base", None), "split": _run(root / "split", SPLIT)}


def _truth_bridge():
    return [(round(c["t"], 2), c["len"], c["partial"]) for c in truth()["counts"]
            if not c["lead_in"] and BRIDGE[0] <= c["t"] < BRIDGE[1]]


def test_precondition_default_run_matches_truth_and_the_edit_only_splits_the_last_chorus(runs):
    secs_b, counts_b = runs["base"]
    secs_s, _ = runs["split"]
    assert _bridge_counts(counts_b) == _truth_bridge()
    tb = [(round(s["t"], 2), s["n_bars"]) for s in secs_b]
    ts = [(round(s["t"], 2), s["n_bars"]) for s in secs_s]
    # identical up to and including the bridge; the edit only adds a start at 42.5 s inside the final chorus
    assert [x for x in ts if x[0] < 34.0] == [x for x in tb if x[0] < 34.0]
    assert any(abs(x[0] - 42.5) < 0.05 for x in ts) and not any(abs(x[0] - 42.5) < 0.05 for x in tb)


def test_a_boundary_edit_later_in_the_song_does_not_move_the_bridge_eight_counts(runs):
    _, counts_s = runs["split"]
    assert _bridge_counts(counts_s) == _truth_bridge(), (
        f"bridge eight-counts after splitting the final chorus at 42.5 s: {_bridge_counts(counts_s)} "
        f"vs truth {_truth_bridge()}")
