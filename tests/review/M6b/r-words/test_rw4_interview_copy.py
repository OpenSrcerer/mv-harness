"""R-WORDS round 4, R4-3 (major).

interview.md tells the user to "answer in meaning/intent.md (free text is fine ...)". Answering a questionnaire by
copying its questions and writing each answer under its question is the ordinary way to do that. When the user does,
the harness's own text becomes the user's claims at user precedence:
* the interview's preamble ("The harness found the facts below. ...") is under an H1 title, which grammar v2 reads
  as the summary and logline, so the user's real logline (the answer to question 1) is lost;
* question 8's text (with its example 'night blue') is parsed as a ``Colours:`` label and becomes user palette;
* the answer to question 9 (Never show) is folded into the numbered question bullet and kept only as a note, so the
  user's prohibitions are not do_not rules.
Pasting the interview untouched also turns status 'draft' into 'user' with a harness-written logline.

Synthetic fixture only (invented lyrics).
"""
from __future__ import annotations

from rw_m6b_support import authored, source

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
        if ln.startswith("9. **"):
            out.append("   " + ANSWER_9)
    return "\n".join(out) + "\n"


def test_answers_written_under_the_copied_questions_are_the_users_claims():
    m = build(source(), _qa_copy(_interview()), authored(), {})["meaning"]
    problems = []
    if m["logline"] != ANSWER_1.split(". ")[0] + ".":
        problems.append(f"logline is {m['logline']!r}, not the answer to question 1")
    if not any("blood" in r for r in m["do_not"]):
        problems.append(f"the answer to 'Never show' is not a do_not rule (do_not={m['do_not']})")
    if any("palette" in str(n).lower() and "night blue" in str(n) for n in m.get("palette_names") or []):
        problems.append("question 8's own text is a user palette entry")
    assert not problems, "; ".join(problems)


def test_untouched_copy_of_the_interview_is_not_a_user_answer():
    m = build(source(), _interview(), authored(), {})["meaning"]
    fs_user = sorted(k for k, v in (m.get("field_sources") or {}).items() if v == "user")
    assert m["status"] != "user" and not fs_user, (
        f"the untouched interview made status {m['status']!r} with user fields {fs_user} "
        f"(logline {m['logline']!r})")
