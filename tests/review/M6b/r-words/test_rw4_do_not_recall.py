"""R-WORDS round 4, R4-2 (major): ordinary do-not headings (``## What I don't want``, ``## Avoid these``, ...) and
bulleted / numbered do-not labels (``- Never show: blood``, ``9. **Never show**: blood``) were silently filed as
``notes`` that never reached the video agent, with no warning.

Rewritten by ud1-meaning for user decision UD1 (W4): free text is never parsed into do-not rules (only the template's
``do_not`` is a hard constraint). The finding's intent, that the user's prohibitions never vanish silently, is
checked under that rule: the text is kept verbatim as a note, the note reaches brief.md, and the meaning stage asks
the user (an open question, the note not quoted) to move it into the template.

Synthetic text only (no lyrics).
"""
from __future__ import annotations

import pytest
from rw_m6b_support import brief_for, source

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build

STORY = "## The story\nTwo keepers wait for a ship.\n\n"


@pytest.mark.parametrize("heading", [
    "What I don't want",
    "Avoid these",
    "Things I never want to see",
    "Never show these",
])
def test_do_not_headings_are_kept_as_notes_and_flagged(heading):
    text = STORY + f"## {heading}\n- blood\n- lens flares\n"
    o = parse_intent(text)
    assert o["do_not"] == [] and o["notes"][-1] == f"## {heading}\n- blood\n- lens flares", o["notes"]
    res = build(source(), text, None, {})
    m = res["meaning"]
    assert any("never obeyed as a rule" in q and "do_not" in q for q in m["open_questions"]), m["open_questions"]
    brief = brief_for(res)
    assert "blood" in brief and "never rules" in brief, "the user's note does not reach brief.md"


@pytest.mark.parametrize("line", [
    "- Never show: blood",
    "- **Never show**: blood",
    "9. **Never show**: blood",
    "- Avoid: blood",
])
def test_do_not_label_as_a_bullet_is_a_note(line):
    o = parse_intent(STORY + line + "\n")
    assert o["do_not"] == [] and o["notes"] == ["## The story\nTwo keepers wait for a ship.\n\n" + line], o["notes"]


def test_the_template_do_not_is_the_rule():
    o = parse_intent(STORY + "do_not:\n  - blood\n  - lens flares\n")
    assert o["do_not"] == ["blood", "lens flares"] and o["notes"] == ["## The story\nTwo keepers wait for a ship."]
