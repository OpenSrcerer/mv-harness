"""R-WORDS round 5: answers to the interview's 'Who sings to whom?' question.

R5-2 (major, seam with voices). The natural answer is voice first (``V1 = C1 The Keeper``, the viewer block's own
syntax). The meaning grammar read only character-first lines while the voices stage mapped voice-first ones, so
voices and meaning disagreed on the user's own mapping.

R5-3 (major). A user who copied the interview and annotated a voice fact bullet (``- **V1**: 19.8 s, ... -> C1 The
Keeper``) or wrote the answer after "Which character is each voice? ..." lost that answer silently.

Rewritten by ud1-meaning for user decision UD1 (W4). One parser serves both stages and the template is the only
source of a voice mapping: ``voices:`` takes the voice-first form (``- V1 = C1 The Keeper``, ``V1: C1 The Keeper``),
and voices and meaning map it identically. The same lines in free text are a note in BOTH stages (they still agree).
Answers typed into a copied interview are kept verbatim as notes, never silently dropped.

Synthetic fixture only (invented lyrics); nothing real is printed.
"""
from __future__ import annotations

import re

import pytest
from rw_m6b_support import authored, source

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build
from mvh.stages.voices.intent import parse_intent as voices_parse


@pytest.mark.parametrize("text", [
    "voices:\n- V1 = C1 The Keeper\n- V2 = C2 The Child\n",
    "voices:\n  V1: C1 The Keeper\n  V2: C2 The Child\n",
    "```yaml\nvoices:\n  - V1 = C1 The Keeper\n  - V2 = C2 The Child\n```\n",
    "## Who sings\nvoices:\n- V1 is C1, the Keeper\n- V2 -> C2 The Child\n",
])
def test_voice_first_mapping_in_the_template_is_read_like_the_voices_stage(text):
    v2c = voices_parse(text)["voice_to_character"]
    assert v2c == {"V1": "C1", "V2": "C2"}
    o = parse_intent(text)
    got = {v: cid for cid, c in o["characters"].items() for v in c["voices"]}
    assert got == v2c and o["characters"]["C1"]["name"] in ("The Keeper", "the Keeper"), o["characters"]
    assert o["logline"] is None


@pytest.mark.parametrize("text", [
    "V1 = C1 The Keeper\nV2 = C2 The Child\n",
    "## Who sings\n- V1 = C1 The Keeper\n- V2 = C2 The Child\n",
    "## Who sings\nV1 is C1, the Keeper. V2 is C2, the Child.\n",
])
def test_voice_first_mapping_in_free_text_is_a_note_in_both_stages(text):
    assert voices_parse(text)["voice_to_character"] == {}
    o = parse_intent(text)
    assert o["characters"] == {} and o["notes"] == [text.strip()] and o["logline"] is None


def _interview_qa() -> str:
    res = build(source(), None, authored(), {})
    iv = res["interview"]
    return iv[:iv.index("## Template")]


def _answer_appended(qa: str) -> str:
    out = []
    for ln in qa.splitlines():
        if re.match(r"\s*- \*\*V1\*\*: ", ln):
            ln += " -> C1 The Keeper"
        elif re.match(r"\s*- \*\*V2\*\*: ", ln):
            ln += " -> C2 The Child"
        out.append(ln)
    return "\n".join(out)


def test_answer_appended_to_copied_voice_bullet_is_kept():
    qa = _interview_qa()
    assert re.search(r"(?m)^\s*- \*\*V1\*\*: ", qa), "fixture interview has no voice fact bullets"
    o = parse_intent(_answer_appended(qa))
    assert len(o["notes"]) == 1 and "- V1: -> C1 The Keeper" in o["notes"][0] and "- V2: -> C2 The Child" in o["notes"][0]
    assert o["notes"][0].startswith("## Who sings to whom?")


def test_answer_on_which_character_line_is_kept():
    qa = _interview_qa()
    txt = "\n".join(ln + " C1 The Keeper sings V1, C2 The Child sings V2." if "Which character is each voice" in ln
                    else ln for ln in qa.splitlines())
    o = parse_intent(txt)
    assert any("C1 The Keeper sings V1, C2 The Child sings V2." in n for n in o["notes"]), o["notes"]


def test_appended_voice_answer_reaches_meaning_as_a_user_note():
    m = build(source(), _answer_appended(_interview_qa()), None, {})["meaning"]
    assert m["status"] == "user" and m["field_sources"].get("notes") == "user"
    assert any("C1 The Keeper" in n for n in m["notes"])


def test_answer_under_a_copied_open_question_is_kept():
    res = build(source(), None, authored(), {})
    iv = res["interview"]
    assert "## Open questions" in iv, "fixture interview has no open questions"
    oq = iv[iv.index("## Open questions"):iv.index("## Template")]
    txt = "\n".join((ln + "\n  - Yes: the keeper is the narrator.") if ln.startswith("- ") else ln
                    for ln in oq.splitlines())
    o = parse_intent(txt)
    assert any("Yes: the keeper is the narrator." in n for n in o["notes"]), o["notes"]
    assert o["perspective"]["narrator"] is None  # a note, never a field
