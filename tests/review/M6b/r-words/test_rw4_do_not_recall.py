"""R-WORDS round 4, R4-2 (major; the headings part is a regression from the R3-3/R3-4 fix).

The fix anchored ``_DO_NOT_HEAD`` to a heading that is a do-not phrase and nothing more (plus a few fixed suffixes).
Ordinary do-not headings that the pre-fix parser read as rules now fall through to ``notes``:
``## What I don't want``, ``## Avoid these``, ``## Things I never want to see``, ``## Never show these``.
A do-not label written as a bullet (``- Never show: blood``), or numbered the way the interview numbers its
question (``9. **Never show**: blood``), is not a rule either: it is a note, or under a story heading it is folded
into the summary (grammar rule 3 accepts only label lines that are not bullets).
``notes`` are not in brief.md (the LLM entry point) and are not hard constraints, so the user's prohibitions never
reach the video agent. No warning is given.

Synthetic text only (no lyrics).
"""
from __future__ import annotations

import pytest

from mvh.stages.meaning.intent import parse_intent

STORY = "## The story\nTwo keepers wait for a ship.\n\n"


@pytest.mark.parametrize("heading", [
    "What I don't want",
    "Avoid these",
    "Things I never want to see",
    "Never show these",
])
def test_common_do_not_headings_give_do_not_rules(heading):
    o = parse_intent(STORY + f"## {heading}\n- blood\n- lens flares\n")
    assert o["do_not"] == ["blood", "lens flares"], (
        f"'## {heading}' bullets became notes, not do_not rules (do_not={o['do_not']}, notes={o['notes']})")


@pytest.mark.parametrize("line", [
    "- Never show: blood",
    "- **Never show**: blood",
    "9. **Never show**: blood",
    "- Avoid: blood",
])
def test_do_not_label_as_a_bullet_is_a_rule(line):
    o = parse_intent(STORY + line + "\n")
    assert o["do_not"] == ["blood"], (
        f"a bulleted do-not label is not a do_not rule (do_not={o['do_not']}, notes={o['notes']})")
