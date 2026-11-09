"""cues on the synthetic song (fixture upstream = generator truth): tiers, D37 merging, lead-ins, references,
pinned overrides, moments."""
import json

import pytest
from tests.synth.m2.ctx import run_stage
from tests.synth.m2.testing import events, synth_ready, truth, validate_all

from mvh.contract import conventions as cv


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = tmp_path_factory.mktemp("cues") / "cues"
    res, ctx, _ = run_stage("cues", synth_ready(), o)
    assert res.status == "ok"
    return o


def test_one_cue_per_time_and_ids(out):
    cues = events(out, "cues")
    ts = [round(c["t"], 6) for c in cues]
    assert ts == sorted(ts) and len(set(ts)) == len(ts)
    assert [c["id"] for c in cues] == [f"Q{i:04d}" for i in range(1, len(cues) + 1)]
    # next(t) strictly after t reaches every cue
    t, seen = -1.0, []
    while True:
        c = cv.event_next(cues, t)
        if c is None:
            break
        seen.append(c["id"])
        t = c["t"]
    assert seen == [c["id"] for c in cues]
    assert validate_all(out) == []


def test_tiers_kinds_and_lead_ins_match_truth(out):
    mine = {round(c["t"], 6): c for c in events(out, "cues")}
    tru = {round(c["t"], 6): c for c in events(synth_ready(), "cues")}
    for t, b in tru.items():
        if b["tier"] == 4 and b["kind"] == "beat" and t not in mine:
            continue                     # virtual beats (no pulse) are not cut points here (decision M2-D9)
        a = mine[t]
        assert (a["kind"], a["tier"]) == (b["kind"], b["tier"]), t
        kinds_b = [k for k in b["kinds"]]
        kinds_a = a.get("kinds") or [a["kind"]]
        if kinds_a != kinds_b:
            assert kinds_b[-1] == "beat" and kinds_a == kinds_b[:-1], (t, kinds_a, kinds_b)   # only the virtual beat is missing
        assert a["lead_in_s"] == b["lead_in_s"], t
        assert a["next_major_in_s"] == b["next_major_in_s"], t
    drop = next(c for c in mine.values() if c["kind"] == "drop")
    assert drop["lead_in_s"] == 9.5 and drop["source"] == {"file": "events/edm_roles.json", "id": "R02"}


def test_compact_tier4_references(out):
    cues = events(out, "cues")
    beats = [c for c in cues if c["kind"] == "beat"]
    assert beats and all(c["tier"] == 4 and c["strength"] is None and c["lead_in_s"] is None for c in beats)
    assert all("kinds" not in c and c["source"]["file"] == "events/beats.json" for c in beats)
    merged = [c for c in cues if "kinds" in c]
    assert merged and all(c["kinds"][0] == c["kind"] and c["sources"][0] == c["source"] and len(c["kinds"]) > 1 for c in merged)
    size = (out / "events" / "cues.json").stat().st_size
    assert size < (synth_ready() / "events" / "cues.json").stat().st_size


def test_moments(out):
    m = events(out, "moments")
    assert 10 <= len(m) <= 20
    assert sorted(x["rank"] for x in m) == list(range(1, len(m) + 1))
    top = min(m, key=lambda x: x["rank"])
    assert top["kind"] == "drop" and abs(top["t"] - 34.5) < 1e-6
    ids = {c["id"] for c in events(out, "cues")}
    assert all(x["cue_id"] in ids and x["d"] is not None and x["d"] >= 0 for x in m)
    # no lyric text in descriptions (NF5)
    with open(synth_ready() / "lyrics" / "lyrics.json", encoding="utf-8") as fh:
        words = {w["text"].lower() for w in json.load(fh)["words"] if len(w["text"]) > 3}
    for x in m:
        assert not (set(x["description"].lower().replace(",", " ").split()) & words), x["description"]


def test_pinned_override(tmp_path):
    res, ctx, _ = run_stage("cues", synth_ready(), tmp_path / "c", overrides={"cues.pinned": [{"t": 12.01, "note": "hero jump"}]})
    cues = events(tmp_path / "c", "cues")
    pin = [c for c in cues if "pinned" in (c.get("kinds") or [c["kind"]])]
    assert len(pin) == 1 and pin[0]["tier"] == 1 and abs(pin[0]["t"] - 12.0) < 1e-6
    assert res.summary["pinned"] == 1
    assert truth()["bpm"] == 120.0
