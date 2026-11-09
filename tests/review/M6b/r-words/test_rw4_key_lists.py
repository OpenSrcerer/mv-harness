"""R-WORDS round 4, R4-1 (major, regression from the W3 grammar rewrite of intent.py).

A user who writes the template's own key names in lower case and then answers in markdown bullets
(``characters:`` then ``- C1 The Keeper = V1``; ``sections:`` then ``- Chorus: ...``; ``line_singers:`` then
``- L005: C1+C2``) now loses those answers with no warning. Layer 2 takes the key plus its column-0 bullets as a
template region; YAML loads a list where a map is expected; ``_apply_yaml`` ignores a list for characters, sections
and line_singers. Nothing goes to notes and nothing is warned. The pre-rewrite parser read all three.

Synthetic text only (no lyrics).
"""
from __future__ import annotations

import pytest

from mvh.stages.meaning.intent import parse_intent

CHARS = "Two keepers wait for a ship.\n\ncharacters:\n- C1 The Keeper = V1 (the low voice). Lead.\n- C2 The Tide = V2\n"
SECS = "Two keepers wait for a ship.\n\nsections:\n- Chorus: wide shots, slow.\n- Intro: fog over water.\n"
SINGERS = "Two keepers wait for a ship.\n\nline_singers:\n- L005: C1+C2\n- L006: C2\n"


def _lost_silently(o) -> bool:
    return not any("intent.md" in w for w in o["warnings"])


def test_lower_case_characters_key_with_bullets_keeps_the_characters():
    o = parse_intent(CHARS)
    got = {cid: (c["name"], c["voices"]) for cid, c in o["characters"].items()}
    assert got.get("C1") == ("The Keeper", ["V1"]) and got.get("C2") == ("The Tide", ["V2"]), (
        f"characters given as bullets under 'characters:' were dropped (got {got}; "
        f"silently={_lost_silently(o)})")


def test_lower_case_sections_key_with_bullets_keeps_the_section_notes():
    o = parse_intent(SECS)
    keys = {s["key"] for s in o["sections"]}
    assert {"chorus", "intro"} <= keys, (
        f"section notes given as bullets under 'sections:' were dropped (got {sorted(keys)}; "
        f"silently={_lost_silently(o)})")


@pytest.mark.parametrize("text", [SINGERS, SINGERS.replace("\n- ", "\n  - ")], ids=["col0", "indented"])
def test_lower_case_line_singers_key_with_bullets_keeps_the_singers(text):
    o = parse_intent(text)
    assert o["line_singers"].get("L005") == ["C1", "C2"] and o["line_singers"].get("L006") == ["C2"], (
        f"line singers given as bullets under 'line_singers:' were dropped (got {o['line_singers']}; "
        f"silently={_lost_silently(o)})")
