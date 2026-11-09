"""R-WORDS round 5, R5-1 (major; regression from the grammar-v2/v3 rewrite).

A field or do-not label written in bold WITH THE COLON INSIDE THE BOLD (``**Story:**``, ``**Never show:**``,
``**Palette:**``) on a line of its own, with the answer below it, gave the value ``*``: the user's logline became
``*`` (first line of brief.md), a do-not rule ``*`` was copied to every agent and the real answer fell to notes.

Rewritten by ud1-meaning for user decision UD1 (W4): markdown labels in free text are not parsed at all. The free
text is the user's notes, verbatim; no field or rule can take a garbled value from it. The finding's intent (never a
``*`` value, never a lost answer) is checked under that rule, and the template is shown to give the same answers as
fields and rules.

Synthetic text only (no lyrics).
"""
from __future__ import annotations

import pytest
from rw_m6b_support import brief_for, source

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build

STORY = "## The story\nTwo keepers wait for a ship.\n\n"


@pytest.mark.parametrize("label", ["**Never show:**", "**Avoid:**", "**Don't:**", "- **Never show:**"])
def test_bold_colon_do_not_label_and_its_bullets_are_one_verbatim_note(label):
    body = "\n  - blood\n  - lens flares\n" if label.startswith("- ") else "\n- blood\n- lens flares\n"
    o = parse_intent(STORY + label + body)
    assert o["do_not"] == [] and "*" not in o["do_not"]
    assert o["notes"] == [STORY.strip() + "\n\n" + label + body.rstrip("\n")], o["notes"]


@pytest.mark.parametrize("label,field", [("**Story:**", "summary"), ("**Setting:**", "setting"), ("**Tone:**", "tone")])
def test_bold_colon_field_label_is_a_note_never_a_star_value(label, field):
    text = ("## Intro\n\n" if field != "summary" else "") + f"{label}\nTwo keepers wait for a ship that never returns.\n"
    o = parse_intent(text)
    assert o[field] is None and o["logline"] is None, f"'{label}' gave {field} = {o[field]!r}"
    assert any(f"{label}\nTwo keepers wait" in n for n in o["notes"]), o["notes"]


def test_bold_colon_palette_label_is_a_note_and_the_template_palette_is_read():
    o = parse_intent("**Palette:**\n- night blue\n- rust red\n")
    assert o["palette"] == [] and o["palette_unparsed"] == [] and o["notes"] == ["**Palette:**\n- night blue\n- rust red"]
    t = parse_intent("palette:\n- night blue\n- rust red\n")
    assert t["palette_names"] == ["night blue", "rust red"] and not t["notes"]


def test_bold_colon_labels_never_reach_brief_as_star():
    """End to end on the synthetic song: brief.md never shows a '*' value and carries the user's note."""
    res = build(source(), "**Story:**\nTwo keepers wait for a ship that never returns.\n\n**Never show:**\n- blood\n",
                None, {})
    m = res["meaning"]
    assert m["logline"] != "*" and "*" not in (m.get("do_not") or []), (m["logline"], m.get("do_not"))
    assert m["field_sources"].get("logline") != "user" and m["do_not"] == []
    brief = brief_for(res)
    bad = [ln for ln in brief.splitlines() if ln.rstrip().endswith(": *") or ln.strip() in ("- *", "* *")]
    assert not bad, f"brief.md carries the '*' value: {bad[:3]}"
    assert "Two keepers wait" in brief, "the user's note does not reach brief.md"
