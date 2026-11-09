"""R-WORDS round 3 (r-words-m6b-r3), finding R3-3: the do-not detection swallowed text that is not a prohibition.

* The N2 fix opened a do-not block at a label line ('Avoid: ...', '**Never show**') and kept it open across blank
  lines and every following bullet, so a list of section notes after a blank line became do_not rules (verbatim
  hard constraints for every agent) and the section notes were lost.
* ``_DO_NOT_HEAD`` matched a do-not word anywhere in a heading, so '## The story: a night that never ends' made the
  story paragraph a do_not rule and the logline/summary were lost.

Rewritten by ud1-meaning for user decision UD1 (W4): free text is never parsed into rules or fields. The finding's
intent (nothing is swallowed into hard constraints, nothing the user wrote is lost) is checked under that rule: every
line is kept verbatim in the notes and only the template makes rules. Synthetic text only."""
from __future__ import annotations

from mvh.stages.meaning.intent import parse_intent


def test_bullets_after_an_avoid_label_are_kept_and_never_rules():
    r = parse_intent("Avoid: cliches.\n\n- Intro: slow drift over water.\n- Drop: wide shots, every lantern at once.\n")
    assert r["do_not"] == [] and r["sections"] == [], f"free text became rules {r['do_not']} / sections {r['sections']}"
    assert r["notes"] == ["Avoid: cliches.\n\n- Intro: slow drift over water.\n- Drop: wide shots, every lantern at once."]


def test_story_heading_with_never_is_a_note_with_its_story():
    r = parse_intent("## The story: a night that never ends\nTwo keepers light a harbour. They lose each other at dawn.\n\n"
                     "## Never show\n- No fire.\n")
    assert r["do_not"] == [] and r["logline"] is None
    assert r["notes"] == ["## The story: a night that never ends\nTwo keepers light a harbour. They lose each other at dawn.",
                          "## Never show\n- No fire."]


def test_the_same_answers_in_the_template_are_rules_and_fields():
    r = parse_intent("logline: Two keepers light a harbour.\ndo_not:\n  - No fire.\n  - cliches\n"
                     "sections:\n- Intro: slow drift over water.\n- Drop: wide shots, every lantern at once.\n")
    assert r["do_not"] == ["No fire.", "cliches"] and r["logline"] == "Two keepers light a harbour."
    assert {s["key"] for s in r["sections"]} == {"intro", "drop"} and not r["notes"]
