"""W4A-UD1 (W4 fixer words): a hard rule typed under the template key do_not is never lost to a note.

Tabs in the indentation, a stray line after the list and a blank line between ``do_not:`` and its items keep every
rule; whatever does not parse is reported (warnings, intent ``unparsed_keys``, meaning.json ``intent_unparsed``, an
open question and a brief.md line). Synthetic text only.
"""
from __future__ import annotations

from mvh.stages.brief.build import _meaning_block
from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build

RULES = ["show the singer's face", "use red light"]


def test_tab_indented_list_keeps_every_rule():
    r = parse_intent("do_not:\n\t- show the singer's face\n\t- use red light\n")
    assert r["do_not"] == RULES and not r["notes"] and not r["unparsed_keys"]


def test_tab_between_dash_and_text():
    r = parse_intent("do_not:\n  -\tshow the singer's face\n  - use red light\n")
    assert r["do_not"] == RULES


def test_tab_inside_the_text_is_kept():
    r = parse_intent("logline: a\tb\n")
    assert r["logline"] == "a\tb"


def test_stray_sentence_after_the_list_is_a_warned_note_and_the_rules_stay():
    r = parse_intent("do_not:\n  - show the singer's face\n  - use red light\n\n  I'd also love fog, just a wish.\n")
    assert r["do_not"] == RULES
    assert any("fog" in n for n in r["notes"])
    assert r["warnings"] and r["unparsed_keys"] == ["do_not"]


def test_one_bad_rule_keeps_the_others():
    r = parse_intent("do_not:\n  - show the singer's face\n  - [broken\n  - use red light\n")
    assert r["do_not"] == RULES and r["unparsed_keys"] == ["do_not"] and r["notes"]


def test_blank_line_between_key_and_items():
    r = parse_intent("do_not:\n\n- show the singer's face\n- use red light\n")
    assert r["do_not"] == RULES and not r["notes"]
    r = parse_intent("do_not:\n- show the singer's face\n\n- use red light\n")
    assert r["do_not"] == RULES and not r["notes"]


def test_prose_after_a_valued_key_still_ends_the_region():
    r = parse_intent("tone: dark\n\nThis is my prose.\n")
    assert r["tone"] == "dark" and r["notes"] == ["This is my prose."]


def test_other_nested_keys_parse_per_entry():
    r = parse_intent("symbolism:\n  - lanterns are memory\n  - [broken\n")
    assert r["symbolism"] == ["lanterns are memory"] and r["unparsed_keys"] == ["symbolism"]


def test_demotion_reaches_meaning_json_and_the_brief(synth_source):
    res = build(synth_source(), "do_not:\n  - use red light\n  - [broken\n", None, {})
    m = res["meaning"]
    assert m["do_not"] == ["use red light"] or [x.get("text", x) if isinstance(x, dict) else x for x in m["do_not"]]
    assert m["intent_unparsed"] == [{"key": "do_not", "entries": 1}]
    assert any("did not parse" in q and "do_not" in q for q in m["open_questions"])
    text = "\n".join(_meaning_block({"meaning": m}))
    assert "did not parse" in text and "typed under do_not" in text


def test_clean_template_reports_nothing(synth_source, synth_intent):
    m = build(synth_source(), synth_intent, None, {})["meaning"]
    assert m["intent_unparsed"] == []
    assert "did not parse" not in "\n".join(_meaning_block({"meaning": m}))


# ---- round 2 (VWU1-a, VWU1-b)
def test_stray_colon_line_after_rules_is_a_note_not_the_only_rule():
    for stray in ("  Also: lots of fog please", "  chorus: no close-ups"):
        r = parse_intent("do_not:\n  - show the singer's face\n  - use red light\n" + stray + "\n")
        assert r["do_not"] == RULES
        assert r["unparsed_keys"] == ["do_not"] and len(r["warnings"]) == 1
        assert stray in r["notes"]  # verbatim, as typed


def test_stray_colon_line_in_symbolism_and_notes():
    r = parse_intent("symbolism:\n  - lanterns are memory\n  Also: fog\n")
    assert r["symbolism"] == ["lanterns are memory"] and r["unparsed_keys"] == ["symbolism"]
    r = parse_intent("notes:\n  - one\n  Also: two\n")  # a note is text either way: kept, no warning
    assert r["notes"] == ["one", "Also: two"] and not r["warnings"]


def test_map_key_mixing_bullets_and_entries_keeps_both():
    r = parse_intent("characters:\n  - C1 Ann = V1\n  C2: Bob = V2\n")
    assert set(r["characters"]) == {"C1", "C2"}
    r = parse_intent("sections:\n  - Chorus: wide shots\n  verse: close\n")
    assert [s["key"] for s in r["sections"]] == ["chorus", "verse"]


def test_tab_after_dash_at_column_0():
    r = parse_intent("do_not:\n-\tshow the singer's face\n-\tuse red light\n")
    assert r["do_not"] == RULES and not r["warnings"] and not r["notes"]


def test_stray_colon_line_reaches_meaning_json_and_the_brief(synth_source):
    res = build(synth_source(), "do_not:\n  - show the singer's face\n  - use red light\n  Also: lots of fog please\n",
                None, {})
    m = res["meaning"]
    rules = [x.get("text", x) if isinstance(x, dict) else x for x in m["do_not"]]
    assert all(r in rules for r in RULES) and not any("fog" in str(r) for r in rules)
    assert m["intent_unparsed"] == [{"key": "do_not", "entries": 1}]
    assert any("do_not" in q for q in m["open_questions"])
    assert "typed under do_not" in "\n".join(_meaning_block({"meaning": m}))
