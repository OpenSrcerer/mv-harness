"""singing.json and lines.tsv scored against the synthetic ground truth (PLAN §7: >= 90 % of lines correct after
the voice -> character mapping; the synthetic duet must be exact)."""
from __future__ import annotations

from mvh.stages.meaning.stage import build

THRESHOLD = 0.90  # PLAN §7 rap-battle gate, applied to the synthetic duet


def _truth_lines(truth):
    char_of = {v["voice"]: cid for cid, v in truth["characters"].items()}
    lead: dict[str, str] = {}
    back: dict[str, set[str]] = {}
    for w in truth["words"]:
        lead.setdefault(w["line_id"], w["voice"])
    for w in truth["backing_words"]:
        back.setdefault(w["line_id"], set()).add(w["voice"])
    return lead, back, char_of


def _score(res, truth):
    lead, back, char_of = _truth_lines(truth)
    ok = 0
    for lid, v in lead.items():
        items = [i for i in res["singing"] if i["line_id"] == lid]
        got_lead = {i["voice_id"] for i in items if i["lead_backing"] == "lead"}
        got_back = {i["voice_id"] for i in items if i["lead_backing"] == "backing"}
        want_singers = [char_of[v]] + sorted(char_of[b] for b in back.get(lid, set()))
        if got_lead == {v} and got_back == back.get(lid, set()) and res["singers"][lid] == want_singers:
            ok += 1
    return ok / len(lead)


def test_singing_matches_truth_with_user_intent(synth_source, synth_intent, truth):
    res = build(synth_source(), synth_intent, None, {})
    acc = _score(res, truth)
    assert acc >= THRESHOLD
    assert acc == 1.0  # the synthetic duet is exact
    rows = {r["id"]: r for r in res["lines_rows"]}
    assert rows["L005"]["singer"] == "C1+C2" and rows["L002"]["singer"] == "C2"  # D38
    assert all(i["character_id"] in ("C1", "C2") for i in res["singing"])
    chars = {c["id"]: c for c in res["characters"]}
    assert chars["C1"]["voice_ids"] == ["V1"] and chars["C1"]["lead_backing"] == "lead"
    assert chars["C2"]["lead_backing"] == "both"  # answers in the verse, harmony in the choruses
    assert chars["C1"]["provenance"]["status"] == "user"


def test_singing_pending_uses_voice_proposals(synth_source, truth):
    res = build(synth_source(), None, None, {})
    assert res["meaning"]["status"] == "pending"
    assert _score(res, truth) == 1.0  # meta/voices.json proposes C1 = V1, C2 = V2
    assert all(c["provenance"]["status"] == "draft" for c in res["characters"])


def test_user_line_override_wins(synth_source, synth_intent):
    text = synth_intent + "\n## Singers\nL001: C2\nL009: C2+C1\n"
    res = build(synth_source(), text, None, {})
    assert res["singers"]["L001"] == ["C2"] and res["singers"]["L009"] == ["C2", "C1"]
    it = [i for i in res["singing"] if i["line_id"] == "L009"]
    assert [i["lead_backing"] for i in it] == ["lead", "backing"] and it[0]["voice_id"] == "V2"
    assert all(i["source"] == "user" for i in it)


def test_unmapped_and_missing_spans(synth_source, synth_source_parts):
    files, events = synth_source_parts
    spans = [s for s in events["voice_spans"] if s["line_id"] != "L003"]  # the voices stage missed one line
    res = build(synth_source(events={"voice_spans": spans}), None, None, {})
    it = [i for i in res["singing"] if i["line_id"] == "L003"]
    assert len(it) == 1 and it[0]["source"] == "nearest" and it[0]["review"] and it[0]["voice_id"] in ("V1", "V2")
    # no voices at all: one default voice, flagged
    res2 = build(synth_source(files={"meta/voices.json": None}, events={"voice_spans": []}), None, None, {})
    assert {i["voice_id"] for i in res2["singing"]} == {"V1"} and "voices:absent" in res2["fallbacks"]
    assert all(r["singer"] for r in res2["lines_rows"])


def test_three_voices_with_announcer(synth_source, synth_source_parts):
    """A rap battle: the user names two characters; a third voice (an announcer) gets a proposed character."""
    files, events = synth_source_parts
    spans = [dict(s) for s in events["voice_spans"]]
    for s in spans:
        if s["line_id"] == "L001":
            s["voice_id"] = "V3"
    voices = dict(files["meta/voices.json"])
    voices["voices"] = voices["voices"] + [{"id": "V3", "seconds": 2.0, "n_lines": 1, "proposed_character_id": None, "hint": None}]
    intent = "## Characters\n- C1 Newton = V1\n- C2 Nye = V2\n"
    res = build(synth_source(files={"meta/voices.json": voices}, events={"voice_spans": spans}), intent, None, {})
    chars = {c["id"]: c for c in res["characters"]}
    assert set(chars) == {"C1", "C2", "C3"} and chars["C3"]["voice_ids"] == ["V3"]
    assert chars["C3"]["provenance"]["status"] == "draft" and res["singers"]["L001"] == ["C3"]
