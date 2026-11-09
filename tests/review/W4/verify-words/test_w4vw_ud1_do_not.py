"""W4 verify-words r1: W4A-UD1 (M6b meaning/intent.py) after the w4fix-words fix.

The fix parses ``do_not`` entry by entry (``_NESTED``), expands tabs in the indentation and keeps blank lines inside
a valueless key's list. Two ordinary ways of typing the do_not list still lose the hard rules:

* VWU1-a (new, introduced by putting do_not in ``_NESTED``): a valid rule list followed by ONE indented line that
  holds a colon (``  Also: lots of fog please`` or ``  chorus: no close-ups``). YAML fails, the per-entry fallback
  parses the list items into ``subl`` and the colon line into ``sub``; ``_load_region`` keeps ``sub if sub else
  subl``, so every typed rule is silently dropped and the stray line becomes the ONLY hard rule. No warning, nothing
  in ``unparsed_keys``, so brief.md says nothing either.
* VWU1-b (not fixed): a tab between ``-`` and the item at column 0 (``do_not:`` then ``-<TAB>show ...``). The fixer
  handles ``-<TAB>`` when the list is indented, but ``_scan_unfenced`` only continues a region over column-0 items that
  start with ``"- "``; the region ends at ``do_not:``, both rules become a free-text note and NO warning is raised.

Synthetic text only (no lyrics). Fast: the parser alone.
"""
from __future__ import annotations

import pytest

from mvh.stages.meaning.intent import parse_intent

RULES = ["show the singer's face", "use red light"]

STRAY_COLON = {
    "wish_with_colon": "do_not:\n  - show the singer's face\n  - use red light\n  Also: lots of fog please\n",
    "section_rule_line": "do_not:\n  - show the singer's face\n  - use red light\n  chorus: no close-ups\n",
}
TAB_AFTER_DASH_COL0 = "do_not:\n-\tshow the singer's face\n-\tuse red light\n"


def _got(r):
    return [str(x).strip().lower() for x in r["do_not"]]


@pytest.mark.parametrize("case", sorted(STRAY_COLON))
def test_vwu1a_rules_survive_a_stray_colon_line(case):
    r = parse_intent(STRAY_COLON[case])
    missing = [x for x in RULES if x not in _got(r)]
    assert not missing, (f"{case}: {len(missing)} of {len(RULES)} typed do_not rules were silently dropped "
                         f"(do_not={len(r['do_not'])}, notes={len(r['notes'])}, warnings={len(r['warnings'])}, "
                         f"unparsed={r['unparsed_keys']})")


def test_vwu1a_a_wish_never_becomes_the_only_hard_rule():
    r = parse_intent(STRAY_COLON["wish_with_colon"])
    promoted = [x for x in _got(r) if "fog" in x]
    assert not (promoted and not r["warnings"]), (
        "a stray 'Also: ...' wish typed under do_not became a hard do_not rule with no warning "
        f"(do_not={len(r['do_not'])})")


def test_vwu1b_tab_after_dash_at_column_0_keeps_rules():
    r = parse_intent(TAB_AFTER_DASH_COL0)
    missing = [x for x in RULES if x not in _got(r)]
    assert not missing, (f"'-<TAB>item' at column 0: {len(missing)} of {len(RULES)} rules became a free-text note "
                         f"(notes={len(r['notes'])}, warnings={len(r['warnings'])}, unparsed={r['unparsed_keys']})")


def test_vwu1b_tab_after_dash_at_column_0_is_at_least_surfaced():
    r = parse_intent(TAB_AFTER_DASH_COL0)
    if all(x in _got(r) for x in RULES):
        return
    assert r["warnings"] and "do_not" in r["unparsed_keys"], (
        "'-<TAB>item' under do_not silently became a note: no warning, no unparsed_keys entry, so neither "
        "meaning.json intent_unparsed nor brief.md mentions it")


def test_vwu1_controls_still_pass():
    """The cases the fixer targeted (and the indented '-<TAB>' form) keep working."""
    for t in ("do_not:\n\t- show the singer's face\n\t- use red light\n",
              "do_not:\n\n- show the singer's face\n- use red light\n",
              "do_not:\n  -\tshow the singer's face\n  -\tuse red light\n",
              "do_not:\n  - show the singer's face\n  - use red light\n\n  I'd also love fog, just a wish.\n"):
        assert all(x in _got(parse_intent(t)) for x in RULES)
