# ruff: noqa: E501
"""R-WORDS round 3 (r-words-m6b-r3), finding R3-1: the interview template drops the user's own answers.

``docs.yaml_template`` says "answers the user already gave are filled in, so the template can replace the free text
without losing anything", and the template header tells the user to copy it into meaning/intent.md. It always writes
``motifs: []``, ``symbolism: []`` and ``do_not: []`` per section, so copying the regenerated template back loses the
user's section-level prohibitions, motifs and symbolism. Synthetic fixture only (no real lyrics)."""
from __future__ import annotations

import rw_m6b_support as S

from mvh.stages.meaning.stage import build


def _template(interview: str) -> str:
    a = interview.index("```yaml")
    b = interview.index("```", a + 7)
    return interview[a:b + 3] + "\n"


def _yaml_intent() -> str:
    _files, ev = S.synth_parts()
    s5 = next(s for s in ev["sections"] if s["id"] == "S05")
    return f"""```yaml
logline: "Two keepers light a harbour."
characters:
  C1: {{name: "The Lamplighter", voices: [V1], lead_backing: lead}}
  C2: {{name: "The Tide", voices: [V2]}}
do_not:
  - "No fire on people."
motifs:
  - {{name: lanterns, lines: [L001, L003], note: "memory"}}
symbolism: ["Lanterns are memory."]
sections:
  S05:
    t0: {s5['t']}
    t1: {s5['t'] + s5['d']}
    feel: "everything at once"
    do_not: ["No close-ups of faces here."]
```
"""


def _roundtrip(intent_text: str):
    first = build(S.source(), intent_text, None, {})
    again = build(S.source(), _template(first["interview"]), None, {})
    return first["meaning"], again["meaning"]


def test_template_keeps_section_do_not_rule():
    a, b = _roundtrip(_yaml_intent())
    s5a = next(s for s in a["sections"] if s["section_id"] == "S05")
    assert "No close-ups of faces here." in (s5a.get("do_not") or [])  # control: the YAML answer is read
    s5b = next(s for s in b["sections"] if s["section_id"] == "S05")
    assert "No close-ups of faces here." in (s5b.get("do_not") or []), \
        "the user's S05 do_not rule is lost when the regenerated interview template is copied back"


def test_template_keeps_motifs_and_symbolism():
    a, b = _roundtrip(_yaml_intent())
    assert [m["name"] for m in a.get("motifs") or []] == ["lanterns"]  # control
    assert [m["name"] for m in b.get("motifs") or []] == ["lanterns"], "user motifs lost through the template"
    assert [x["text"] for x in b.get("symbolism") or []] == ["Lanterns are memory."], "user symbolism lost through the template"
