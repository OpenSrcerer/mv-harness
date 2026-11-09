"""R-WORDS round 5, R5-4 (major; R4-2 only partly fixed): ordinary variants of do-not headings ('Avoid at all costs',
'No-nos', 'Hard limits', ...) sent the user's prohibitions to ``notes`` (not hard constraints, cut to 12 words in
brief.md) with no warning.

Rewritten by ud1-meaning for user decision UD1 (W4): no heading vocabulary is guessed any more; free text is the
user's notes and only the template's ``do_not`` is a rule. The finding's two demands are checked under that rule:
(1) the user's words are never silently lost: each heading block is one verbatim note, shown in brief.md in full
(within a 120-word budget) and in meaning.md; (2) a warning: the meaning stage adds an open question telling the
user that free text is never obeyed as a rule and that rules go under ``do_not`` in the template.

Synthetic text only (no lyrics).
"""
from __future__ import annotations

import pytest
from rw_m6b_support import source

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build

STORY = "## The story\nTwo keepers wait for a ship.\n\n"


@pytest.mark.parametrize("heading", [
    "Avoid at all costs",
    "Things I don't want to see in the video",
    "What I'd never want to see",
    "No-nos",
    "Hard limits",
])
def test_do_not_heading_variants_are_verbatim_notes(heading):
    o = parse_intent(STORY + f"## {heading}\n- blood\n- lens flares\n")
    assert o["do_not"] == [] and o["notes"][-1] == f"## {heading}\n- blood\n- lens flares", o["notes"]


def test_bullets_under_a_never_heading_get_a_warning():
    """Whatever the vocabulary, a free-text note with never / avoid / don't makes the stage ask for the template."""
    m = build(source(), STORY + "## Avoid at all costs\n- blood\n", None, {})["meaning"]
    assert m["do_not"] == []
    assert any("never obeyed as a rule" in q and "under do_not" in q for q in m["open_questions"]), m["open_questions"]
