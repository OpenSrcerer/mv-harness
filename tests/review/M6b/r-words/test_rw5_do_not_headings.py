"""R-WORDS round 5, R5-4 (major; R4-2 only partly fixed).

The R4-2 fix made the do-not heading rule a closed vocabulary: a heading made only of trigger words and a fixed list
of filler words (at most 8 tokens). The four headings named in R4-2 pass, but ordinary variants of them still send
the user's prohibitions to ``notes`` (not hard constraints; brief.md shows at most 3 notes cut to 12 words), with
no warning. R4-2's suggested fix asked for a warning when bullets under a heading with never/don't/avoid fall to
notes; none was added.

Synthetic text only (no lyrics).
"""
from __future__ import annotations

import pytest

from mvh.stages.meaning.intent import parse_intent

STORY = "## The story\nTwo keepers wait for a ship.\n\n"


@pytest.mark.parametrize("heading", [
    "Avoid at all costs",
    "Things I don't want to see in the video",
    "What I'd never want to see",
    "No-nos",
    "Hard limits",
])
def test_do_not_heading_variants(heading):
    o = parse_intent(STORY + f"## {heading}\n- blood\n- lens flares\n")
    assert o["do_not"] == ["blood", "lens flares"], (
        f"'## {heading}': do_not={o['do_not']}, notes={o['notes']}, warnings={o['warnings']}")


def test_bullets_under_a_never_heading_that_fall_to_notes_are_warned():
    """Whatever the vocabulary, a heading with 'never'/'avoid'/'don't' whose bullets end up as notes must warn."""
    o = parse_intent(STORY + "## Avoid at all costs\n- blood\n")
    assert o["do_not"] == ["blood"] or o["warnings"], (
        f"bullets under a do-not-looking heading became notes with no warning (notes={o['notes']})")
