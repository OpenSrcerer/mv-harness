"""D81: answers given once for a group of sections (``every section``, ``every <label>``), the ``# suggestion`` marker,
and ``mvh meaning --suggest`` (edit.add_suggestions). Synthetic text only.

The synthetic song has S01 intro, S02 verse, S03 chorus, S04 bridge, S05 chorus, S06 outro."""
from __future__ import annotations

import copy

import pytest

from mvh.stages.meaning import edit as E
from mvh.stages.meaning.anchor import anchor_claim, group_key
from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build

GROUPED = """```yaml
logline: "A night watch"
sections:
  every section:
    feel: "base"
    camera: "wide"
  every chorus:
    feel: "lift"
    palette: [#112233]
  S05:
    t0: 34.5
    t1: 50.5
    feel: "biggest"
```
"""


def _sec(res, sid):
    return next(s for s in res["meaning"]["sections"] if s["section_id"] == sid)


def _group(res, key):
    return next(g for g in res["meaning"]["section_defaults"] if g["key"] == key)


def _template(res) -> str:
    iv = res["interview"]
    a = iv.index("```yaml")
    return iv[a:iv.index("```", a + 7) + 3] + "\n"


def _draft(synth_authored, **feel_by_section):
    """The synthetic draft with the given feel on the named sections (S03='x')."""
    d = copy.deepcopy(synth_authored)
    for s in d["sections"]:
        if s["section_id"] in feel_by_section:
            s["feel"] = feel_by_section[s["section_id"]]
    return d


# ------------------------------------------------------------------------------------------------ anchoring
def test_group_keys(synth_source_parts):
    secs = synth_source_parts[1]["sections"]
    assert group_key("every section") == group_key("All") == group_key("default") == "all"
    assert group_key("every chorus") == group_key("Each  Choruses") == group_key("all chorus") == "chorus"
    assert group_key("chorus") is None and group_key("S03") is None and group_key("last chorus") is None
    a = anchor_claim({"key": "every section"}, secs)
    assert a["how"] == "all" and a["specificity"] == 0 and len(a["section_ids"]) == len(secs)
    a = anchor_claim({"key": "Every Choruses"}, secs)
    assert a["how"] == "every" and a["section_ids"] == ["S03", "S05"] and a["group"] == "chorus"
    a = anchor_claim({"key": "every drop"}, secs)
    assert not a["section_ids"] and "drop" in a["orphan_reason"]


def test_an_answer_is_inherited_downwards(synth_source):
    res = build(synth_source(), GROUPED, None, {})
    assert res["meaning"]["status"] == "user"
    s1, s3, s5 = _sec(res, "S01"), _sec(res, "S03"), _sec(res, "S05")
    assert (s1["feel"], s1["camera_hint"]) == ("base", "wide")                 # every section
    assert (s3["feel"], s3["camera_hint"], s3["palette_hint"]) == ("lift", "wide", ["#112233"])   # its group, then all
    assert s5["feel"] == "biggest" and s5["palette_hint"] == ["#112233"]       # the single section wins
    assert s1["field_scope"] == {"camera_hint": "all", "feel": "all"}
    assert s3["field_scope"] == {"camera_hint": "all", "feel": "type", "palette_hint": "type"}
    assert s5["field_scope"]["feel"] == "section"
    assert all(v == "user" for v in s3["field_sources"].values() if v != "audio")
    g = _group(res, "all")
    assert g["feel"] == "base" and g["camera_hint"] == "wide" and g["field_sources"] == {"camera_hint": "user", "feel": "user"}
    g = _group(res, "chorus")
    assert g["section_ids"] == ["S03", "S05"] and g["feel"] == "lift" and g["palette_hint"] == ["#112233"]
    # nothing the user answered for a group is a gap for the drafting agent
    assert not any(gap.startswith("sections.S01") and "feel" in gap.split(": ")[1].split(", ")
                   for gap in res["input"]["facts"]["gaps"])


def test_template_writes_group_answers_at_the_group(synth_source):
    res = build(synth_source(), GROUPED, None, {})
    t = _template(res)
    assert "  every section:   # the default for the whole song\n    feel: \"base\"" in t
    assert "  every chorus:   # group of 2: S03 S05\n    feel: \"lift\"" in t
    assert "every verse" not in t                                    # a label with one section is that section
    s3 = t[t.index("  S03:"):t.index("  S04:")]
    assert 'feel: ""' in s3 and "palette: []" in s3                  # inherited: not frozen into the section
    assert 'feel: "biggest"' in t[t.index("  S05:"):t.index("  S06:")]
    again = build(synth_source(), t, None, {})
    assert not again["intent"]["warnings"]
    assert [(s["section_id"], s["feel"], s["camera_hint"], s["palette_hint"], s["field_scope"]) for s in again["meaning"]["sections"]] \
        == [(s["section_id"], s["feel"], s["camera_hint"], s["palette_hint"], s["field_scope"]) for s in res["meaning"]["sections"]]
    assert _template(again) == t                                     # a fixed point


def test_a_one_section_group_the_user_wrote_keeps_its_entry(synth_source):
    res = build(synth_source(), "```yaml\nsections:\n  every outro:\n    feel: \"fade\"\n```\n", None, {})
    assert _sec(res, "S06")["feel"] == "fade"
    t = _template(res)
    assert "  every outro:   # group of 1: S06" in t
    assert _sec(build(synth_source(), t, None, {}), "S06")["field_scope"] == {"feel": "type"}


# ------------------------------------------------------------------------------------------------ the marker
def test_a_marked_line_is_not_an_answer():
    text = ('```yaml\nlogline: "A night watch"   # suggestion\ntone: dark # suggestion from Ann\n'
            'do_not:\n  - "no faces"   # suggestion\n  - no fire\n'
            'sections:\n  S03:\n    t0: 17.0\n    t1: 25.0\n    feel: "lift"   # Suggestion\n    camera: "wide"\n```\n')
    it = parse_intent(text)
    assert it["logline"] is None and it["do_not"] == ["no fire"]
    assert it["tone"] == "dark # suggestion from Ann"                # one space: text, not the marker
    assert [(c["key"], c["feel"], c["camera"]) for c in it["sections"]] == [("S03", None, "wide")]
    assert it["suggested"] == ["logline", "do_not[]", "sections.S03.feel"]
    accepted = parse_intent(text.replace("   # suggestion", "").replace("   # Suggestion", ""))
    assert accepted["logline"] == "A night watch" and accepted["do_not"] == ["no faces", "no fire"]
    assert accepted["sections"][0]["feel"] == "lift" and accepted["suggested"] == []


def test_only_marked_lines_means_no_answer(synth_source):
    res = build(synth_source(), '```yaml\nlogline: "x"   # suggestion\n```\n', None, {})
    assert res["meaning"]["status"] == "pending" and res["meaning"]["intent_suggested"] == ["logline"]


# ------------------------------------------------------------------------------------------------ suggestions
def test_draft_shared_by_a_group_is_one_suggestion(synth_source, synth_authored):
    res = build(synth_source(), None, _draft(synth_authored, S03="rising light", S05="rising light"), {})
    g = _group(res, "chorus")
    assert g["feel"] == "rising light" and g["field_sources"]["feel"] == "draft"
    sug = E.suggestions_of(res["meaning"])
    assert ("chorus", "feel", "rising light", ["S03", "S05"]) in sug["groups"]
    assert sug["sections"][("S03", "feel")] == "rising light" and sug["song"].get("logline")


def test_new_file_gets_marked_suggestions_and_they_answer_nothing(synth_source, synth_authored):
    draft = _draft(synth_authored, S03="rising light", S05="rising light")
    draft["do_not"] = ["no rain"]
    res = build(synth_source(), None, draft, {})
    assert res["meaning"]["suggested_do_not"] == ["no rain"] and res["meaning"]["do_not"] == []
    text, n = E.add_suggestions(E.starter_text(res["interview"]), res["meaning"])
    assert n > 3 and sum(ln.endswith("   # suggestion") for ln in text.splitlines()) == n
    assert '  every chorus:   # group of 2: S03 S05\n    feel: "rising light"   # suggestion' in text
    for sid, nxt in (("S03", "S04"), ("S05", "S06")):                        # not repeated on each chorus
        assert 'feel: ""' in text[text.index(f"  {sid}:"):text.index(f"  {nxt}:")]
    assert 'do_not:   # rules in your own words; copied verbatim to every agent\n  - "no rain"   # suggestion' in text
    assert f'logline: "{res["meaning"]["logline"]}"   # suggestion' in text
    it = parse_intent(text)
    assert len(it["suggested"]) == n and not it["do_not"] and not it["sections"] and it["logline"] is None
    again = build(synth_source(), text, draft, {})
    assert again["meaning"]["status"] == "draft"                             # nothing became the user's
    assert E.add_suggestions(text, again["meaning"]) == (text, n)            # refreshing changes nothing


def test_accepting_a_suggestion_makes_it_the_users(synth_source, synth_authored):
    draft = _draft(synth_authored, S03="rising light", S05="rising light")
    res = build(synth_source(), None, draft, {})
    text, _n = E.add_suggestions(E.starter_text(res["interview"]), res["meaning"])
    text = text.replace('feel: "rising light"   # suggestion', 'feel: "rising light"')
    again = build(synth_source(), text, draft, {})
    assert again["meaning"]["status"] == "user"
    assert _sec(again, "S03")["field_sources"]["feel"] == "user" and _sec(again, "S03")["field_scope"]["feel"] == "type"
    assert _sec(again, "S02")["field_sources"].get("feel") == "draft"        # the rest is still the draft's


def test_suggest_never_touches_what_the_user_wrote(synth_source, synth_authored):
    draft = _draft(synth_authored, S03="rising light", S05="rising light")
    res = build(synth_source(), None, draft, {})
    mine = E.starter_text(res["interview"]).replace('logline: ""', 'logline: "Mine"', 1)
    mine = "My heading\n\n" + mine + "The town is flooded.   # suggestion\n"
    user = build(synth_source(), mine, draft, {})
    text, n = E.add_suggestions(mine, user["meaning"])
    assert 'logline: "Mine"\n' in text and text.startswith("My heading\n\n") and text.endswith("The town is flooded.   # suggestion\n")
    changed = [ln for ln in mine.splitlines() if ln not in text.splitlines()]
    assert changed and all(ln.split("   #")[0].split(":", 1)[1].strip() in ('""', "[]") for ln in changed)  # only empty fields
    assert n == sum(ln.endswith("   # suggestion") for ln in text.splitlines()) - 1   # the free-text line is not counted
    # a draft that no longer suggests anything: the marked lines are emptied again, the rest stays
    bare, n0 = E.add_suggestions(text, build(synth_source(), mine, None, {})["meaning"])
    assert n0 == 0 and bare == mine.replace("palette: []   # hex (#1b2a49) or colour words (night blue)", "palette: []")


def test_crlf_files_keep_their_line_endings(synth_source, synth_authored):
    res = build(synth_source(), None, synth_authored, {})
    crlf = E.starter_text(res["interview"]).replace("\n", "\r\n")
    text, n = E.add_suggestions(crlf, res["meaning"])
    assert n > 0 and "\r\n" in text and "\n" not in text.replace("\r\n", "")


def test_text_without_a_template_is_left_alone(synth_source, synth_authored):
    res = build(synth_source(), None, synth_authored, {})
    assert E.add_suggestions("Just my notes.\n", res["meaning"]) == ("Just my notes.\n", 0)


def test_suggest_into_creates_then_fills(tmp_path, synth_source, synth_authored):
    import json

    res = build(synth_source(), None, synth_authored, {})
    (tmp_path / "meaning").mkdir()
    (tmp_path / "meaning" / "interview.md").write_text(res["interview"], encoding="utf-8")
    (tmp_path / "meaning" / "meaning.json").write_text(json.dumps(res["meaning"]), encoding="utf-8")
    p, created, n = E.suggest_into(tmp_path)
    assert created and n > 0 and p.read_text(encoding="utf-8").count("   # suggestion") >= n
    before = p.read_bytes()
    assert E.suggest_into(tmp_path) == (p, False, n) and p.read_bytes() == before


# ------------------------------------------------------------------------------------------------ viewer block
BLOCK = """```yaml
logline: "From the template"
tone: "grey"
do_not:
  - no fire
```

<!-- mvh-viewer:begin v1 -->
## Viewer corrections
_Written by `mvh view`._

### Song
- logline: From the viewer
- theme: keeping watch
- theme: the sea
- palette: #0e2346, rust red
- do not: no faces

### Every section
- camera: wide

### Every chorus
- feel: lift
<!-- mvh-viewer:end -->
"""


def test_viewer_block_song_and_groups(synth_source):
    it = parse_intent(BLOCK)
    assert it["logline"] == "From the viewer" and it["tone"] == "grey"         # the block wins; the rest stays
    assert it["themes"] == ["keeping watch", "the sea"]
    assert it["palette"][0] == "#0e2346" and len(it["palette"]) == 2
    assert it["do_not"] == ["no fire", "no faces"]                             # rules: a union
    assert [(c["key"], c["feel"], c["camera"], c["origin"]) for c in it["sections"]] == \
        [("every section", None, "wide", "viewer"), ("every chorus", "lift", None, "viewer")]
    res = build(synth_source(), BLOCK, None, {})
    assert _sec(res, "S03")["feel"] == "lift" and _sec(res, "S01")["camera_hint"] == "wide"
    assert res["meaning"]["field_sources"]["logline"] == "user" and "viewer" in res["meaning"]["intent_form"]


@pytest.mark.parametrize("key", ["every section", "every chorus"])
def test_a_section_answer_in_the_template_beats_a_group_in_the_viewer(synth_source, key):
    text = ('```yaml\nsections:\n  S03:\n    t0: 17.0\n    t1: 25.0\n    feel: "mine"\n```\n\n'
            f"<!-- mvh-viewer:begin v1 -->\n### {key.capitalize()}\n- feel: group\n<!-- mvh-viewer:end -->\n")
    res = build(synth_source(), text, None, {})
    assert _sec(res, "S03")["feel"] == "mine" and _sec(res, "S05")["feel"] == "group"
