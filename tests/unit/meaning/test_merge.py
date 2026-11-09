"""Merge precedence (user > draft > audio facts), status, citations, orphans, the drafting bundle, privacy."""
from __future__ import annotations

import copy
import json

from mvh.contract import schemas
from mvh.stages.meaning.cites import check_claims
from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build


def _sec(res, sid):
    return next(s for s in res["meaning"]["sections"] if s["section_id"] == sid)


def test_status_lifecycle(synth_source, synth_intent, synth_authored):
    assert build(synth_source(), None, None, {})["meaning"]["status"] == "pending"
    assert build(synth_source(), None, synth_authored, {})["meaning"]["status"] == "draft"
    assert build(synth_source(), synth_intent, synth_authored, {})["meaning"]["status"] == "user"


def test_user_wins_draft_fills_gaps(synth_source, synth_intent, synth_authored):
    res = build(synth_source(), synth_intent, synth_authored, {})
    m = res["meaning"]
    assert m["logline"] == parse_intent(synth_intent)["logline"] and m["field_sources"]["logline"] == "user"
    assert m["setting"] == synth_authored["setting"] and m["field_sources"]["setting"] == "draft"
    s1 = _sec(res, "S01")
    assert s1["feel"] == "slow drift over dark water" and s1["field_sources"]["feel"] == "user"
    assert s1["movement_hint"] and s1["field_sources"]["movement_hint"] == "draft"  # gap filled by the draft
    s3 = _sec(res, "S03")  # the user wrote nothing for S03
    assert s3["feel"] == next(x for x in synth_authored["sections"] if x["section_id"] == "S03")["feel"]
    assert s3["provenance"]["status"] == "draft"
    s5 = _sec(res, "S05")  # 'Drop:' anchors to the drop's section through events/edm_roles.json
    assert s5["feel"] == "wide shots, every lantern at once"
    # do-not rules are the user's words only, on every section too
    assert m["do_not"] == parse_intent(synth_intent)["do_not"]
    assert all(r in s3["do_not"] for r in m["do_not"])
    # audio facts are labelled as such
    assert s1["emotion"]["audio"] and s1["field_sources"]["emotion.audio"] == "audio"
    assert schemas.validate(m, "mvh/files/meaning") == []


def test_draft_cannot_claim_user(synth_source, synth_authored):
    d = copy.deepcopy(synth_authored)
    d["status"] = "user"
    d["themes"][0]["source"] = "user"
    res = build(synth_source(), None, d, {})
    assert res["meaning"]["status"] == "draft"
    assert all(t["source"] != "user" and t["status"] == "draft" for t in res["meaning"]["themes"])
    assert any("status is not 'draft'" in w for w in res["warnings"])


def test_citation_checks():
    doc = {"themes": [{"text": "x", "source": "lyric", "cites": [{"id": "L999"}, {"id": "L001", "quote": " ".join(["w"] * 14)},
                                                                   {"t0": 5.0, "t1": 999.0}]},
                      {"text": "y", "cites": []}, {"cites": []}],
           "sections": [], "characters": [], "motifs": [], "symbolism": []}
    fixed, probs = check_claims(doc, {"L001"}, 60.0)
    th = fixed["themes"]
    assert len(th) == 2 and th[0]["cites"] == [{"id": "L001", "quote": " ".join(["w"] * 10)}]
    assert th[1]["source"] == "speculative"
    assert any("L999" in p for p in probs) and any("14 words" in p for p in probs)
    assert not any("w w w" in p for p in probs)  # problems never quote the text


def test_orphans_when_sections_change(synth_source, synth_source_parts):
    files, events = synth_source_parts
    intent = """```yaml
sections:
  S05: {t0: 34.5, t1: 50.5, occurrence_label: "chorus#2", feel: "release"}
  S07: {t0: 60.0, t1: 70.0, feel: "a section that is gone"}
```"""
    # sections shift: S04 is split in two, so the old S05 (the drop) is now S06
    secs = copy.deepcopy(events["sections"])
    s4 = secs[3]
    a, b = dict(s4, d=4.75), dict(s4, t=s4["t"] + 4.75, d=4.75)
    new = secs[:3] + [a, b] + secs[4:]
    for k, s in enumerate(new, 1):
        s["id"] = f"S{k:02d}"
    res = build(synth_source(events={"sections": new}), intent, None, {})
    assert _sec(res, "S06")["feel"] == "release" and _sec(res, "S06")["field_sources"]["feel"] == "user"
    assert len(res["orphans"]) == 1 and res["orphans"][0]["old_section_id"] == "S07"
    assert res["orphans"][0]["t_range"] == [60.0, 70.0]
    assert schemas.validate({"orphans": res["orphans"]}, "mvh/files/orphans") == []
    assert res["summary"]["orphans"] == 1


def test_bundle_and_privacy(synth_source, synth_source_parts):
    files, _ = synth_source_parts
    res = build(synth_source(), None, None, {})
    assert schemas.validate(res["input"], "mvh/files/meaning_input") == []
    assert res["input"]["lines_file"] == "lyrics/lines.tsv"
    assert "facts" in res["input"] and res["input"]["facts"]["gaps"]
    texts = [ln["text"] for ln in files["lyrics/lyrics.json"]["lines"]]
    blob = json.dumps(res["input"]) + res["request"] + res["meaning_md"] + json.dumps(res["meaning"])
    assert not any(t in blob for t in texts)  # no lyric line in the bundle, the merged meaning or meaning.md
    for t in texts:  # the interview quotes at most 8 words of a hook
        if t in res["interview"]:
            assert len(t.split()) <= 8
    # schema.json is self-contained (no $ref)
    assert "$ref" not in json.dumps(res["schema"]) and res["schema"]["properties"]["status"]
    off = build(synth_source(), None, None, {"lyrics_to_agents": False})
    assert off["input"]["lines_file"] is None and all(r["text"] == "" for r in off["lines_rows"])
    assert "not** available" in off["request"]


def test_interview_template_roundtrip(synth_source):
    res = build(synth_source(), None, None, {})
    iv = res["interview"]
    assert "V1" in iv and "V2" in iv and "Never show" in iv and "```yaml" in iv
    tmpl = iv[iv.index("```yaml"):]
    filled = tmpl.replace('feel: ""', 'feel: "x"', 1).replace('name: ""', 'name: "A"', 2)
    it = parse_intent(filled)
    assert it["form"] == "yaml" and set(it["characters"]) == {"C1", "C2"}
    assert len(it["sections"]) == 1 and it["sections"][0]["key"] == "S01" and it["sections"][0]["t0"] == 1.0
    res2 = build(synth_source(), filled, None, {})
    assert res2["meaning"]["status"] == "user" and _sec(res2, "S01")["feel"] == "x"
