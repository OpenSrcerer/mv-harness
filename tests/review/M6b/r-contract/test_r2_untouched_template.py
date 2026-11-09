"""R-CONTRACT (M6b) round 2, R2-1 (major, round-1 r-words F4 not fixed on two common song shapes).

interview.md says of its YAML template "Empty = no answer". The fix turned the harness's voice proposals into
comments, but two prefills remain that are not empty:

* **voices absent** (the voices stage failed or is degraded; real-jeremy in tests/contract has no voices): the
  fallback character ``C1 Lead voice`` gets ``voice_mapping {"V1": "user"}`` (``vhow.get(v, "user")`` default in
  meaning/stage.py), so the template writes ``voices: [V1]`` as if the user had said it;
* **no characters** (instrumental songs, no lyrics): the placeholder line is ``lead_backing: lead``.

Pasting the untouched template into intent.md (what the SKILL tells the agent to do with the user's answers) flips
``meaning.status`` from ``pending`` to ``user`` and stamps a harness default as a user character, so the SKILL rule
"pending + empty intent -> show the interview and wait" no longer fires and brief.md says ``meaning: user``.
"""
from __future__ import annotations

import pytest
from rc2_support import source, template_of

from mvh.stages.meaning.stage import build

SHAPES = {
    "voices_absent": dict(drop_files=("meta/voices.json",), drop_events=("voice_spans",)),
    "instrumental": dict(drop_files=("meta/voices.json", "lyrics/lyrics.json"), drop_events=("voice_spans",)),
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("fenced", [True, False], ids=["fenced", "unfenced"])
def test_untouched_template_is_not_a_user_answer(shape: str, fenced: bool) -> None:
    first = build(source(**SHAPES[shape]), None, None, {})
    assert first["meaning"]["status"] == "pending", "precondition: nothing authored yet"
    tmpl = template_of(first["interview"], fenced=fenced)
    again = build(source(**SHAPES[shape]), tmpl, None, {})
    m = again["meaning"]
    user_chars = [(c["id"], c["name"]) for c in m["characters"] if c["provenance"]["status"] == "user"]
    assert m["status"] == "pending" and not user_chars, (
        f"{shape}: pasting the untouched interview template made meaning.status={m['status']!r} and user characters "
        f"{user_chars} (the template prefills a harness default as an answer)")
