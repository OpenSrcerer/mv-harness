# ruff: noqa: E501
"""R-WORDS round 3 (r-words-m6b-r3), finding R3-3: the do-not detection now swallows text that is not a prohibition.

* The N2 fix opens a do-not block at a label line ('Avoid: ...', '**Never show**') and keeps it open across blank
  lines and every following bullet, so a list of section notes after a blank line becomes do_not rules (verbatim
  hard constraints for every agent) and the section notes are lost.
* ``_DO_NOT_HEAD`` matches a do-not word anywhere in a heading, so '## The story: a night that never ends' makes the
  story paragraph a do_not rule and the logline/summary are lost.
Synthetic text only."""
from __future__ import annotations

from mvh.stages.meaning.intent import parse_intent


def test_bullets_after_blank_line_are_not_swallowed_by_avoid_label():
    r = parse_intent("Avoid: cliches.\n\n- Intro: slow drift over water.\n- Drop: wide shots, every lantern at once.\n")
    assert r["do_not"] == ["cliches."], f"section notes became do_not rules: {r['do_not']}"
    assert {s["key"] for s in r["sections"]} == {"intro", "drop"}, "the section notes are lost"


def test_story_heading_with_never_is_not_a_do_not_block():
    r = parse_intent("## The story: a night that never ends\nTwo keepers light a harbour. They lose each other at dawn.\n\n"
                     "## Never show\n- No fire.\n")
    assert r["do_not"] == ["No fire."], f"the story became a do_not rule: {len(r['do_not'])} rules"
    assert r["logline"] == "Two keepers light a harbour.", "the user's logline is lost"
