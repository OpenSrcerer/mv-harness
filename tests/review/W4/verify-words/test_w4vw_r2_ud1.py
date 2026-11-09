"""W4 verify-words r2: UD1 (M6b meaning/intent.py) after w4fix-words-r2 (VWU1-a, VWU1-b).

VWU1-a and VWU1-b are fixed for the reported shapes (see docs/review/W4-verify-words.md). Still open:

* VWR2-1 (major, VWU1-a not fully fixed): ``_load_region`` still ends with ``merged[key] = sub if sub else subl``.
  When every ``- `` item under ``do_not`` fails to parse (one unclosed quote, the synth fixture's own quoted style) and
  a stray ``Also: ...`` line sits beside it, ``subl`` is empty and the stray wish becomes the ONLY hard rule. The
  warning names the broken item, never the promoted wish, so meaning.json / brief.md present ``Also: lots of fog
  please`` as a do-not rule (an agent would avoid fog). The round-2 invariant ("a bare 'key: value' line among a list
  key's entries is a note, never an item") holds only while at least one item parsed.
* VWR2-2 (minor): ``do_not:`` followed by column-0 ``* rule`` / ``• rule`` / ``– rule`` bullets (Markdown and word
  processors type these) silently becomes a free-text note: 0 warnings, nothing in ``unparsed_keys``. The same silent
  demotion VWU1-b fixed for ``-<TAB>``; at minimum it should be surfaced.
* VWR2-3 (minor): a stray ``key: value`` line indented deeper than the item before it (``  - rule`` then
  ``    Also: fog``) joins that item's entry, the entry fails, and the rule is demoted with it (warned). The grammar
  promises "one bad line never takes the other rules with it".

Synthetic text only (no lyrics). Fast: the parser alone.
"""
from __future__ import annotations

import pytest

from mvh.stages.meaning.intent import parse_intent

RULES = ["show the singer's face", "use red light"]


def _got(r):
    return [str(x).strip().lower() for x in r["do_not"]]


# ---------------------------------------------------------------------------------------------- VWR2-1 (major)
BROKEN_PLUS_STRAY = {
    "unclosed_quote": 'do_not:\n  - "No text on screen except the lyrics.\n  Also: lots of fog please\n',
    "unclosed_bracket": "do_not:\n  - [no red light\n  Also: lots of fog please\n",
    "section_line": 'do_not:\n  - "No text on screen except the lyrics.\n  chorus: no close-ups\n',
}


@pytest.mark.parametrize("case", sorted(BROKEN_PLUS_STRAY))
def test_vwr2_1_stray_line_never_becomes_a_rule_when_the_items_fail(case):
    r = parse_intent(BROKEN_PLUS_STRAY[case])
    stray = BROKEN_PLUS_STRAY[case].splitlines()[-1].strip().lower()
    promoted = [x for x in _got(r) if x == stray]
    assert not promoted, (f"{case}: every '- ' item failed and the stray line beside them became the only do_not "
                          f"rule (do_not={len(r['do_not'])}, warnings={len(r['warnings'])}); round 2 keeps such a line "
                          "as a note only while some item parsed")


def test_vwr2_1_same_stray_line_same_outcome():
    """The stray line's fate must not depend on whether a neighbouring item parsed."""
    ok = parse_intent("do_not:\n  - use red light\n  Also: lots of fog please\n")
    bad = parse_intent('do_not:\n  - "use red light\n  Also: lots of fog please\n')
    fog_ok = any("fog" in x for x in _got(ok))
    fog_bad = any("fog" in x for x in _got(bad))
    assert fog_ok == fog_bad, (f"the stray wish is a rule={fog_bad} when the item is broken but a rule={fog_ok} when it "
                               "parses")


# ---------------------------------------------------------------------------------------------- VWR2-2 (minor)
OTHER_BULLETS = {
    "star": "do_not:\n* show the singer's face\n* use red light\n",
    "bullet": "do_not:\n• show the singer's face\n• use red light\n",
    "en_dash": "do_not:\n– show the singer's face\n– use red light\n",
    "dash_nbsp": "do_not:\n- show the singer's face\n- use red light\n",
}


@pytest.mark.parametrize("case", sorted(OTHER_BULLETS))
def test_vwr2_2_rules_typed_as_other_bullets_are_at_least_surfaced(case):
    r = parse_intent(OTHER_BULLETS[case])
    if all(x in _got(r) for x in RULES):
        return  # read as rules: fine
    assert r["warnings"] or r["unparsed_keys"], (
        f"{case}: rules typed under 'do_not:' as column-0 bullets silently became a free-text note "
        f"(do_not={len(r['do_not'])}, notes={len(r['notes'])}, 0 warnings, unparsed_keys=[]): never obeyed and "
        "nothing in meaning.json intent_unparsed, the open questions or brief.md says so")


# ---------------------------------------------------------------------------------------------- VWR2-3 (minor)
DEEPER_STRAY = {
    "indented_list": "do_not:\n  - show the singer's face\n    Also: lots of fog please\n  - use red light\n",
    "col0_list": "do_not:\n- show the singer's face\n- use red light\n  Also: lots of fog please\n",
}


@pytest.mark.parametrize("case", sorted(DEEPER_STRAY))
def test_vwr2_3_a_deeper_stray_line_does_not_take_its_rule(case):
    r = parse_intent(DEEPER_STRAY[case])
    missing = [x for x in RULES if x not in _got(r)]
    assert not missing, (f"{case}: a stray 'Also: ...' line indented under a rule took {len(missing)} rule(s) into a "
                         f"note with it (warnings={len(r['warnings'])}); the grammar says one bad line never takes the "
                         "other rules with it")


# ---------------------------------------------------------------------------------------------- controls (pass)
def test_vwr2_controls_round2_shapes_hold():
    for t in ("do_not:\n  - show the singer's face\n  - use red light\n  Also: lots of fog please\n",
              "do_not:\n  Also: lots of fog please\n  - show the singer's face\n  - use red light\n",
              "do_not:\n  - show the singer's face\n  Also: fog\n  - use red light\n  Bridge: dark\n",
              "do_not:\n\t- show the singer's face\n\t- use red light\n\tAlso: fog\n",
              "do_not:\n-\tshow the singer's face\n-\tuse red light\n",
              "do_not:\r\n-\tshow the singer's face\r\n-\tuse red light\r\n",
              "```yaml\ndo_not:\n-\tshow the singer's face\n-\tuse red light\n",
              "do_not:\n-\tshow the singer's face\n-\tuse red light\ntone: dark\n"):
        r = parse_intent(t)
        assert all(x in _got(r) for x in RULES)
        assert not any("fog" in x or "dark" in x for x in _got(r))
