# ruff: noqa: E501
"""structure on the synthetic song (upstream = the fixture's exact rhythm/allin1/harmony/dynamics) scored against
the generator truth; DP, overrides and the degraded paths."""
import numpy as np
import pytest
from tests.synth.m2.ctx import FixtureCtx, run_stage
from tests.synth.m2.testing import doc, events, synth_ready, truth, validate_all


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    fx = synth_ready()
    o = tmp_path_factory.mktemp("structure") / "structure"
    res, ctx, _ = run_stage("structure", fx, o)
    assert res.status == "ok"
    return o


def _bf(est, ref, tol=0.5):
    from mvh.stages.rhythm.fusion import f_measure
    return f_measure(est, ref, tol)


def test_sections_match_truth(out):
    tr = truth()
    sec = events(out, "sections")
    assert _bf([s["t"] for s in sec], [s["t"] for s in tr["sections"]]) >= 0.95
    assert [s["label"] for s in sec] == [s["label"] for s in tr["sections"]]
    assert [s["repeat_group"] for s in sec] == [s["repeat_group"] for s in tr["sections"]]
    assert [(s["start_bar"], s["n_bars"]) for s in sec] == [(s["start_bar"], s["n_bars"]) for s in tr["sections"]]
    # ids, occurrence labels, contiguity, >= 2 bars
    assert [s["id"] for s in sec] == [f"S{i:02d}" for i in range(1, len(sec) + 1)]
    assert sec[4]["occurrence_label"] == "chorus#2"
    for a, b in zip(sec, sec[1:]):
        assert abs(a["t"] + a["d"] - b["t"]) < 1e-6
    assert all(s["n_bars"] >= 2 for s in sec if s["label"] != "silence")
    assert validate_all(out) == []


def test_phrases_and_edm_roles_match_truth(out):
    tr = truth()
    ph = events(out, "phrases")
    assert [(p["start_bar"], p["n_bars"], p["section_id"]) for p in ph] == [(p["start_bar"], p["n_bars"], p["section_id"]) for p in tr["phrases"]]
    assert doc(out, "meta/structure.json")["phrase_bars"] == 4
    roles = events(out, "edm_roles")
    assert [(r["role"], r["start_bar"], r["n_bars"], r["section_id"]) for r in roles] == \
        [(r["role"], r["start_bar"], r["n_bars"], r["section_id"]) for r in tr["edm_roles"]]
    assert all(r["evidence"] for r in roles)
    meta = doc(out, "meta/structure.json")
    assert meta["repeat_groups"]["C"]["section_ids"] == ["S03", "S05"]


def test_segment_dp_prefers_regular_lengths():
    from mvh.stages.structure import segment_dp

    score = np.zeros(32)
    score[[8, 16, 24]] = 2.0
    score[12] = 0.9                      # weaker candidate off the 8-bar grid
    b = segment_dp(score, 32, 2, 1.0, set(), set())
    assert b == [0, 8, 16, 24]
    b = segment_dp(score, 32, 2, 1.0, {12}, {16})
    assert 12 in b and 16 not in b


def test_overrides_boundaries_and_labels(tmp_path):
    fx = synth_ready()
    ov = {"structure.boundaries": [{"t": 13.02, "action": "add"}, {"t": 50.5, "action": "remove"}],
          "structure.labels": [{"t": 20.0, "label": "drop"}]}
    res, ctx, _ = run_stage("structure", fx, tmp_path / "s", overrides=ov)
    sec = events(tmp_path / "s", "sections")
    ts = [s["t"] for s in sec]
    assert any(abs(t - 13.0) < 0.01 for t in ts) and not any(abs(t - 50.5) < 0.01 for t in ts)
    lab = next(s for s in sec if s["t"] <= 20.0 < s["t"] + s["d"])
    assert lab["label"] == "drop" and lab["conf"] == 1.0
    assert doc(tmp_path / "s", "meta/structure.json")["overrides_applied"]


def test_degrades_without_dynamics_harmony_and_allin1(tmp_path, monkeypatch):
    """Real-song fixtures have no dynamics/chroma; allin1 may be missing: own features carry the stage."""
    fx = synth_ready()
    orig_events, orig_curve, orig_up = FixtureCtx.events, FixtureCtx.curve, FixtureCtx.upstream

    def events_(self, name):
        if name in ("dynamics", "impacts", "stops", "silences"):
            from mvh.runner.spec import StageError
            raise StageError("absent")
        return orig_events(self, name)

    def curve_(self, cid):
        if cid.startswith(("chroma.", "dyn.")):
            from mvh.runner.spec import StageError
            raise StageError("absent")
        return orig_curve(self, cid)

    def up_(self, stage):
        if stage == "allin1":
            from mvh.runner.spec import StageError
            raise StageError("absent")
        return orig_up(self, stage)

    monkeypatch.setattr(FixtureCtx, "events", events_)
    monkeypatch.setattr(FixtureCtx, "curve", curve_)
    monkeypatch.setattr(FixtureCtx, "upstream", up_)
    res, ctx, _ = run_stage("structure", fx, tmp_path / "s")
    assert res.status == "degraded"
    assert {"allin1:unavailable", "chroma:own_cqt", "dynamics:unavailable"} <= set(res.fallbacks)
    sec = events(tmp_path / "s", "sections")
    tr = truth()
    assert _bf([s["t"] for s in sec], [s["t"] for s in tr["sections"]], 0.5) >= 0.7
    assert doc(tmp_path / "s", "meta/structure.json")["labeling"] == "structural"
    roles = events(tmp_path / "s", "edm_roles")
    assert any(r["role"] == "drop" and abs(r["t"] - 34.5) < 0.05 for r in roles)
    assert validate_all(tmp_path / "s") == []
