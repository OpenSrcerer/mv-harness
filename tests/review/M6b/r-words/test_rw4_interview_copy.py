"""R-WORDS round 4, R4-3 (major).

interview.md tells the user to answer in meaning/intent.md. Answering a questionnaire by copying its questions and
writing each answer under its question is the ordinary way to do that. When the user did, the harness's own text
became the user's claims at user precedence (the preamble became the logline, question 8's example 'night blue'
became a user colour) and pasting the interview untouched turned status 'draft' into 'user'.

Rewritten by ud1-meaning for user decision UD1 (W4): free text, including answers written under copied questions, is
the user's notes (verbatim, user-authored), never fields or rules. The finding's intent is checked under that rule:
the harness's text is never the user's, each answer is kept verbatim headed by its question, nothing is a user field
or rule, and an untouched copy answers nothing.

Synthetic fixture only (invented lyrics).
"""
from __future__ import annotations

from rw_m6b_support import authored, brief_for, source

from mvh.stages.meaning.stage import build

ANSWER_1 = "Two lighthouse keepers wait for a ship that never returns. It is about grief."
ANSWER_9 = "No blood. No faces in close-up."


def _interview() -> str:
    return build(source(), None, authored(), {})["interview"]


def _qa_copy(iv: str) -> str:
    qa = iv[:iv.index("## Open questions")]
    out = []
    for ln in qa.splitlines():
        out.append(ln)
        if ln.startswith("1. **"):
            out.append("   " + ANSWER_1)
        if "**Never show**" in ln:
            out.append("   " + ANSWER_9)
    return "\n".join(out) + "\n"


def test_answers_written_under_the_copied_questions_are_the_users_notes():
    res = build(source(), _qa_copy(_interview()), authored(), {})
    m = res["meaning"]
    fs_user = sorted(k for k, v in m["field_sources"].items() if v == "user")
    assert m["status"] == "user" and fs_user == ["notes"], (m["status"], fs_user)
    assert m["notes"] == ["## What does this song mean to you?\n   " + ANSWER_1, "## Never show\n   " + ANSWER_9], m["notes"]
    assert m["do_not"] == [] and m["field_sources"]["logline"] == "draft"  # free text never fills a field
    assert not any("night blue" in str(n) for n in m.get("palette_names") or [])
    assert any("never obeyed as a rule" in q for q in m["open_questions"])
    brief = brief_for(res)
    assert "lighthouse keepers" in brief and "never rules" in brief


def test_untouched_copy_of_the_interview_is_not_a_user_answer():
    m = build(source(), _interview(), authored(), {})["meaning"]
    fs_user = sorted(k for k, v in (m.get("field_sources") or {}).items() if v == "user")
    assert m["status"] != "user" and not fs_user and not m["notes"], (
        f"the untouched interview made status {m['status']!r} with user fields {fs_user} (notes {len(m['notes'])})")
