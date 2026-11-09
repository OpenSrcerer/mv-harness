"""Intent grammar (meaning/intent.py, mvh-intent v2, UD1): the interview copied into intent.md, template keys answered
with bullets, and the template's hint comments.

* a copy of interview.md: the harness's own lines are never the user's; the user's answers (under a question, after
  it on the same line, after a voice fact, under an open question) are kept verbatim as notes, headed by the question
  they answer; an untouched copy answers nothing; nothing in it becomes a field or a rule (every song shape x answer
  layout x copy extent);
* map keys of the template answered with bullets (``characters:`` + ``- C1 ...``);
* the template's hint comments are comments whatever the spacing before them, and the interview's questions and the
  template's hints stay in sync with the parser.
Synthetic fixture only (invented lyrics)."""
from __future__ import annotations

import itertools
import re
from typing import Any

import pytest

from mvh.stages.meaning.intent import TEMPLATE_HINTS, free_text_notes, parse_intent
from mvh.stages.meaning.interview_text import OBEY
from mvh.stages.meaning.stage import build

SHAPES = {
    "synth": {},
    "no_voices": {"files": {"meta/voices.json": None}, "events": {"voice_spans": []}},
    "instrumental": {"files": {"meta/voices.json": None, "lyrics/lyrics.json": None}, "events": {"voice_spans": []}},
}
ANSWERS = {  # question title -> answer text
    "What does this song mean to you?": "Two keepers wait for a ship. It is about grief.",
    "The world": "A harbour town in 1920, one long night.",
    "Colours": "#c93523, rust red",
    "Never show": "No blood on screen.",
}
QUESTION_HEAD = {"What does this song mean to you?": r"1\. \*\*What does this song mean to you\?\*\*",
                 "The world": r"\d+\. \*\*The world\*\*",
                 "Colours": r"\d+\. \*\*Colours\*\*",
                 "Never show": r"\d+\. \*\*Never show\*\*"}
LAYOUTS = {
    "indented": lambda q, a: [q, "   " + a],
    "flush": lambda q, a: [q, a],
    "blank_between": lambda q, a: [q, "", a],
    "inline": lambda q, a: [q + " " + a],
    "bullet_answer": lambda q, a: [q, "   - " + a],
}
HARNESS = ("harness found", "voice(s) were found", "Credits found", "meaning status", "night blue", "draft asks",
           "Which character is each voice", "What should happen", "mood arc", "Already answered", "Template (copy",
           "Interview:", "copied verbatim", "where and when")


def _src(synth_source, shape):
    return synth_source(**SHAPES[shape])


def _interview(synth_source, shape, authored=None) -> str:
    return build(_src(synth_source, shape), None, authored, {})["interview"]


def _answered(iv: str, layout: str, whole: bool) -> str:
    text = iv if whole else iv[:iv.index("## Template")]
    out: list[str] = []
    for ln in text.splitlines():
        hit = next((t for t, rx in QUESTION_HEAD.items() if re.match(rx, ln)), None)
        out.extend(LAYOUTS[layout](ln, ANSWERS[hit]) if hit else [ln])
    return "\n".join(out) + "\n"


def _user_fields(m: dict[str, Any]) -> list[str]:
    return sorted(k for k, v in (m.get("field_sources") or {}).items() if v == "user")


# ------------------------------------------------------------------------------------------------ interview copy
@pytest.mark.parametrize("shape,layout,whole", list(itertools.product(sorted(SHAPES), sorted(LAYOUTS), [False, True])))
def test_answers_under_copied_questions_are_notes_headed_by_their_question(synth_source, synth_authored, shape, layout,
                                                                           whole):
    iv = _interview(synth_source, shape, synth_authored)
    r = build(_src(synth_source, shape), _answered(iv, layout, whole), synth_authored, {})
    m, it = r["meaning"], r["intent"]
    assert m["status"] == "user" and _user_fields(m) == ["notes"]
    assert len(m["notes"]) == 4, m["notes"]
    for title, answer in ANSWERS.items():
        note = next(n for n in m["notes"] if answer in n)  # every answer, verbatim
        assert note.startswith("## " + title), note  # headed by the question it answers
    # free text is never a field or a rule: the draft fills the fields, the do-not list stays the user's (empty)
    assert m["do_not"] == [] and m["field_sources"].get("logline") == "draft"
    assert any("never obeyed as a rule" in q for q in m["open_questions"])  # 'Never show' answered in free text
    # none of the harness's own text became a note
    assert not [n for n in m["notes"] if any(h in n for h in HARNESS)], m["notes"]
    assert not it["line_singers"] and not it["characters"] and not it["sections"], it
    assert not it["warnings"], it["warnings"]


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("authored", [False, True])
@pytest.mark.parametrize("cut", ["whole", "questions", "no_template_fence"])
def test_untouched_interview_copy_answers_nothing(synth_source, synth_authored, shape, authored, cut):
    a = synth_authored if authored else None
    iv = _interview(synth_source, shape, a)
    text = {"whole": iv, "questions": iv[:iv.index("## Template")],
            "no_template_fence": "\n".join(ln for ln in iv.splitlines() if not ln.startswith("```")) + "\n"}[cut]
    r = build(_src(synth_source, shape), text, a, {})
    m = r["meaning"]
    assert m["status"] == ("draft" if authored else "pending") and not _user_fields(m), (m["status"], _user_fields(m))
    assert not r["intent"]["notes"] and not r["intent"]["do_not"], r["intent"]["notes"]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_interview_line_is_known_to_the_parser(synth_source, synth_authored, shape):
    """Sync guard: every line docs.interview_md writes outside the template is the harness's (no note), and each
    numbered question becomes only the heading of an answer."""
    iv = _interview(synth_source, shape, synth_authored)
    qa = iv[:iv.index("```yaml")]
    assert free_text_notes(qa.splitlines()) == []
    qs = [ln for ln in iv.splitlines() if re.match(r"\d+\. ", ln)]
    assert qs
    for q in qs:
        notes = free_text_notes([q, "an answer"])
        assert len(notes) == 1 and notes[0].startswith("## ") and notes[0].endswith("\nan answer"), (q[:60], notes)


def test_interview_and_template_say_what_must_be_obeyed(synth_source):
    iv = _interview(synth_source, "synth")
    assert OBEY in iv and "free text is never a rule" in iv
    t = iv[iv.index("```yaml"):]
    assert "Anything that must be obeyed goes here" in t


def _voice_answers(iv: str) -> str:
    out = []
    for ln in iv[:iv.index("## Template")].splitlines():
        if re.match(r"\s*- \*\*V1\*\*: ", ln):
            ln += " -> C1 The Keeper"
        elif "Which character is each voice" in ln:
            ln += " C2 The Child sings V2."
        out.append(ln)
    return "\n".join(out) + "\n"


def test_answers_appended_to_copied_voice_lines_are_kept(synth_source):
    r = parse_intent(_voice_answers(_interview(synth_source, "synth")))
    assert r["characters"] == {} and len(r["notes"]) == 1
    note = r["notes"][0]
    assert note.startswith("## Who sings to whom?") and "- V1: -> C1 The Keeper" in note
    assert "C2 The Child sings V2." in note and "first heard" not in note


def test_answer_under_a_copied_open_question_is_kept(synth_source, synth_authored):
    iv = _interview(synth_source, "synth", synth_authored)
    oq = iv[iv.index("## Open questions"):iv.index("## Template")]
    first = next(ln for ln in oq.splitlines() if ln.startswith("- "))
    txt = oq.replace(first, first + "\n  - Yes: the keeper is the narrator.", 1)
    r = parse_intent(txt)
    assert r["notes"] == ["## Open questions\n" + first + "\n  - Yes: the keeper is the narrator."]
    assert r["perspective"]["narrator"] is None


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_interview_answers_round_trip_through_the_template(synth_source, layout):
    from test_intent_grammar import _template, _user_claims

    iv = _interview(synth_source, "synth")
    first = build(_src(synth_source, "synth"), _answered(iv, layout, False), None, {})
    t1 = _template(first)
    again = build(_src(synth_source, "synth"), t1, None, {})
    assert _user_claims(again) == _user_claims(first) and _template(again) == t1
    assert not again["intent"]["warnings"]


# ------------------------------------------------------------------------------------------------ keys with bullets
KEY_LISTS = {
    "characters": ("characters:\n- C1 The Keeper = V1 (the low voice). Lead.\n- C2: The Tide = V2\n",
                   lambda o: {k: (c["name"], c["voices"]) for k, c in o["characters"].items()}
                   == {"C1": ("The Keeper", ["V1"]), "C2": ("The Tide", ["V2"])}),
    "voices": ("voices:\n- V1 = C1 The Keeper\n- V2 = C2 The Tide\n",
               lambda o: {k: (c["name"], c["voices"]) for k, c in o["characters"].items()}
               == {"C1": ("The Keeper", ["V1"]), "C2": ("The Tide", ["V2"])}),
    "sections": ("sections:\n- Chorus: wide shots, slow.\n- S03: fog\n",
                 lambda o: {(s["key"], s["feel"]) for s in o["sections"]} == {("chorus", "wide shots, slow"), ("S03", "fog")}),
    "line_singers": ("line_singers:\n- L005: C1+C2\n- L006 = C2\n",
                     lambda o: o["line_singers"] == {"L005": ["C1", "C2"], "L006": ["C2"]}),
    "perspective": ("perspective:\n- narrator: C1\n- addressee: the sea\n",
                    lambda o: o["perspective"] == {"narrator": "C1", "addressee": "the sea"}),
}
KEY_WRAPS = {
    "col0": (lambda t: t, []),
    "indented": (lambda t: re.sub(r"(?m)^- ", "  - ", t), []),
    "fenced": (lambda t: "```yaml\n" + t + "```\n", []),
    "after_story": (lambda t: "Two keepers wait for a ship.\n\n" + t, ["Two keepers wait for a ship."]),
    "before_note": (lambda t: t + "\n## Notes\nKeep it quiet.\n", ["## Notes\nKeep it quiet."]),
}


@pytest.mark.parametrize("key,wrap", list(itertools.product(sorted(KEY_LISTS), sorted(KEY_WRAPS))))
def test_map_keys_answered_with_bullets(key, wrap):
    text, ok = KEY_LISTS[key]
    add, notes = KEY_WRAPS[wrap]
    o = parse_intent(add(text))
    assert ok(o), o
    assert o["notes"] == notes
    assert not o["warnings"], o["warnings"]


def test_unknown_bullet_under_a_map_key_is_kept_and_warned():
    o = parse_intent("characters:\n- somebody in a coat\n- C1 Ann = V1\n")
    assert o["characters"]["C1"]["name"] == "Ann" and "somebody in a coat" in o["notes"]
    assert any("characters" in w for w in o["warnings"])


# ------------------------------------------------------------------------------------------------ template hints
def test_template_hint_comments_are_known(synth_source):
    from test_intent_grammar import _template

    t = _template(build(_src(synth_source, "synth"), None, None, {}))
    for ln in t.splitlines():
        m = re.search(r"\s(#\s.*)$", ln)
        if not m or ln.lstrip().startswith("#") or re.match(r"\s+S\d{2,}:", ln):
            continue
        assert m.group(1).startswith(TEMPLATE_HINTS), ln


@pytest.mark.parametrize("spaces", [" ", "  ", "\t"])
@pytest.mark.parametrize("wrap", ["fenced", "unfenced"])
def test_hint_after_a_typed_value_is_a_comment_whatever_the_spacing(spaces, wrap):
    body = (f"palette: #c93523{spaces}# hex (#1b2a49) or colour words (night blue)\n"
            f"line_singers:{spaces}# optional per-line fixes, lead first: {{L005: C1+C2}}\n  L006: C2\n"
            f"voices: 2{spaces}# which character sings each voice (V1: C1 Name), or the number of singers\n"
            f"do_not:{spaces}# rules in your own words; copied verbatim to every agent\n  - no fire\n")
    o = parse_intent("```yaml\n" + body + "```\n" if wrap == "fenced" else body)
    assert o["palette"] == ["#c93523"] and o["line_singers"] == {"L006": ["C2"]} and o["do_not"] == ["no fire"]
    assert o["n_voices"] == 2
    assert not o["notes"] and not o["warnings"]
