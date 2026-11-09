"""R-WORDS M6b round 2: intent.md parsing findings that the round-1 fixes did not close (or reopened).

N1 (F4 reopened, major): the fix comments out the harness's voice proposals and skips empty character entries, but
when the song has NO characters (no voices: instrumental songs, and real-megafauna / real-versatile in tests/contract)
the template's placeholder line is ``C1: {name: "", description: "", voices: [], lead_backing: lead}``. ``lead`` is a
prefilled non-empty value, so pasting the untouched template ("Empty = no answer") creates a user character C1 and
flips meaning.status from pending to user.

N2 (F3 reopened, major): the do-not fix only skips blocks under a markdown ``#`` heading. The interview asks the
question as ``**Never show**: what must never appear on screen?``; a user who answers with that bold label (or a
``Never show: ...`` line, or a ``## Don'ts`` heading) gets no do_not rule at all, and the prohibition becomes the
chorus feel (bold label / Don'ts) or the logline (single line), at user precedence.

N3 (r-contract F3 partially fixed, major): the unfenced template is parsed as YAML only when the WHOLE file parses.
A user who pastes the template without the fence and adds one markdown note after it (natural) falls back to free
text: the template's do_not rule is lost, every character is named ``{name`` and every section's feel becomes the
template comment (``# intro#1 0:01.0-0:09.0``); status user. Only a generic warning was added.

N4 (regression introduced by the F3 fix, major): ``_looks_like_template`` treats any file whose first line starts
with a lowercase template key as the unfenced template. A free-text answer such as ``palette: night blue, #f2a541,
rust red`` followed by section notes (``chorus: ...``) parses as YAML: ``#f2a541, rust red`` becomes a YAML comment
(two of three colours lost) and the section notes are unknown YAML keys (dropped). No warning. The same file with
``Logline:`` capitalised keeps all of it (free text).
"""
from __future__ import annotations

import json

import pytest
from rw_m6b_support import ROOT, source

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import build


def _template(res: dict) -> str:
    iv = res["interview"]
    a = iv.index("```yaml")
    b = iv.index("```", a + 7)
    return iv[a:b + 3] + "\n"


# ------------------------------------------------------------------------------------------------ N1
def _no_voice_source():
    # a song with no lyrics and no voices (instrumental): the meaning stage has no characters to list
    return source({"lyrics/lyrics.json": None, "meta/voices.json": {"voices": []}}, {"voice_spans": []})


def test_untouched_template_of_a_song_without_characters_is_not_an_answer():
    pending = build(_no_voice_source(), None, None, {})
    assert pending["meaning"]["status"] == "pending" and not pending["characters"]
    res = build(_no_voice_source(), _template(pending), None, {})
    assert res["meaning"]["status"] == "pending", (
        f"pasting the untouched template made the status {res['meaning']['status']!r}; user characters: "
        f"{[c['id'] for c in res['characters'] if c['provenance']['status'] == 'user']}")


@pytest.mark.parametrize("slug", ["megafauna", "versatile"])
def test_untouched_template_of_a_real_instrumental_fixture_is_not_an_answer(slug):
    import rw_m6b_support as S

    d = ROOT / "tests" / "contract" / f"real-{slug}"
    if not (d / ".done.json").is_file() and not (d / "manifest.json").is_file():
        pytest.skip(f"tests/contract/real-{slug} is not built")

    def load(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    files = {r: load(d / r) for r in S.FILES if (d / r).is_file()}
    ev = {n: load(d / "events" / f"{n}.json")["items"] for n in S.EVENTS if (d / "events" / f"{n}.json").is_file()}
    pending = build(S.DictSource(files, ev), None, None, {})
    assert pending["meaning"]["status"] == "pending"
    res = build(S.DictSource(files, ev), _template(pending), None, {})
    assert res["meaning"]["status"] == "pending", f"real-{slug}: untouched template -> status {res['meaning']['status']!r}"


# ------------------------------------------------------------------------------------------------ N2
def test_bold_never_show_label_from_the_interview_is_a_rule_not_a_feel():
    # the interview prints the question as '**Never show**: ...'; the user mirrors that label
    o = parse_intent("**Never show**\n- Chorus: never show the singers' faces.\n")
    feels = [(s["key"], s["feel"]) for s in o["sections"]]
    assert o["do_not"], "the user's Never-show rule was not recognised as a do_not rule"
    assert not feels, f"the prohibition became a section feel: {feels}"


def test_single_line_never_show_answer_is_a_rule_not_the_logline():
    o = parse_intent("Never show: the singers' faces in the chorus.\n")
    assert o["do_not"], "a 'Never show: ...' answer was not recognised as a do_not rule"
    assert not (o["logline"] or "").lower().startswith("never show"), "the prohibition became the user's logline"


def test_donts_heading_is_a_do_not_block():
    o = parse_intent("## Don'ts\n- Chorus: never show the singers' faces.\n")
    assert o["do_not"] and not o["sections"], (
        f"'## Don'ts' is not read as a do-not block: do_not={len(o['do_not'])}, feels={[s['key'] for s in o['sections']]}")


# ------------------------------------------------------------------------------------------------ N3
def _filled_unfenced_template() -> str:
    pending = build(source(), None, None, {})
    t = _template(pending)
    body = t[len("```yaml\n"):t.rindex("```")]
    body = body.replace('C2: {name: ""', 'C2: {name: "The Tide"')
    body = body.replace("do_not:   # rules in your own words; copied verbatim to every agent", "do_not:\n  - No text on screen.")
    assert "The Tide" in body and "No text on screen." in body
    return body


def test_unfenced_template_followed_by_a_markdown_note_keeps_the_template_answers():
    txt = _filled_unfenced_template() + "\n## Never show\n- No confetti.\n"
    o = parse_intent(txt)
    bad_names = {k: v["name"] for k, v in o["characters"].items() if str(v.get("name") or "").startswith("{")}
    comment_feels = [s["key"] for s in o["sections"] if str(s.get("feel") or "").startswith("#")]
    assert "No text on screen." in o["do_not"], "the do_not rule written in the template was dropped"
    assert not bad_names, f"YAML syntax became character names: {sorted(bad_names)}"
    assert not comment_feels, f"template comments became the user's feel for {len(comment_feels)} section(s)"


# ------------------------------------------------------------------------------------------------ N4
FREE = ("logline: two lovers on opposite banks\n"
        "palette: night blue, #f2a541, rust red\n"
        "chorus: lanterns rise over the water\n"
        "drop: strobes and white light\n")


def test_lowercase_free_text_answers_are_not_lost_as_yaml():
    cap = parse_intent(FREE.replace("logline:", "Logline:", 1))  # same answers, read as free text
    low = parse_intent(FREE)
    assert len(cap["palette"]) == 3 and {s["key"] for s in cap["sections"]} == {"chorus", "drop"}  # control
    lost = []
    if len(low["palette"]) < 3:
        lost.append(f"palette {len(low['palette'])}/3 colours")
    if {s["key"] for s in low["sections"]} != {"chorus", "drop"}:
        lost.append(f"section notes {sorted(s['key'] for s in low['sections'])}")
    assert not lost or low["warnings"], f"answers silently lost when the first key is lowercase: {lost}"
