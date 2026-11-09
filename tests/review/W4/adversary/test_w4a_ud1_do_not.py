"""W4A-UD1 (M6b meaning/intent.py, UD1 / D78): a hard rule typed in the template is lost to a note.

UD1 makes the template's ``do_not`` the ONLY source of hard constraints. The tolerant parser parses each entry of
``characters``, ``voices``, ``sections``, ``line_singers`` and ``motifs`` on its own when a region does not parse
(``_NESTED``), but ``do_not`` is all-or-nothing: one YAML-invalid line anywhere under it demotes EVERY rule under it
to a free-text note (advisory, never obeyed). Three ordinary ways of typing it:

* a tab-indented list (Notepad inserts a tab; YAML forbids tabs) -> every rule becomes a note;
* one indented sentence after the list -> every rule becomes a note;
* ``do_not:`` then a blank line, then ``- item`` (valid YAML: a blank line inside a block sequence is allowed) -> the
  region scanner stops at the blank line, ``do_not`` is "untouched", the item becomes a note and NO warning is raised.

Synthetic text only (no lyrics). Fast: the parser alone.
"""

from __future__ import annotations

import pytest

from mvh.stages.meaning.intent import parse_intent

RULES = ["show the singer's face", "use red light"]

CASES = {
    "tab_indent": "do_not:\n\t- show the singer's face\n\t- use red light\n",
    "trailing_indented_sentence": ("do_not:\n  - show the singer's face\n  - use red light\n\n"
                                   "  I'd also love lots of fog, but that is just a wish.\n"),
    "blank_line_before_items": "do_not:\n\n- show the singer's face\n- use red light\n",
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_w4a_every_typed_do_not_rule_survives(case):
    r = parse_intent(CASES[case])
    got = [str(x).strip().lower() for x in r["do_not"]]
    missing = [x for x in RULES if x not in got]
    assert not missing, (f"{case}: {len(missing)} of {len(RULES)} hard rules typed under the template key do_not became "
                         f"free-text notes (do_not={len(got)}, notes={len(r['notes'])}, warnings={len(r['warnings'])})")


def test_w4a_blank_line_case_is_at_least_warned():
    r = parse_intent(CASES["blank_line_before_items"])
    if r["do_not"]:
        return
    assert r["warnings"], "do_not: + blank line + '- item' silently turned a hard rule into a note (no warning)"


def test_w4a_control_plain_list_parses():
    r = parse_intent("do_not:\n  - show the singer's face\n  - use red light\n")
    assert [str(x).lower() for x in r["do_not"]] == RULES
