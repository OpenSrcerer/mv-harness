"""Intent grammar v3 (meaning/intent.py): property-style checks over the ways a user answers that v2 missed.

* rule 0: the user copies interview.md and answers under its questions (every song shape x answer layout x copy extent);
* map keys answered with bullets (``characters:`` + ``- C1 ...``);
* do-not heading vocabulary and bulleted / numbered do-not labels;
* the template's hint comments are comments whatever the spacing before them;
* the interview's questions and the template's hints stay in sync with the parser.
Synthetic fixture only (invented lyrics)."""
from __future__ import annotations

import itertools
import re
from typing import Any

import pytest

from mvh.stages.meaning.intent import TEMPLATE_HINTS, _interview_echo, parse_intent
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


# ------------------------------------------------------------------------------------------------ rule 0
@pytest.mark.parametrize("shape,layout,whole", list(itertools.product(sorted(SHAPES), sorted(LAYOUTS), [False, True])))
def test_answers_under_copied_questions_are_the_claims(synth_source, synth_authored, shape, layout, whole):
    iv = _interview(synth_source, shape, synth_authored)
    r = build(_src(synth_source, shape), _answered(iv, layout, whole), synth_authored, {})
    m, it = r["meaning"], r["intent"]
    assert m["status"] == "user"
    assert m["logline"] == "Two keepers wait for a ship." and m["field_sources"]["logline"] == "user"
    assert m["summary"] == ANSWERS["What does this song mean to you?"]
    assert m["setting"] == ANSWERS["The world"]
    assert m["palette"][0] == "#c93523" and len(m["palette"]) == 2 and not it["palette_unparsed"]
    assert any("No blood on screen." in r_ for r_ in m["do_not"]) and len(m["do_not"]) == 1
    # none of the harness's own text became a claim
    harness = ("harness found", "voice(s) were found", "Credits found", "meaning status", "night blue", "draft asks",
               "Which character is each voice", "What should happen", "mood arc")
    claims = [str(x) for x in it["notes"] + it["do_not"] + it["palette_names"]] + [str(it["summary"])]
    assert not [c for c in claims if any(h in c for h in harness)], claims
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
    assert not r["intent"]["notes"] and not r["intent"]["do_not"]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_interview_question_is_known_to_the_parser(synth_source, synth_authored, shape):
    """Sync guard: docs.interview_md's numbered questions must all be rule-0 questions in intent.py."""
    iv = _interview(synth_source, shape, synth_authored)
    qs = [ln for ln in iv.splitlines() if re.match(r"\d+\. ", ln)]
    assert qs
    for q in qs:
        got = _interview_echo([(0, q)])
        assert got[0][1].startswith("## ") and len(got) == 1, (q[:60], got)


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
    "sections": ("sections:\n- Chorus: wide shots, slow.\n- S03: fog\n",
                 lambda o: {(s["key"], s["feel"]) for s in o["sections"]} == {("chorus", "wide shots, slow"), ("S03", "fog")}),
    "line_singers": ("line_singers:\n- L005: C1+C2\n- L006 = C2\n",
                     lambda o: o["line_singers"] == {"L005": ["C1", "C2"], "L006": ["C2"]}),
    "perspective": ("perspective:\n- narrator: C1\n- addressee: the sea\n",
                    lambda o: o["perspective"] == {"narrator": "C1", "addressee": "the sea"}),
}
KEY_WRAPS = {
    "col0": lambda t: t,
    "indented": lambda t: re.sub(r"(?m)^- ", "  - ", t),
    "fenced": lambda t: "```yaml\n" + t + "```\n",
    "after_story": lambda t: "Two keepers wait for a ship.\n\n" + t,
    "before_note": lambda t: t + "\n## Notes\nKeep it quiet.\n",
}


@pytest.mark.parametrize("key,wrap", list(itertools.product(sorted(KEY_LISTS), sorted(KEY_WRAPS))))
def test_map_keys_answered_with_bullets(key, wrap):
    text, ok = KEY_LISTS[key]
    o = parse_intent(KEY_WRAPS[wrap](text))
    assert ok(o), o
    assert not o["warnings"], o["warnings"]


def test_unknown_bullet_under_a_map_key_is_kept_and_warned():
    o = parse_intent("characters:\n- somebody in a coat\n- C1 Ann = V1\n")
    assert o["characters"]["C1"]["name"] == "Ann" and "somebody in a coat" in o["notes"]
    assert any("characters" in w for w in o["warnings"])


# ------------------------------------------------------------------------------------------------ do-not recall
STORY = "## The story\nTwo keepers wait.\n\n"


@pytest.mark.parametrize("heading", ["What I don't want", "Avoid these", "Things I never want to see", "Never show these",
                                     "What not to show", "No-gos", "Things we must not show", "Don’t show"])
def test_do_not_heading_vocabulary(heading):
    o = parse_intent(STORY + f"## {heading}\n- blood\n- lens flares\n")
    assert o["do_not"] == ["blood", "lens flares"] and o["logline"] == "Two keepers wait."


@pytest.mark.parametrize("heading", ["Never Let Me Go", "Don't Stop Me Now: my notes", "Never Again", "Avoiding the obvious",
                                     "Things to do", "What I want", "The story: a night that never ends"])
def test_titles_with_do_not_words_are_not_do_not_headings(heading):
    o = parse_intent(f"## {heading}\nA keeper waits.\n\n- Chorus: wide\n")
    assert o["do_not"] == [] and {s["key"] for s in o["sections"]} == {"chorus"}


@pytest.mark.parametrize("line", ["- Never show: blood", "* **Never show**: blood", "9. **Never show**: blood",
                                  "- Avoid: blood", "1) Do not: blood", "- **Don't**: blood"])
@pytest.mark.parametrize("after", ["", "\n- Chorus: wide\n", "\nC1 Ann = V1\n"])
def test_bulleted_do_not_label_is_one_rule(line, after):
    o = parse_intent(STORY + line + "\n" + after)
    assert o["do_not"] == ["blood"], o["do_not"]
    assert o["logline"] == "Two keepers wait."


@pytest.mark.parametrize("text,dn,notes", [
    ("- **Never show**\n  - blood\n  - fire\n- Chorus: wide\n", ["blood", "fire"], []),
    ("- Never show:\n- blood\n- fire\n\n## Notes\nThe end.\n", ["blood", "fire"], ["The end."]),
    ("- **Never show**\n  - blood\n- fire\n", ["blood"], ["fire"]),
])
def test_bulleted_bare_label_lists(text, dn, notes):
    o = parse_intent(text)
    assert o["do_not"] == dn and o["notes"] == notes


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
            f"do_not:{spaces}# rules in your own words; copied verbatim to every agent\n  - no fire\n")
    o = parse_intent("```yaml\n" + body + "```\n" if wrap == "fenced" else body)
    assert o["palette"] == ["#c93523"] and o["line_singers"] == {"L006": ["C2"]} and o["do_not"] == ["no fire"]
    assert not o["notes"] and not o["warnings"]
