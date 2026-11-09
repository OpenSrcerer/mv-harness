"""The intent grammar (meaning/intent.py, mvh-intent v2, UD1): checks over the interview template's variants, the exact
round trip of user claims through the template, and the rule that free text is the user's notes (never fields or
rules). Synthetic fixture only (invented lyrics)."""
from __future__ import annotations

import itertools
import re
from typing import Any

import pytest

from mvh.stages.meaning.intent import parse_intent, tolerant_yaml_line
from mvh.stages.meaning.stage import build


# ------------------------------------------------------------------------------------------------ helpers
def _template(res: dict[str, Any]) -> str:
    iv = res["interview"]
    a = iv.index("```yaml")
    b = iv.index("```", a + 7)
    return iv[a:b + 3] + "\n"


def _user_claims(res: dict[str, Any]) -> dict[str, Any]:
    """Every user claim of a build, in a comparable form (draft and harness facts left out)."""
    m = res["meaning"]
    fs = m["field_sources"]
    g = {k: m[k] for k in ("logline", "summary", "setting", "tone", "palette", "references", "notes") if fs.get(k) == "user"}
    for k in ("themes", "symbolism"):
        if fs.get(k) == "user":
            g[k] = [c["text"] for c in m[k]]
    if fs.get("motifs") == "user":
        g["motifs"] = [(x["name"], [o["line_id"] for o in x["occurrences"]], x.get("note")) for x in m["motifs"]]
    g["perspective"] = {k: m["perspective"][k] for k in ("narrator", "addressee") if fs.get(f"perspective.{k}") == "user"}
    g["do_not"] = list(m["do_not"])
    g["characters"] = {c["id"]: ({k: c[k] for k, v in c["field_sources"].items() if v == "user"},
                                 sorted(v for v, how in c["voice_mapping"].items() if how == "user"))
                       for c in m["characters"] if c["provenance"]["status"] == "user"}
    g["line_singers"] = sorted((it["line_id"], it["character_id"]) for it in res["singing"] if it.get("source") == "user")
    secs = {}
    for s in m["sections"]:
        u = {k: (s["emotion"]["lyric"] if k == "emotion.lyric" else s[k]) for k, v in s["field_sources"].items() if v == "user"}
        own_dn = [r for r in s["do_not"] if r not in m["do_not"]]
        if u or own_dn:
            secs[s["section_id"]] = (u, own_dn)
    g["sections"] = secs
    g["status"] = m["status"]
    return g


def _full_yaml(ev_sections: list[dict[str, Any]]) -> str:
    s5 = next(s for s in ev_sections if s["id"] == "S05")
    return f"""# Our video

```yaml
logline: "Two keepers light a harbour."
summary: "Two keepers light a harbour.\\nThey lose each other at dawn: then the town wakes."
themes: [loss, light]
setting: "A harbour town, one night"
tone: "slow, warm #1 then cold"
perspective: {{narrator: C1, addressee: C2}}
characters:
  C1: {{name: "The Lamplighter", description: "old, patient", voices: [V1], lead_backing: lead}}
  C2: {{name: "The Tide", voices: [V2]}}
line_singers:
  L005: C1+C2
palette: [#0e2346, lantern amber, rust red]
do_not:
  - "No fire on people."
  - Chorus: never show faces
motifs:
  - {{name: lanterns, lines: [L001, L003], note: "memory"}}
symbolism: ["Lanterns are memory, and memory fades."]
references: ["Tarkovsky, Stalker"]
notes: ["Keep every cut on a count."]
sections:
  S05:
    t0: {s5['t']}
    t1: {s5['t'] + s5['d']}
    feel: "everything at once"
    meaning: "the reunion"
    emotion: joy
    movement: "spin outward"
    camera: "crane up"
    palette: [#f2a541]
    characters: [C1, C2]
    do_not: ["No close-ups of faces here."]
```

Intro: slow drift over dark water.
"""


@pytest.fixture
def src(synth_source):
    return synth_source()


@pytest.fixture
def ev_sections(synth_source_parts):
    return synth_source_parts[1]["sections"]


# ------------------------------------------------------------------------------------------------ round trip
def _intents(ev_sections, synth_intent) -> dict[str, str]:
    return {"synth_fixture": synth_intent, "full_yaml": _full_yaml(ev_sections),
            "free_text_only": "Logline: A night watch.\nTone: grey\nNever show: blood\n\n- C1 Ann = V1. Lead.\n"
                              "- Chorus: wide shots\n\n## Notes\nThe end should be quiet.\n"}


@pytest.mark.parametrize("name", ["synth_fixture", "full_yaml", "free_text_only"])
def test_template_round_trip_is_exact(src, synth_source, ev_sections, synth_intent, name):
    text = _intents(ev_sections, synth_intent)[name]
    first = build(src, text, None, {})
    claims = _user_claims(first)
    assert claims["status"] == "user"
    t1 = _template(first)
    again = build(synth_source(), t1, None, {})
    assert again["intent"]["form"] == "yaml" and not again["intent"]["warnings"], again["intent"]["warnings"]
    assert _user_claims(again) == claims
    assert _template(again) == t1  # a fixed point: the template of the template is the template


def test_full_yaml_reads_every_field(src, ev_sections):
    r = build(src, _full_yaml(ev_sections), None, {})
    c = _user_claims(r)
    assert c["logline"] == "Two keepers light a harbour." and "\n" in c["summary"]
    assert c["tone"] == "slow, warm #1 then cold"
    assert c["palette"][0] == "#0e2346" and len(c["palette"]) == 3
    assert c["do_not"] == ["No fire on people.", "Chorus: never show faces"]
    assert c["perspective"] == {"narrator": "C1", "addressee": "C2"}
    assert c["motifs"] == [("lanterns", ["L001", "L003"], "memory")]
    assert c["references"] == ["Tarkovsky, Stalker"]
    # the template's notes, then the free text: the H1 above the template labels it, the line after it is a note
    assert c["notes"] == ["Keep every cut on a count.", "Intro: slow drift over dark water."]
    s5 = c["sections"]["S05"][0]
    assert s5["palette_hint"] == ["#f2a541"] and s5["camera_hint"] == "crane up" and s5["emotion.lyric"] == "joy"
    assert c["sections"]["S05"][1] == ["No close-ups of faces here."]
    assert ("L005", "C1") in c["line_singers"] and ("L005", "C2") in c["line_singers"]
    assert set(c["sections"]) == {"S05"}  # the free-text 'Intro:' line is not a section feel


# ------------------------------------------------------------------------------------------------ template variants
def _filled(src) -> str:
    t = _template(build(src, None, None, {}))
    t = t.replace('logline: ""', 'logline: "Two keepers light a harbour."', 1)
    t = t.replace('C1: {name: ""', 'C1: {name: "Keeper"', 1)
    t = t.replace("do_not:   # rules in your own words; copied verbatim to every agent",
                  "do_not:   # rules in your own words; copied verbatim to every agent\n  - never show faces", 1)
    t = re.sub(r'(  S05:.*\n(?:    .*\n){3})    feel: ""', r'\1    feel: "slow burn"', t)
    assert "Keeper" in t and "never show faces" in t and "slow burn" in t
    return t


PALETTES = {
    "flow_hex": "palette: [#c93523, night blue]",
    "flow_quoted": 'palette: ["#c93523", "night blue"]',
    "block_hex": "palette:\n  - #c93523\n  - night blue",
    "block_col0": "palette:\n- #c93523\n- night blue",
    "plain_hex": "palette: #c93523, night blue",
}
WRAPS = {
    "fenced": lambda t: t,
    "unfenced": lambda t: "\n".join(ln for ln in t.splitlines() if not ln.startswith("```")) + "\n",
    "open_fence_only": lambda t: t[:t.rindex("```")],
    "no_marker": lambda t: "\n".join(ln for ln in t.splitlines() if not ln.startswith("```") and "mvh-intent" not in ln) + "\n",
}
AROUND = {  # free text around the template: always notes
    "alone": (lambda t: t, []),
    "story_before": (lambda t: "## The story\nA keeper waits for the light.\n\n" + t,
                     ["## The story\nA keeper waits for the light."]),
    "prose_after": (lambda t: t + "\nThe end should be quiet.\n", ["The end should be quiet."]),
    "note_after": (lambda t: t + "\n## Notes\nChorus: everything glows.\n", ["## Notes\nChorus: everything glows."]),
    "never_after": (lambda t: t + "\n## Never show\n- No confetti.\n", ["## Never show\n- No confetti."]),
}


@pytest.mark.parametrize("pal,wrap,around", list(itertools.product(sorted(PALETTES), sorted(WRAPS), sorted(AROUND))))
def test_template_variants_keep_every_answer_and_no_comment(src, synth_source, pal, wrap, around):
    t = _filled(src)
    assert "palette: []   # hex (#1b2a49)" in t and "{L005: C1+C2}" in t  # the template's example comments
    t = t.replace("palette: []", PALETTES[pal], 1)
    add, notes = AROUND[around]
    text = add(WRAPS[wrap](t))
    r = build(synth_source(), text, None, {})
    m, it = r["meaning"], r["intent"]
    c1 = next(c for c in m["characters"] if c["id"] == "C1")
    s05 = next(s for s in m["sections"] if s["section_id"] == "S05")
    assert m["status"] == "user" and "yaml" in it["form"], (it["form"], it["warnings"])
    assert m["logline"] == "Two keepers light a harbour." and m["field_sources"]["logline"] == "user"
    assert m["do_not"] == ["never show faces"] and c1["name"] == "Keeper" and s05["feel"] == "slow burn"
    assert "#c93523" in m["palette"] and len(m["palette"]) == 2 and not it["palette_unparsed"]
    # the free text around the template is kept verbatim as notes, and only that
    assert it["notes"] == notes and m["notes"] == notes
    # the template's own example comments never become claims
    assert "#1b2a49" not in m["palette"] and "L005" not in it["line_singers"]
    assert not any(str(c["name"]).startswith("{") for c in m["characters"])
    assert not any(str(s.get("feel") or "").startswith("#") for s in m["sections"])
    assert not any("{" in x or "# hex" in x or "mvh-intent" in x for x in it["notes"] + it["do_not"])
    assert not it["warnings"], it["warnings"]


VOICE_STYLES = {
    "characters_voices": lambda t: t.replace('C1: {name: "Keeper", description: "", voices: []',
                                             'C1: {name: "Keeper", description: "", voices: [V2]', 1),
    "voices_map": lambda t: re.sub(r"(?m)^voices:.*$", "voices:\n  V2: C1 Keeper", t, count=1),
    "voices_bullets": lambda t: re.sub(r"(?m)^voices:.*$", "voices:\n  - V2 = C1 Keeper", t, count=1),
    "voices_bullets_col0": lambda t: re.sub(r"(?m)^voices:.*$", "voices:\n- V2 = C1 Keeper", t, count=1),
    "voices_arrow": lambda t: re.sub(r"(?m)^voices:.*$", "voices:\n  - V2 -> C1", t, count=1),
}


@pytest.mark.parametrize("style,wrap", list(itertools.product(sorted(VOICE_STYLES), ["fenced", "unfenced"])))
def test_voice_mapping_variants(src, synth_source, style, wrap):
    """'V1 = C1 Name' (the viewer block's own syntax) is a template answer under ``voices:``; it maps exactly like the
    characters' voice lists, in the meaning stage and in the voices stage (one parser)."""
    from mvh.stages.voices.intent import parse_intent as voices_parse

    t = _filled(src)
    assert re.search(r"(?m)^voices:   # which character sings each voice", t)
    text = WRAPS[wrap](VOICE_STYLES[style](t))
    r = build(synth_source(), text, None, {})
    c1 = next(c for c in r["characters"] if c["id"] == "C1")
    assert c1["voice_ids"] == ["V2"] and c1["voice_mapping"] == {"V2": "user"} and c1["name"] == "Keeper"
    assert voices_parse(text)["voice_to_character"] == {"V2": "C1"}
    assert not r["intent"]["warnings"] and not r["intent"]["notes"], (r["intent"]["warnings"], r["intent"]["notes"])


def test_voices_count_and_mapping_conflict():
    o = parse_intent("voices: 3\n")
    assert o["n_voices"] == 3 and not o["characters"]
    o = parse_intent("characters:\n  C1: {name: Ann, voices: [V1]}\nvoices:\n  V1: C2 Bo\n")
    assert o["characters"]["C1"]["voices"] == [] and o["characters"]["C2"] == {
        "name": "Bo", "description": None, "voices": ["V1"], "lead_backing": None}
    assert any("'voices' wins" in w for w in o["warnings"])


@pytest.mark.parametrize("wrap", sorted(WRAPS))
@pytest.mark.parametrize("shape", ["synth", "no_voices", "instrumental"])
def test_untouched_template_is_no_answer(synth_source, wrap, shape):
    over = {"no_voices": {"files": {"meta/voices.json": None}, "events": {"voice_spans": []}},
            "instrumental": {"files": {"meta/voices.json": None, "lyrics/lyrics.json": None}, "events": {"voice_spans": []}}}
    first = build(synth_source(**over.get(shape, {})), None, None, {})
    assert first["meaning"]["status"] == "pending"
    r = build(synth_source(**over.get(shape, {})), WRAPS[wrap](_template(first)), None, {})
    it = r["intent"]
    assert r["meaning"]["status"] == "pending" and not it["characters"] and not it["sections"] and not it["notes"], it
    assert not it["warnings"] and it["n_voices"] is None


# ------------------------------------------------------------------------------------------------ free text = notes
FREE_TEXT_CASES = [  # every one of these used to be parsed into rules or fields by the heuristic grammar (v3)
    "## Never show\n- No fire.\n- Chorus: no faces.\n",
    "## Don'ts\n- No fire.\n",
    "## Don’ts\n- No fire.\n",
    "## Things to avoid\n- Lens flares\n",
    "**Never show**\n- Chorus: never show faces.\n",
    "**Never show**\n\n- blood\n- fire\n\n- Intro: slow\n",
    "Never show: blood\n\n- C1 The Keeper = V1\n",
    "Avoid: cliches.\n\n- Intro: slow drift.\n- Drop: wide.\n",
    "**Avoid:** lens flares\n- Chorus: wide\n",
    "**Story:**\nTwo keepers wait for a ship that never returns.\n",
    "# Never Let Me Go\n\nA keeper waits. The tide takes it.\n\nC1 The Keeper = V1\n",
    "## The story: a night that never ends\nTwo keepers. They part.\n\n## Never show\n- No fire.\n",
    "Logline: A night watch.\nNarrator: C1\nAddressee: C2\nThemes: loss, light\nNotes: keep it slow\n",
    "Palette: night blue, #f2a541, rust red\nIntro: slow drift. Verse: call and response\n",
    "## Who sings\n- V1 = C1 The Keeper\n- V2 = C2 The Child\nL005: C1+C2\n",
    "9. **Never show**: blood\n- **Don't**: confetti\n1) Do not: smoke\n",
]


@pytest.mark.parametrize("text", FREE_TEXT_CASES)
def test_free_text_is_notes_never_fields_or_rules(text):
    r = parse_intent(text)
    assert r["form"] == "text"
    assert r["do_not"] == [] and r["sections"] == [] and r["characters"] == {} and r["line_singers"] == {}
    assert not any(r[k] for k in ("logline", "summary", "setting", "tone", "themes", "symbolism", "palette", "motifs",
                                  "references"))
    assert r["perspective"] == {"narrator": None, "addressee": None}
    joined = "\n".join(r["notes"])
    for ln in text.splitlines():  # never silently dropped: every line of the user's text is in a note, verbatim
        assert ln.rstrip() in joined, ln
    assert not r["warnings"]


def test_notes_are_blocks_under_headings():
    r = parse_intent("Opening thought.\n\n# Title\n\n## The story\nA keeper waits.\n\nSecond paragraph.\n\n"
                     "## Look\n- lots of fog\nSlow pans only.\n\n\n\n## Empty\n")
    assert r["notes"] == ["Opening thought.", "# Title\n## The story\nA keeper waits.\n\nSecond paragraph.",
                          "## Look\n- lots of fog\nSlow pans only.", "## Empty"]


def test_rule_like_note_gets_an_open_question_not_a_rule(synth_source):
    r = build(synth_source(), "## Never show\n- blood\n\nA quiet story.\n", None, {})
    m = r["meaning"]
    assert m["do_not"] == [] and m["notes"] == ["## Never show\n- blood\n\nA quiet story."]
    assert m["field_sources"]["notes"] == "user" and m["status"] == "user"
    assert any("never obeyed as a rule" in q and "do_not" in q for q in m["open_questions"])
    assert "blood" not in " ".join(m["open_questions"])  # the user's words are not quoted back


@pytest.mark.parametrize("line,expected", [
    ("palette: []   # hex (#1b2a49) or colour words (night blue)", "palette: []"),
    ("palette: [#c93523, night blue]   # hint", 'palette: ["#c93523", night blue]'),
    ("  - #0e2346", '  - "#0e2346"'),
    ("tone: dark #1 hit", 'tone: "dark #1 hit"'),
    ("tone: dark  # a comment", "tone: dark"),
    ("logline: Two keepers: one night", 'logline: "Two keepers: one night"'),
    ("  S01:   # intro#1 0:01.0-0:09.0", "  S01:"),
    ('  C1: {name: "", voices: []}   # proposes V1', '  C1: {name: "", voices: []}'),
    ("feel: yes", 'feel: "yes"'),
    ("voices:   # which character sings each voice (V1: C1 Name), or the number of singers", "voices:"),
    ("# a comment line", ""),
])
def test_tolerant_yaml_line(line, expected):
    assert tolerant_yaml_line(line) == expected


def test_broken_template_entry_keeps_the_rest_and_warns():
    text = ("```yaml\nlogline: \"x\"\ncharacters:\n  C1: {name: Ann, voices: [V1]}\n  C2: {name: \"Bo, voices: [V2]}\n"
            "do_not:\n  - no fire\n```\n")
    r = parse_intent(text)
    assert r["logline"] == "x" and r["do_not"] == ["no fire"] and r["characters"]["C1"]["name"] == "Ann"
    assert any("does not parse" in w for w in r["warnings"]) and "C2" not in r["characters"]
    assert r["notes"] == ['  C2: {name: "Bo, voices: [V2]}']  # kept verbatim, never silently dropped


def test_unknown_template_key_is_a_note():
    r = parse_intent("```yaml\nlogline: x\nmood_board: [fog, salt]\n```\n")
    assert r["logline"] == "x" and r["notes"] == ["mood_board: fog; salt"]
    assert any("unknown template key" in w for w in r["warnings"])
