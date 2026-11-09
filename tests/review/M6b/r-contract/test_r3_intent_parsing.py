"""R-CONTRACT (M6b) round 3: intent.md parsing after the round-2 fixes (synthetic fixture only, invented lyrics).

R3-1 (major, new): the interview template's own palette hint breaks the whole template. The template line is
``palette: []   # hex (#1b2a49) or colour words (night blue)``; typing a hex code into the brackets as the hint
shows (``palette: [#c93523, night blue]``) is a YAML ParserError (``#`` after ``[`` starts a comment), so the
whole block is dropped: the user's characters and do_not rules are lost and the meaning goes back to pending.

R3-2 (major, R2-2 / r-words N3 not fully fixed): when the unfenced template does not parse as YAML (R3-1's hex
palette, or no ``# mvh-intent`` marker line plus any ``Key:`` note elsewhere in the file), the whole file is
re-read as free text, and the template's EXAMPLE COMMENTS become user claims: ``line_singers:   # ... {L005: C1+C2}``
gives L005 to C1+C2 at user precedence and ``palette: []   # hex (#1b2a49) ...`` makes #1b2a49 the user's palette.
R2-2's fix asked to never feed template comment lines to the free-text parser; only ``{name`` lines and ``# ...``
section notes are skipped.

R3-3 (major, regression of the N2 fix): a do-not label line (``Never show: blood``) opens a block that keeps
every following bullet, even after a blank line. Character lines and section notes written as bullets below it
become do-not rules (hard constraints on every frame per SKILL.md) and the characters are lost.

R3-4 (major): ``_DO_NOT_HEAD`` is searched anywhere in a heading, so a title heading such as ``# Never Let Me Go``
or ``# Don't Stop Me Now: my notes`` (``don't`` was added by the N2 fix) turns the story, the character lines and
the section notes under it into do-not rules.

UD1 (W4, user decision): the template is the only source of fields and do-not rules; free text is the user's notes,
kept verbatim and never parsed. R3-1 and R3-2 stand as written; R3-3 and R3-4 are restated under that rule.
"""
from __future__ import annotations

import pytest
from rc2_support import source, template_of

from mvh.stages.meaning.stage import build


def _template(fenced: bool) -> str:
    first = build(source(), None, None, {})
    return template_of(first["interview"], fenced=fenced)


def _fill(t: str) -> str:
    t = t.replace('C1: {name: ""', 'C1: {name: "Keeper"', 1)
    t = t.replace("do_not:   # rules in your own words; copied verbatim to every agent",
                  "do_not:   # rules in your own words; copied verbatim to every agent\n  - never show faces")
    assert "Keeper" in t and "never show faces" in t
    return t


# ------------------------------------------------------------------------------------------------ R3-1
@pytest.mark.parametrize("fenced", [True, False], ids=["fenced", "unfenced"])
def test_hex_palette_as_the_template_hint_shows_keeps_the_answers(fenced: bool) -> None:
    t = _fill(_template(fenced))
    assert "palette: []   # hex (#1b2a49)" in t, "precondition: the template's palette hint"
    t = t.replace("palette: []", "palette: [#c93523, night blue]", 1)
    m = build(source(), t, None, {})["meaning"]
    c1 = next(c for c in m["characters"] if c["id"] == "C1")
    problems = []
    if "never show faces" not in m["do_not"]:
        problems.append(f"do_not lost ({m['do_not']})")
    if c1["name"] != "Keeper":
        problems.append(f"C1 named {c1['name']!r}")
    if "#c93523" not in m["palette"]:
        problems.append(f"palette {m['palette']}")
    assert not problems, ("typing a hex code into the template's palette brackets, as its hint shows, drops the template: "
                          + "; ".join(problems) + f" (status {m['status']}, intent_form {m['intent_form']})")


# ------------------------------------------------------------------------------------------------ R3-2
def _no_marker(t: str) -> str:
    return "\n".join(ln for ln in t.splitlines() if "mvh-intent" not in ln)


FALLBACKS = {
    "hex_palette": lambda: _fill(_template(False)).replace("palette: []", "palette: [#c93523, night blue]", 1),
    "no_marker_plus_note": lambda: _no_marker(_template(False)) + "\n\n## Notes\nChorus: everything glows.\n",
}


@pytest.mark.parametrize("case", sorted(FALLBACKS))
def test_template_example_comments_never_become_user_claims(case: str) -> None:
    text = FALLBACKS[case]()
    assert "{L005: C1+C2}" in text and "#1b2a49" in text, "precondition: the template's example comments"
    r = build(source(), text, None, {})
    m, intent = r["meaning"], r["intent"]
    problems = []
    if "L005" in intent["line_singers"]:
        problems.append(f"line_singers L005 = {intent['line_singers']['L005']} (the template's example comment)")
    if "#1b2a49" in m["palette"]:
        problems.append(f"palette {m['palette']} source {m['field_sources'].get('palette')} (the template's example hex)")
    l005 = [it for it in r["singing"] if it["line_id"] == "L005" and it.get("source") == "user"]
    if l005:
        problems.append("events/singing.json L005 has source 'user'")
    assert not problems, f"{case}: " + "; ".join(problems) + f" (status {m['status']}, intent_form {m['intent_form']})"


# ------------------------------------------------------------------------------------------------ R3-3 (UD1)
# Rewritten by ud1-meaning (W4, user decision UD1): free text is never a do-not rule or a field. R3-3 was about
# free text being swallowed into hard constraints; under UD1 nothing in free text is a constraint at all, so the
# findings' intent becomes: the user's lines are kept verbatim (as notes), no rule or character is invented from
# them, and the same answers written in the template give exactly the rule and the characters.
def test_do_not_label_and_bullets_in_free_text_are_notes_not_rules() -> None:
    text = "Never show: blood\n\n- C1 The Keeper = V1\n- C2 The Tide = V2\n"
    r = build(source(), text, None, {})
    m = r["meaning"]
    user_chars = [c["id"] for c in m["characters"] if c["provenance"]["status"] == "user"]
    assert m["do_not"] == [] and not user_chars, (f"free text became rules {m['do_not']} or characters {user_chars}")
    assert m["notes"] == [text.strip()], m["notes"]  # no heading: the whole free text is one verbatim note
    assert any("never obeyed as a rule" in q for q in m["open_questions"])
    tmpl = "do_not:\n  - blood\ncharacters:\n- C1 The Keeper = V1\n- C2 The Tide = V2\n"
    t = build(source(), tmpl, None, {})["meaning"]
    names = {c["id"]: (c["name"], c["provenance"]["status"]) for c in t["characters"]}
    assert t["do_not"] == ["blood"] and names.get("C1") == ("The Keeper", "user") and not t["notes"], (t["do_not"], names)


def test_avoid_label_and_section_bullets_in_free_text_are_notes() -> None:
    text = "A keeper waits for the light.\n\nAvoid: lens flares\n\n- Chorus: wide shots\n- Bridge: one candle\n"
    m = build(source(), text, None, {})["meaning"]
    feels = {s["section_id"] for s in m["sections"] if (s.get("field_sources") or {}).get("feel") == "user"}
    assert m["do_not"] == [] and not feels, (m["do_not"], feels)
    assert m["notes"] == [text.strip()], m["notes"]
    tmpl = "do_not: [lens flares]\nsections:\n- Chorus: wide shots\n- Bridge: one candle\n"
    t = build(source(), tmpl, None, {})["meaning"]
    feels = {s["section_id"] for s in t["sections"] if (s.get("field_sources") or {}).get("feel") == "user"}
    assert t["do_not"] == ["lens flares"] and feels, (t["do_not"], feels)


# ------------------------------------------------------------------------------------------------ R3-4 (UD1)
@pytest.mark.parametrize("title", ["Never Let Me Go", "Don't Stop Me Now: my notes"])
def test_title_heading_with_a_do_not_word_is_a_note_not_a_rule(title: str) -> None:
    text = f"# {title}\n\nA keeper waits for the light. The tide takes it.\n\nC1 The Keeper = V1\nChorus: wide shots\n"
    m = build(source(), text, None, {})["meaning"]
    assert not m["do_not"], f"heading '# {title}': do_not {m['do_not']}"
    assert m["notes"] == [f"# {title}\nA keeper waits for the light. The tide takes it.\n\nC1 The Keeper = V1\n"
                          "Chorus: wide shots"], m["notes"]
