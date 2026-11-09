"""R-WORDS M6b F1 (major): brief.md presents an agent/LLM draft's claims as the user's once the user has answered
anything at all.

PLAN §8.3/§8.4: a draft fills the gaps with ``status: draft`` and provenance on every claim; CONTRACT §12: the brief's
meaning block shows the logline, palette and per-section feel. The meaning stage records the per-field origin
(``meaning.json field_sources``, ``sections[].field_sources``), but brief.build only looks at the document-level
``status`` (logline) and at the section-level ``provenance.status`` (feel), which is ``user`` as soon as ONE field of
the section is the user's. So a draft logline / palette / section feel reaches the LLM entry point unlabelled, under a
``meaning: user`` status line.
"""
from __future__ import annotations

import re

from rw_m6b_support import authored, brief_for, source

from mvh.stages.meaning.stage import build


def _meaning_block(brief: str) -> str:
    m = re.search(r"## Meaning.*?(?=\n## )", brief, re.S)
    assert m, "brief has no meaning block"
    return m.group(0)


def test_draft_logline_is_labelled_when_the_user_answered_only_a_rule():
    # the user answered one question (a do-not rule); the agent's draft fills the logline and the palette
    res = build(source(), "## Never show\n- No text on screen.\n", authored(), {})
    m = res["meaning"]
    assert m["status"] == "user"
    assert m["field_sources"]["logline"] == "draft"  # the stage knows the logline is the draft's
    block = _meaning_block(brief_for(res))
    logline_line = next(ln for ln in block.splitlines() if m["logline"][:30] in ln)
    assert "draft" in logline_line.lower(), "a draft logline is shown as if the user wrote it"


def test_draft_palette_is_labelled_when_status_is_user():
    res = build(source(), "## Never show\n- No text on screen.\n", authored(), {})
    assert res["meaning"]["field_sources"]["palette"] == "draft"
    block = _meaning_block(brief_for(res))
    pal_line = next(ln for ln in block.splitlines() if ln.startswith("Palette"))
    assert "draft" in pal_line.lower(), "the draft's palette is shown as the user's palette"


def test_draft_section_feel_is_labelled_when_the_user_gave_another_field():
    # the user gave only a camera note for S02; the draft gives its feel
    intent = "```yaml\nsections:\n  S02: {t0: 9.0, t1: 17.0, camera: handheld}\n```\n"
    res = build(source(), intent, authored(), {})
    s2 = next(s for s in res["meaning"]["sections"] if s["section_id"] == "S02")
    assert s2["field_sources"]["feel"] == "draft" and s2["provenance"]["status"] == "user"
    brief = brief_for(res)
    row = next(ln for ln in brief.splitlines() if ln.startswith("| S02 "))
    assert "(draft)" in row, "the draft's feel for S02 is shown in the cue sheet as the user's"
