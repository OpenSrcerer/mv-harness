"""R-WORDS round 5: answers to the interview's 'Who sings to whom?' question.

R5-2 (major, seam with voices). interview.md asks "Which character is each voice?". The natural answer is voice
first: ``V1 = C1 The Keeper`` (the very syntax of the viewer block, ``- V1 = C1 Name``), ``- V1 = C1 ...`` or
``V1 is C1, the Keeper``. The meaning grammar only reads character-first lines (``C1 The Keeper = V1``), so these
answers become notes (or, with no heading, the user's logline and summary) and no character gets a name or voice.
The voices stage reads the same file and DOES map them (``voices.intent._V_TO_C``), so voices and meaning disagree
on the user's own mapping.

R5-3 (major, regression from the R4-3 fix). Rule 0 drops whole interview lines it recognises as the harness's
(``_IV_ECHO``). A user who copies the interview and annotates each voice fact bullet
(``- **V1**: 19.8 s, 7 lines, ... -> C1 The Keeper``) or writes the answer after "Which character is each voice? ..."
on the same line loses that answer silently: not a character, not a note, no warning; status stays pending.

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
    "V1 = C1 The Keeper\nV2 = C2 The Child\n",
    "## Who sings\n- V1 = C1 The Keeper\n- V2 = C2 The Child\n",
    "## Who sings\nV1 is C1, the Keeper. V2 is C2, the Child.\n",
])
def test_voice_first_mapping_is_read_like_the_voices_stage(text):
    v2c = voices_parse(text)["voice_to_character"]
    assert v2c == {"V1": "C1", "V2": "C2"}  # the voices stage maps the user's answer
    o = parse_intent(text)
    got = {v: cid for cid, c in o["characters"].items() for v in c["voices"]}
    assert got == v2c, (f"meaning's parser maps {got} where voices maps {v2c} "
                        f"(notes={len(o['notes'])}, summary set={o['summary'] is not None})")


def test_voice_first_answer_is_not_the_logline():
    o = parse_intent("V1 = C1 The Keeper\nV2 = C2 The Child\n")
    assert o["logline"] is None or "V1" not in o["logline"], "a voice mapping became the user's logline"


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


def test_answer_appended_to_copied_voice_bullet_is_not_dropped_silently():
    qa = _interview_qa()
    assert re.search(r"(?m)^\s*- \*\*V1\*\*: ", qa), "fixture interview has no voice fact bullets"
    o = parse_intent(_answer_appended(qa))
    kept = bool(o["characters"]) or any("Keeper" in n for n in o["notes"]) or any("V1" in w for w in o["warnings"])
    assert kept, ("the user's '-> C1 The Keeper' on the copied V1 bullet vanished: "
                  f"characters={o['characters']}, notes={len(o['notes'])}, warnings={o['warnings']}")


def test_answer_on_which_character_line_is_not_dropped_silently():
    qa = _interview_qa()
    txt = "\n".join(ln + " C1 The Keeper sings V1, C2 The Child sings V2." if "Which character is each voice" in ln
                    else ln for ln in qa.splitlines())
    o = parse_intent(txt)
    kept = bool(o["characters"]) or any("Keeper" in n for n in o["notes"])
    assert kept, f"the answer typed after the question was dropped: characters={o['characters']}, notes={o['notes']}"


def test_appended_voice_answer_reaches_meaning():
    res = build(source(), _answer_appended(_interview_qa()), None, {})
    m = res["meaning"]
    names = [c.get("name") for c in m["characters"]]
    assert m["status"] != "pending" or "The Keeper" in names, (
        f"status={m['status']} names={names}: the user's voice answers were ignored without a trace")


def test_answer_under_a_copied_open_question_is_not_dropped_silently():
    """Same root (R5-3): every bullet under a copied '## Open questions' heading is dropped as the harness's, so the
    user's answer written as a sub-bullet (or typed after the question) vanishes with no note and no warning."""
    res = build(source(), None, authored(), {})
    iv = res["interview"]
    assert "## Open questions" in iv, "fixture interview has no open questions"
    oq = iv[iv.index("## Open questions"):iv.index("## Template")]
    txt = "\n".join((ln + "\n  - Yes: the keeper is the narrator.") if ln.startswith("- ") else ln
                    for ln in oq.splitlines())
    o = parse_intent(txt)
    assert any("narrator" in n for n in o["notes"]) or o["perspective"]["narrator"] or o["warnings"], (
        f"the user's sub-bullet answer vanished: notes={o['notes']}, perspective={o['perspective']}")
