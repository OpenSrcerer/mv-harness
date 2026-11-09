"""intent.md parsing (UD1, grammar mvh-intent v2): the template is the only source of fields and do-not rules, free text
is kept verbatim as the user's notes, the viewer block wins. Synthetic text only (the fixture's lyrics are invented)."""
from __future__ import annotations

import pytest

from mvh.stages.meaning.colors import parse_color, parse_palette
from mvh.stages.meaning.intent import parse_intent, split_singers


def test_synth_fixture_template_and_notes(synth_intent):
    it = parse_intent(synth_intent)
    assert it["present"] and it["form"] == "yaml+text"
    assert it["characters"]["C1"]["voices"] == ["V1"] and it["characters"]["C2"]["voices"] == ["V2"]
    assert it["characters"]["C1"]["name"] == "The Lamplighter"
    assert it["characters"]["C1"]["lead_backing"] == "lead"
    assert it["n_characters"] == 2
    # do-not rules verbatim (the user's words, from the template)
    assert it["do_not"] == ["Never show fire burning a person or a boat.", "No text on screen except the lyrics."]
    assert len(it["palette"]) == 5 and all(h.startswith("#") and len(h) == 7 for h in it["palette"])
    assert it["palette_names"][0] == "night blue" and not it["palette_unparsed"]
    assert [s["key"] for s in it["sections"]] == ["intro", "verse", "build", "drop"]
    assert it["sections"][0]["feel"] == "slow drift over dark water"
    assert it["logline"].startswith("Two figures keep a harbour town lit")
    # the prose around the template: two notes, verbatim, the story heading kept, the template's label heading not
    assert len(it["notes"]) == 2 and it["notes"][0].startswith("## The story\nTwo figures keep")
    assert it["notes"][1].startswith("The 3/4 bar") and it["free_notes"] == it["notes"]
    assert not any("My answers" in n for n in it["notes"])
    assert it["summary"] is None  # free text never fills a field


def test_yaml_template_and_reanchor_fields():
    text = """# my answers
Some free text: it is a note, never a field.

```yaml
logline: "A night watch"
characters:
  C1: {name: Newton, voices: [V1], lead_backing: lead}
  C2: {name: "Nye", description: "bow tie", voices: [V2, V3]}
line_singers: {L005: C1+C2, L007: C2}
palette: ["#112233", deep teal]
do_not:
  - "No real logos"
sections:
  S03:
    t0: 17.0
    t1: 25.0
    occurrence_label: chorus#1
    feel: "the voices meet"
    palette: ["#ff0000"]
    characters: [C1, C2]
  S04: {feel: ""}
```
"""
    it = parse_intent(text)
    assert it["form"] == "yaml+text"
    assert it["logline"] == "A night watch"
    assert it["notes"] == ["# my answers\nSome free text: it is a note, never a field."]
    assert it["characters"]["C2"]["voices"] == ["V2", "V3"] and it["characters"]["C2"]["description"] == "bow tie"
    assert it["line_singers"] == {"L005": ["C1", "C2"], "L007": ["C2"]}
    assert it["palette"][0] == "#112233" and len(it["palette"]) == 2
    assert it["do_not"] == ["No real logos"]
    s = [c for c in it["sections"] if c["key"] == "S03"]
    assert len(s) == 1 and s[0]["t0"] == 17.0 and s[0]["t1"] == 25.0 and s[0]["palette"] == ["#ff0000"]
    assert not [c for c in it["sections"] if c["key"] == "S04"]  # an empty answer is no claim


def test_whole_file_yaml_and_bad_yaml():
    it = parse_intent("logline: just yaml\ncharacters:\n  C1: {name: A, voices: [V1]}\n")
    assert it["form"] == "yaml" and it["logline"] == "just yaml" and it["n_characters"] == 1
    bad = parse_intent("```yaml\nlogline: [unclosed\n```\n## Never show\n- blood\n")
    assert any("does not parse" in w for w in bad["warnings"])
    # the broken entry and the free text are both kept as notes; neither is a rule
    assert bad["do_not"] == [] and bad["logline"] is None
    assert "logline: [unclosed" in bad["notes"] and "## Never show\n- blood" in bad["notes"]


def test_line_singers_template_free_text_and_bom():
    it = parse_intent("﻿line_singers:\n  L001: C1\n  L002: C2 + C1\n")
    assert it["line_singers"] == {"L001": ["C1"], "L002": ["C2", "C1"]}
    free = parse_intent("## Singers\nL001: C1\nL002 = C2 + C1\n")
    assert free["line_singers"] == {} and free["notes"] == ["## Singers\nL001: C1\nL002 = C2 + C1"]
    assert split_singers("C3 & C1, C3") == ["C3", "C1"]


def test_plain_text_only_is_one_note():
    it = parse_intent("It is about losing a friend. Everything should feel grey.")
    assert it["logline"] is None and it["summary"] is None and it["form"] == "text"
    assert it["notes"] == ["It is about losing a friend. Everything should feel grey."]


def test_empty_and_missing():
    assert parse_intent(None)["present"] is False
    assert parse_intent("  \n")["present"] is False


def test_colours():
    assert parse_color("#ABC") == "#aabbcc"
    dark = parse_color("night blue")
    base = parse_color("blue")
    assert dark != base and int(dark[1:3], 16) <= int(base[1:3], 16)
    hexes, names, bad = parse_palette(["rust red", "glorbish", "#000000"])
    assert len(hexes) == 2 and bad == ["glorbish"] and names[1] == "#000000"


VIEWER_BLOCK = """# What this song means to me (meaning/intent.md)
## Characters
- C1 The Lamplighter = voice V2

<!-- mvh-viewer:begin v1 -->
## Viewer corrections
_Written by `mvh view`._

### Voices
- V1 = C1 The Lamplighter
- V2 = C2 The Tide

### S02 verse#1 9.000-17.000 s
- feel: call / response
- palette: #1b2a49, #f2a541
- do not: no boats
<!-- mvh-viewer:end -->
"""


def test_viewer_block_wins():
    it = parse_intent(VIEWER_BLOCK)
    assert it["characters"]["C1"]["voices"] == ["V1"] and it["characters"]["C2"]["voices"] == ["V2"]
    assert it["characters"]["C2"]["name"] == "The Tide" and it["form"].endswith("viewer")
    s = it["sections"][0]
    assert s["key"] == "S02" and (s["t0"], s["t1"]) == (9.0, 17.0) and s["origin"] == "viewer"
    assert s["feel"] == "call / response" and s["palette"] == ["#1b2a49", "#f2a541"] and s["do_not"] == ["no boats"]
    assert not any(k.startswith("viewer") for k in (c["key"] for c in it["sections"]))
    # the free-text character line is a note (the viewer's default title is the harness's, not a note)
    assert it["notes"] == ["## Characters\n- C1 The Lamplighter = voice V2"]


def test_viewer_block_grammar_matches_m6a():
    """Round trip through the viewer's own writer (M6a), when it is installed."""
    ib = pytest.importorskip("mvh.stages.viewer.intent_block")
    state = ib.merge(ib.empty(), {"voices": {"V3": {"character_id": "C3", "name": "Announcer"}},
                                  "sections": {"S04": {"t0": 25.0, "t1": 34.5, "label": "bridge#1", "feel": "tense",
                                                       "camera": "push in", "do_not": ["no smoke"]}}})
    it = parse_intent(ib.apply("free text\n", state))
    assert it["characters"]["C3"] == {"name": "Announcer", "description": None, "voices": ["V3"], "lead_backing": None}
    s = it["sections"][0]
    assert (s["key"], s["t0"], s["t1"], s["feel"], s["camera"], s["do_not"]) == ("S04", 25.0, 34.5, "tense", "push in", ["no smoke"])
    assert it["notes"] == ["free text"]
    fresh = parse_intent(ib.apply("", state))  # the viewer created the file: its default title is not a note
    assert fresh["notes"] == [] and fresh["characters"]["C3"]["name"] == "Announcer"
