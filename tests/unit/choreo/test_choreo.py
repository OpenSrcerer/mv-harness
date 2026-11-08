# ruff: noqa: E501
"""choreo on the synthetic song with the fixture's exact upstream, scored against the generator truth
(counts, accents formula, grooves, hit points, holds) plus the tables and the drum fallback."""
import csv
import itertools

import numpy as np
import pytest
from tests.synth.m2.ctx import FixtureCtx, load_curve, run_stage
from tests.synth.m2.testing import doc, events, synth_ready, truth, validate_all


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    fx = synth_ready()
    o = tmp_path_factory.mktemp("choreo") / "choreo"
    res, ctx, _ = run_stage("choreo", fx, o)
    assert res.status == "ok" and not res.fallbacks
    return o


def test_counts_equal_truth(out):
    mine, tru = events(out, "counts"), truth()["counts"]
    keys = ("id", "start_beat", "len", "first_count", "phrase_id", "section_id", "partial", "lead_in", "in_pulse")
    assert [{k: c[k] for k in keys} for c in mine] == [{k: c[k] for k in keys} for c in tru]
    for a, b in zip(mine, tru):
        assert abs(a["t"] - b["t"]) < 1e-6 and abs(a["d"] - b["d"]) < 1e-6
        assert np.allclose(a["accents"], b["accents"], atol=0.02), (a["id"], a["accents"], b["accents"])
    lead = mine[0]
    assert lead["id"] == "E000" and lead["first_count"] == 5 and lead["start_beat"] == -3 and lead["lead_in"]
    assert validate_all(out) == []


def test_beats_table_counts_and_accent_formula(out):
    tr = truth()
    with open(out / "tables" / "beats.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(tr["beats"])
    for r in rows:
        assert abs(float(r["accent"]) - tr["accents"][r["beat_index"]]) < 0.02
    # E000 lead-in covers the pickup beat as count 8, E001 starts on bar 1 beat 1
    assert rows[0]["eight_id"] == "E000" and rows[0]["count"] == "8"
    assert rows[1]["eight_id"] == "E001" and rows[1]["count"] == "1"
    with open(out / "tables" / "bars.csv", encoding="utf-8", newline="") as fh:
        bars = list(csv.DictReader(fh))
    assert bars[0]["pickup"] == "1" and bars[0]["section_id"] == ""
    assert bars[1]["section_id"] == "S01" and bars[1]["phrase_id"] == "P01" and bars[1]["groove_id"] == "G01"
    with open(out / "tables" / "sections.csv", encoding="utf-8", newline="") as fh:
        secs = list(csv.DictReader(fh))
    assert [s["edm_role"] for s in secs] == ["", "", "", "build", "drop", ""]
    assert all(s["level"] for s in secs)


def test_grooves_match_truth(out):
    tr = truth()
    mine = {g["bar"]: g for g in events(out, "grooves")}
    gt = {int(b): tr["groove_ids"][p] for b, p in tr["bar_pattern"].items()}
    assert set(mine) == set(gt)
    pairs = list(itertools.combinations(sorted(gt), 2))
    agree = np.mean([(mine[a]["groove_id"] == mine[b]["groove_id"]) == (gt[a] == gt[b]) for a, b in pairs])
    assert agree >= 0.95
    fx_items = {g["bar"]: g for g in events(synth_ready(), "grooves")}
    for b, g in mine.items():
        t = fx_items[b]
        for row in ("kick", "snare"):
            assert [v > 0 for v in g["pattern"][row]] == [v > 0 for v in t["pattern"][row]], (b, row)
        assert abs(g["syncopation"] - t["syncopation"]) < 0.02
    swung = [b for b in range(5, 9)]
    assert all(abs(mine[b]["swing"] - 1.5) < 0.1 for b in swung)
    assert all(abs(mine[b]["swing"] - 1.0) < 0.05 for b in range(18, 26))
    meta = doc(out, "meta/grooves.json")
    assert sum(g["n_bars"] for g in meta["grooves"]) == len(mine)


def test_hit_points_and_holds_match_truth(out):
    tr = truth()
    tru_hp = events(synth_ready(), "hit_points")
    mine = events(out, "hit_points")
    from mvh.stages.rhythm.fusion import f_measure
    assert f_measure([h["t"] for h in mine], [h["t"] for h in tru_hp], 0.03) >= 0.9
    top = min(mine, key=lambda h: h["rank"])
    assert abs(top["t"] - 34.5) < 0.01
    holds = events(out, "holds")
    tru_h = events(synth_ready(), "holds")
    assert [(round(h["t"], 3), h["kind"]) for h in holds] == [(round(h["t"], 3), h["kind"]) for h in tru_h]
    assert tr["formulas"]["holds"]


def test_curves_flash_rule_and_range(out):
    acc = load_curve(out, "choreo.accent")
    mv = load_curve(out, "choreo.movement")
    n = -(-truth()["n_samples"] * 100 // truth()["sr"])
    assert len(acc) == len(mv) == n
    assert np.isfinite(acc).all() and np.isfinite(mv).all() and acc.max() <= 1 and mv.min() >= 0
    from mvh.contract.conventions import flash_samples
    rows = truth()
    for b in rows["beats"][1:10]:
        a = rows["accents"][str(b["beat_index"])] if isinstance(next(iter(rows["accents"])), str) else rows["accents"][b["beat_index"]]
        if a > 0:
            f0, f1 = flash_samples(b["t"])
            assert acc[f0] >= a - 0.02 and acc[f1] >= a - 0.02
    # silence bar 17 (32.5-34.5) is still
    assert mv[3300:3400].max() < 0.5 * mv.max()


def test_drum_fallback_when_drums_absent(tmp_path, monkeypatch):
    fx = synth_ready()
    orig = FixtureCtx.events

    def events_(self, name):
        if name == "drum_hits":
            from mvh.runner.spec import StageError
            raise StageError("absent")
        return orig(self, name)

    monkeypatch.setattr(FixtureCtx, "events", events_)
    res, ctx, _ = run_stage("choreo", fx, tmp_path / "c")
    assert res.status == "degraded" and "drums:own_hpss" in res.fallbacks
    g = events(tmp_path / "c", "grooves")
    assert len(g) >= 20
    drop = [x for x in g if 18 <= x["bar"] <= 21]
    kick_on_beats = np.mean([sum(1 for k in (0, 4, 8, 12) if x["pattern"]["kick"][k] > 0) for x in drop])
    assert kick_on_beats >= 3.0          # four-on-the-floor is recovered from the mix
    assert validate_all(tmp_path / "c") == []
