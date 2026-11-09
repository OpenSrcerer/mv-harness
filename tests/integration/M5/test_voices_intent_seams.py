"""W3 seam (D51): the voices stage reads the viewer's managed intent block and the YAML interview template."""

from __future__ import annotations

from mvh.stages.viewer import intent_block as IB
from mvh.stages.voices.intent import parse_intent


def _with_block(prefix: str, voices: dict) -> str:
    st = IB.merge(IB.empty(), {"voices": voices})
    return IB.write(prefix, st) if hasattr(IB, "write") else prefix + "\n" + IB.render(st) + "\n"


def test_viewer_block_mapping_wins_and_keeps_the_voice_count():
    text = _with_block("## Characters\n- C1 The Lamplighter (voice V2)\n",
                       {"V1": {"character_id": "C1", "name": "The Lamplighter"},
                        "V2": {"character_id": "C1", "name": "The Lamplighter"},
                        "V3": {"character_id": "C2", "name": "The Tide"}})
    it = parse_intent(text)
    assert it["voice_to_character"] == {"V1": "C1", "V2": "C1", "V3": "C2"}
    # two voices mapped to one character must not shrink the clustering below the voices the user mapped
    assert it["n_voices_min"] == 3 and it["n_voices"] is None


def test_yaml_template_character_voice_lists_are_read():
    text = ("```yaml\n# mvh-intent v1\nlogline: a test\ncharacters:\n  C1: {name: Ann, voices: [V2]}\n"
            "  C2: {name: Bob, voices: [V1]}\nline_singers: {L005: C1+C2}\n```\n")
    it = parse_intent(text)
    assert it["n_characters"] == 2
    assert it["voice_to_character"] == {"V1": "C2", "V2": "C1"}
    assert it["line_characters"].get("L005") == ["C1", "C2"]
