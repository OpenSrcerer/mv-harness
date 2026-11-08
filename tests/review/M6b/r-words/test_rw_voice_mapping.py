# ruff: noqa: E501
"""R-WORDS M6b F2 (major): a voices-stage proposal attaches a voice to a user character that the user explicitly
mapped to a DIFFERENT voice, merging two singers into one character.

meaning.singing.build_characters applies ``meta/voices.json proposed_character_id`` before it gives an unmapped voice
to a user character that has no voice yet. The voices stage (M5) proposes V_k -> C_k by order whenever intent.md names
as many characters as there are voices and its own intent parser finds no explicit mapping, and that parser does not
read the ``voices: [V2]`` lists of the YAML template that meaning/interview.md tells the user to fill in. So for the
synthetic duet, a user who writes "C1 = The Tide, voice V2; C2 = The Lamplighter" in the template gets C1 singing
every line (V1 AND V2) and C2 singing none: the duet collapses into one character, and the open question asks the
user again about C2. PLAN §8 / §4.3: the user's character mapping is the source of truth (SPIKE: "the user's
voice->character mapping is the source of truth"); PLAN §7 gate: >= 90 % of lines correct after the user maps voices.
"""
from __future__ import annotations

import copy

from rw_m6b_support import source, synth_parts

from mvh.stages.meaning.stage import build
from mvh.stages.voices.intent import parse_intent as voices_parse_intent

INTENT = """```yaml
characters:
  C1: {name: "The Tide", description: "", voices: [V2], lead_backing: lead}
  C2: {name: "The Lamplighter", description: "", voices: [], lead_backing: lead}
```
"""


def _voices_meta_as_m5_would_write(intent: str) -> dict:
    """meta/voices.json with proposed_character_id computed exactly as mvh.stages.voices.core does (lines 260-262)."""
    files, _ = synth_parts()
    vm = copy.deepcopy(files["meta/voices.json"])
    p = voices_parse_intent(intent)
    voices_all = [v["id"] for v in vm["voices"]]
    v2c = p.get("voice_to_character") or {}
    if not v2c and p.get("n_characters") and p["n_characters"] == len(voices_all):
        v2c = {v: f"C{i + 1}" for i, v in enumerate(voices_all)}
    for v in vm["voices"]:
        v["proposed_character_id"] = v2c.get(v["id"])
    return vm


def test_user_mapped_character_does_not_absorb_a_second_voice():
    vm = _voices_meta_as_m5_would_write(INTENT)
    res = build(source({"meta/voices.json": vm}), INTENT, None, {})
    chars = {c["id"]: c for c in res["characters"]}
    assert chars["C1"]["voice_ids"] == ["V2"], (
        f"C1 was mapped by the user to V2 only, but got voices {chars['C1']['voice_ids']} "
        f"(how: {chars['C1']['voice_mapping']})")


def test_the_duet_keeps_two_characters_after_a_partial_user_mapping():
    vm = _voices_meta_as_m5_would_write(INTENT)
    res = build(source({"meta/voices.json": vm}), INTENT, None, {})
    singers = {c for cs in res["singers"].values() for c in cs}
    assert len(singers) == 2, f"the two-voice duet is sung by {sorted(singers)} only"
