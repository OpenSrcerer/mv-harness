"""R-WORDS round 5, R5-1 (major; regression from the grammar-v2/v3 rewrite).

A field or do-not label written in bold WITH THE COLON INSIDE THE BOLD (``**Story:**``, ``**Never show:**``,
``**Palette:**``), the most common markdown way to write a label, on a line of its own with the answer below it,
gives the value ``*``. The label regexes (``_LABEL``, ``_DO_NOT_INLINE``, ``_PALETTE``) end with
``:\\s*\\**\\s*(\\S.*?)``: the closing ``**`` is split, one ``*`` is eaten by ``\\**`` and the other is taken as the
value. So the user's logline and summary become ``*`` (at user precedence, first line of brief.md), a do-not rule
``*`` is copied verbatim to every agent, the palette is ``['*']`` unparsed, and the real answer below the label falls
to notes or is folded into the story summary. The pre-rewrite parser read ``**Never show:**`` + bullets as rules.

Synthetic text only (no lyrics).
"""
from __future__ import annotations

import pytest
from rw_m6b_support import brief_for, source

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build

STORY = "## The story\nTwo keepers wait for a ship.\n\n"


@pytest.mark.parametrize("label", ["**Never show:**", "**Avoid:**", "**Don't:**", "- **Never show:**"])
def test_bold_colon_do_not_label_lists_its_bullets(label):
    body = "\n  - blood\n  - lens flares\n" if label.startswith("- ") else "\n- blood\n- lens flares\n"
    o = parse_intent(STORY + label + body)
    assert "*" not in o["do_not"], f"'{label}' produced the do-not rule '*' (do_not={o['do_not']})"
    assert o["do_not"] == ["blood", "lens flares"], (
        f"'{label}' + bullets: do_not={o['do_not']}, notes={o['notes']}, summary={o['summary']!r}")


@pytest.mark.parametrize("label,field", [("**Story:**", "summary"), ("**Setting:**", "setting"), ("**Tone:**", "tone")])
def test_bold_colon_field_label_takes_the_text_below(label, field):
    text = ("## Intro\n\n" if field != "summary" else "") + f"{label}\nTwo keepers wait for a ship that never returns.\n"
    o = parse_intent(text)
    assert o[field] != "*", f"'{label}' on its own line gave {field} = '*'"
    assert o[field] and "Two keepers wait" in o[field], f"{field}={o[field]!r}"


def test_bold_colon_palette_label_takes_its_bullets():
    o = parse_intent("**Palette:**\n- night blue\n- rust red\n")
    assert o["palette_unparsed"] != ["*"], "'**Palette:**' gave the unparsed palette item '*'"
    assert o["palette_names"] == ["night blue", "rust red"], (
        f"palette={o['palette']} names={o['palette_names']} unparsed={o['palette_unparsed']} notes={o['notes']}")


def test_bold_colon_story_label_does_not_reach_brief_as_star():
    """End to end on the synthetic song: the logline the video agent reads first must not be '*'."""
    res = build(source(), "**Story:**\nTwo keepers wait for a ship that never returns.\n\n**Never show:**\n- blood\n",
                None, {})
    m = res["meaning"]
    assert m["logline"] != "*" and "*" not in (m.get("do_not") or []), (
        f"meaning.json logline={m['logline']!r} do_not={m.get('do_not')} (field_sources={m.get('field_sources')})")
    brief = brief_for(res)
    bad = [ln for ln in brief.splitlines() if ln.rstrip().endswith(": *") or ln.strip() in ("- *", "* *")]
    assert not bad, f"brief.md carries the '*' value: {bad[:3]}"
