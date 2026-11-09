"""R-CONTRACT (M6b) round 2, R2-2 (major): round-1 F3 is fixed only for a file that is nothing but the template.

interview.md: "answer in meaning/intent.md (free text is fine, or copy the template at the end)", and the template's
first line says "copy this block ... (with or without the markdown fence)". ``parse_intent`` now reads the file as
YAML only when the WHOLE file is the template. Three natural ways of doing what the interview says fall back to
free text:

* a ``## The story`` paragraph, then the template (unfenced);
* the template with its opening ```` ```yaml ```` but without the closing fence (a partial copy);
* the template (unfenced), then one line of prose.

In each, the user's ``do_not`` rule is lost, C1 is named ``{name`` and a section's feel becomes the template's
comment (``# chorus#2 0:34.5-0:50.5``), all at user precedence. The only change from round 1 is a generic warning.

R2-3 (major, regression of the F3 fix): ``_looks_like_template`` takes any file whose first line starts with a
lowercase template key for the template. A free-text answer ``palette: night blue, #f2a541, rust red`` then parses
as YAML: ``#f2a541, rust red`` is a YAML comment (two of three colours lost) and the ``chorus:`` note is an unknown
key (dropped), with no warning. Before the fix the free-text parser kept all of it.

UD1 (W4): the template is the only source of fields; free text is the user's notes. R2-3's test is restated under
that rule (nothing lost: the colours through the template's tolerances, the ``chorus:`` line as a note).
"""
from __future__ import annotations

import re

import pytest
from rc2_support import source, template_of

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build


def _filled_template() -> str:
    first = build(source(), None, None, {})
    t = template_of(first["interview"], fenced=False)
    t = t.replace('C1: {name: ""', 'C1: {name: "Keeper"', 1)
    t = t.replace("do_not:   # rules in your own words; copied verbatim to every agent",
                  "do_not:   # rules in your own words; copied verbatim to every agent\n  - never show faces")
    t = re.sub(r'(  S05:.*\n(?:    .*\n){3})    feel: ""', r'\1    feel: "slow burn"', t)
    assert "Keeper" in t and "never show faces" in t and "slow burn" in t
    return t


VARIANTS = {
    "story_then_template": lambda t: "## The story\nA keeper waits for the light.\n\n" + t,
    "open_fence_only": lambda t: "```yaml\n" + t,
    "template_then_prose": lambda t: t + "\nThe end should be quiet.\n",
}


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_template_answers_survive_free_text_around_them(variant: str) -> None:
    text = VARIANTS[variant](_filled_template())
    m = build(source(), text, None, {})["meaning"]
    c1 = next(c for c in m["characters"] if c["id"] == "C1")
    s05 = next(s for s in m["sections"] if s["section_id"] == "S05")
    problems = []
    if "never show faces" not in m["do_not"]:
        problems.append(f"do_not rule lost (do_not={m['do_not']})")
    if c1["name"] != "Keeper":
        problems.append(f"C1 named {c1['name']!r}")
    if s05["feel"] != "slow burn":
        problems.append(f"S05 feel {s05['feel']!r}")
    assert not problems, f"{variant}: " + "; ".join(problems) + f" (intent_form={m['intent_form']}, status={m['status']})"


def test_lowercase_palette_line_keeps_every_colour_and_the_line_after_it() -> None:
    """Rewritten for UD1 (W4, ud1-meaning). R2-3 asked that this text lose nothing. Under UD1 a column-0 lower-case
    template key (``palette:``) IS the unfenced template, and the template's tolerances keep all three colours
    (``#f2a541`` is a value, not a comment). ``chorus:`` is not a template key, so that line is free text: it is
    kept verbatim as the user's note and is never turned into a section feel."""
    r = parse_intent("palette: night blue, #f2a541, rust red\nchorus: wide shots, every lantern at once\n")
    assert len(r["palette"]) == 3 and not r["palette_unparsed"], (
        f"palette {r['palette']} unparsed {r['palette_unparsed']} (form {r['form']!r}, warnings {r['warnings']})")
    assert r["notes"] == ["chorus: wide shots, every lantern at once"] and r["sections"] == [], (
        f"the free-text line was dropped or parsed: notes {r['notes']}, sections {[s['key'] for s in r['sections']]}")
    assert not r["warnings"]
