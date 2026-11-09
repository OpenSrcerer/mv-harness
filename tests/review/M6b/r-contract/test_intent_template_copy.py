"""R-CONTRACT (M6b) F3: the interview's YAML template, copied as its first line says, loses the user's answers.

interview.md ends with "## Template (copy into meaning/intent.md)" and a ```yaml block whose first line is
"# mvh-intent v1: copy this block into meaning/intent.md and fill it in". SKILL.md tells the video agent to write the
user's answers into intent.md "(free text, or the YAML template at the end of the interview)". Copying the block's
content (without the markdown fence) is the natural reading, but parse_intent only treats an unfenced file as YAML
when its FIRST line is a template key; the template's own leading comment line defeats that, so the file falls to
the free-text parser:
  - the user's do_not rule is silently dropped (it never reaches meaning.json or brief.md),
  - YAML syntax becomes "user" claims (character name '{name', S05 feel '# chorus#2 0:34.5-0:50.5'),
  - meaning.status is still 'user' and no warning or open question says anything went wrong.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SYNTH = ROOT / "tests" / "contract" / "synth"


def _filled_template(interview: str) -> str:
    block = interview.split("```yaml", 1)[1].split("```", 1)[0]
    assert block.lstrip().startswith("# mvh-intent"), "precondition: the template starts with its comment line"
    t = block.replace('logline: ""', 'logline: "two keepers light the harbour"', 1)
    t = t.replace('C1: {name: "", description: ""', 'C1: {name: "Lamplighter", description: "the keeper"', 1)
    i = t.index("  S05:")
    t = t[:i] + t[i:].replace('feel: ""', 'feel: "explode outward"', 1)
    t = t.replace("do_not:   # rules in your own words; copied verbatim to every agent",
                  "do_not:   # rules in your own words; copied verbatim to every agent\n  - no cars on screen", 1)
    return t


@pytest.fixture(scope="module")
def merged(tmp_path_factory):
    if not (SYNTH / "events" / "sections.json").is_file():
        pytest.skip("tests/contract/synth is not built")
    from mvh.stages.meaning.devrun import DevRun

    # 1) the interview exactly as the stage writes it (pending, no intent)
    w0 = tmp_path_factory.mktemp("m6b-rc-iv")
    dr0 = DevRun(SYNTH, w0, song_dir=w0 / "song")
    dr0.run("meaning")
    dr0.publish(w0 / "song")
    with open(w0 / "song" / "meaning" / "interview.md", encoding="utf-8") as fh:
        interview = fh.read()
    # 2) the agent copies the template block (the YAML, not the markdown fence) into intent.md and fills it in
    w1 = tmp_path_factory.mktemp("m6b-rc-yaml")
    song = w1 / "song"
    (song / "meaning").mkdir(parents=True)
    with open(song / "meaning" / "intent.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_filled_template(interview))
    dr = DevRun(SYNTH, w1, song_dir=song)
    done = dr.run("meaning")
    dr.publish(song)
    with open(song / "meaning" / "meaning.json", encoding="utf-8") as fh:
        return json.load(fh), done


def test_copied_template_keeps_the_users_do_not_rule(merged) -> None:
    m, _done = merged
    assert "no cars on screen" in m["do_not"], f"the user's do-not rule was dropped (do_not={m['do_not']!r}, intent_form={m.get('intent_form')!r})"


def test_copied_template_answers_are_parsed_not_garbled(merged) -> None:
    m, _done = merged
    c1 = next(c for c in m["characters"] if c["id"] == "C1")
    s05 = next(s for s in m["sections"] if s["section_id"] == "S05")
    assert (m["logline"], c1["name"], s05["feel"]) == ("two keepers light the harbour", "Lamplighter", "explode outward"), (
        f"template answers mis-parsed as free text: logline={m['logline']!r}, C1 name={c1['name']!r}, S05 feel={s05['feel']!r}")


def test_unparsed_template_is_not_silently_status_user(merged) -> None:
    m, done = merged
    if m.get("intent_form") == "yaml":
        return
    warns = (done.get("result") or {}).get("warnings") or []
    assert warns or m["open_questions"], "intent.md fell back to free text with no warning and no open question"
