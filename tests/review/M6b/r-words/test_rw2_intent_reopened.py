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

UD1 (W4, user decision): the interview template is the only source of fields and do-not rules; free text is the
user's notes, kept verbatim, never parsed. N1 and N3 stand as written; N2 and N4 are restated under that rule.
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


# ------------------------------------------------------------------------------------------------ N2 (UD1)
# Rewritten by ud1-meaning (W4, user decision UD1). N2 asked that a prohibition never become a section feel or the
# logline. Under UD1 free text is never parsed at all: the answer is kept verbatim as the user's note, it is not a
# do-not rule (only the template's do_not is), and the meaning stage asks the user to move it into the template.
@pytest.mark.parametrize("text", [
    "**Never show**\n- Chorus: never show the singers' faces.\n",
    "Never show: the singers' faces in the chorus.\n",
    "## Don'ts\n- Chorus: never show the singers' faces.\n",
])
def test_never_show_answer_in_free_text_is_a_note_never_a_feel_or_logline(text):
    o = parse_intent(text)
    assert o["notes"] == [text.strip()], o["notes"]
    assert o["do_not"] == [] and o["sections"] == [] and o["logline"] is None and o["summary"] is None
    m = build(source(), text, None, {})["meaning"]
    assert any("never obeyed as a rule" in q for q in m["open_questions"]), m["open_questions"]


def test_never_show_answer_in_the_template_is_a_rule_not_a_feel():
    o = parse_intent("do_not:\n  - \"Chorus: never show the singers' faces.\"\n")
    assert o["do_not"] == ["Chorus: never show the singers' faces."] and o["sections"] == [] and not o["notes"]


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


# ------------------------------------------------------------------------------------------------ N4 (UD1)
FREE = ("logline: two lovers on opposite banks\n"
        "palette: night blue, #f2a541, rust red\n"
        "chorus: lanterns rise over the water\n"
        "drop: strobes and white light\n")


def test_lowercase_template_keys_keep_every_answer():
    """Rewritten for UD1: ``logline:`` / ``palette:`` (column 0, lower case) are the unfenced template and keep all three
    colours; ``chorus:`` / ``drop:`` are not template keys, so those lines are free text, kept verbatim as one note
    (never section feels, never lost). The capitalised ``Logline:`` line is free text too."""
    low = parse_intent(FREE)
    assert low["logline"] == "two lovers on opposite banks" and len(low["palette"]) == 3, low
    assert low["notes"] == ["chorus: lanterns rise over the water\ndrop: strobes and white light"] and not low["sections"]
    cap = parse_intent(FREE.replace("logline:", "Logline:", 1))
    assert cap["logline"] is None and cap["notes"][0] == "Logline: two lovers on opposite banks"
    assert len(cap["palette"]) == 3  # 'palette:' still starts a template region
