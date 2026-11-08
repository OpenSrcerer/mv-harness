# ruff: noqa: E501
"""R-WORDS M6b F3 and F4 (major): intent.md parsing turns things the user did NOT say into user claims.

F3: a "Never show" bullet addressed to a section ("- Chorus: never show the singers' faces.") is kept verbatim as a
do-not rule (good) but is ALSO parsed as a section note, so it becomes the user's ``feel`` for every chorus (the
free-text line loop in intent._parse_text runs _section_notes over every line, including the do-not block). The
brief's cue sheet and ``meaningAt(t).feel`` then carry the prohibition as the section's positive direction, at the
highest precedence (user).

F4: the YAML template that interview.md prints ("Empty = no answer") is prefilled with the harness's voice proposals and
a default ``lead_backing``. Pasting it into intent.md untouched therefore flips ``meaning.status`` from pending to
``user`` and stamps the proposed characters and voice mappings as user-confirmed, so the SKILL rule (pending + empty
intent -> show the interview and wait) no longer fires and the brief claims the user authored the meaning.
"""
from __future__ import annotations

from rw_m6b_support import source

from mvh.stages.meaning.stage import build

NEVER = "## Never show\n- Chorus: never show the singers' faces.\n- Drop: no confetti, no fireworks.\n"


def test_section_addressed_do_not_rule_is_not_a_feel():
    res = build(source(), NEVER, None, {})
    assert "Chorus: never show the singers' faces." in res["meaning"]["do_not"]  # verbatim rule: fine
    feels = {s["section_id"]: s["feel"] for s in res["meaning"]["sections"] if s["feel"]}
    assert not feels, f"do-not rules became section feels (user claims): {sorted(feels)}"


def _template(res: dict) -> str:
    iv = res["interview"]
    a = iv.index("```yaml")
    b = iv.index("```", a + 7)
    return iv[a:b + 3] + "\n"


def test_untouched_template_is_not_a_user_answer():
    pending = build(source(), None, None, {})
    assert pending["meaning"]["status"] == "pending"
    res = build(source(), _template(pending), None, {})
    assert res["meaning"]["status"] == "pending", (
        f"pasting the empty template made the meaning status {res['meaning']['status']!r}")


def test_untouched_template_does_not_confirm_voice_proposals():
    pending = build(source(), None, None, {})
    res = build(source(), _template(pending), None, {})
    confirmed = {c["id"]: c["voice_mapping"] for c in res["characters"]
                 if c["provenance"]["status"] == "user" or "user" in c["voice_mapping"].values()}
    assert not confirmed, f"harness proposals became user-confirmed mappings: {confirmed}"
