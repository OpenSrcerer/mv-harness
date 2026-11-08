# ruff: noqa: E501
"""R-WORDS round 3 (r-words-m6b-r3), finding R3-2: hex colours typed into the interview template destroy the answer.

The template line is ``palette: []   # hex (#1b2a49) or colour words (night blue)``. A user who types hex codes the
natural way (``palette: [#0e2346, #f2a541, rust red]``) writes YAML where ``#`` starts a comment, so:
* fenced (the form the interview shows): the block does not parse and is removed from the free text too, so every
  answer is lost (logline, do_not rules); the warning wrongly says "free text used";
* unfenced: the free-text fallback loses the logline and the do_not rule and turns the template's own example
  ``#1b2a49`` (in the comment) into a user colour;
* block list (``- #0e2346``): the hex items load as null and are dropped without a warning.
Synthetic fixture only."""
from __future__ import annotations

import pytest
import rw_m6b_support as S

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build


def _filled(fenced: bool, block_list: bool = False) -> str:
    iv = build(S.source(), None, None, {})["interview"]
    a = iv.index("```yaml")
    b = iv.index("```", a + 7)
    t = iv[a:b + 3] + "\n"
    pal = "palette:\n  - #0e2346\n  - #f2a541\n  - rust red" if block_list else "palette: [#0e2346, #f2a541, rust red]"
    t = (t.replace('logline: ""', 'logline: "Two keepers light a harbour."')
          .replace("palette: []", pal, 1)
          .replace("do_not:   # rules", "do_not:\n  - No fire on people.\n#", 1))
    if not fenced:
        t = "\n".join(ln for ln in t.splitlines() if not ln.startswith("```")) + "\n"
    return t


@pytest.mark.parametrize("fenced", [True, False], ids=["fenced", "unfenced"])
def test_hex_palette_in_template_keeps_the_other_answers(fenced):
    r = parse_intent(_filled(fenced))
    assert r["do_not"] == ["No fire on people."], f"the user's do_not rule is lost ({r['form']}, {r['warnings']})"
    assert r["logline"] == "Two keepers light a harbour.", "the user's logline is lost"


@pytest.mark.parametrize("fenced", [True, False], ids=["fenced", "unfenced"])
def test_hex_palette_in_template_is_read(fenced):
    r = parse_intent(_filled(fenced))
    assert "#1b2a49" not in r["palette"], "the template comment's example colour became a user colour"
    assert {"#0e2346", "#f2a541"} <= set(r["palette"]), f"typed hex colours lost: {r['palette']}"


def test_hex_block_list_not_silently_dropped():
    r = parse_intent(_filled(True, block_list=True))
    assert {"#0e2346", "#f2a541"} <= set(r["palette"]) or r["warnings"], \
        f"'- #0e2346' items vanish with no warning: palette={r['palette']}"
