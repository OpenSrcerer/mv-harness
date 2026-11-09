"""R-CONTRACT (M6b) round 2.

R2-4 (major, new; same class as round-1 F2): the user maps voices only (``C1: {voices: [V1]}``); the draft names and
describes the characters. ``build_characters`` fills the user character's empty name/description from the draft
(``filled_by_draft``) but that marker never leaves the stage: meaning.json says ``provenance {source: user, status:
user}`` with no per-field source, and brief.md's character table prints the draft's name and description with no
``(draft)`` label. A character-driven video agent designs the cast from the draft as if the user wrote it.

R2-5 (major, round-1 F2 fixed in brief.md only): agents that build in code read per-section meaning through
``song.meaningAt(t)`` / meaning.json, and skill/mv-harness tells them that ``provenance.status === 'draft'`` marks
agent-written text. In a section that mixes the user's feel with the draft's camera, status is ``user`` and the draft
camera/movement/palette are indistinguishable; ``field_sources`` (the per-field origin, decision A3) is mentioned
nowhere in SKILL.md or RECIPES.md.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from rc2_support import ROOT, SYNTH, authored, source

from mvh.stages.meaning.stage import build

INTENT_VOICES_ONLY = "```yaml\ncharacters:\n  C1: {voices: [V1]}\n  C2: {voices: [V2]}\n```\n"


def _brief(res: dict) -> str:
    from mvh.stages.brief.build import gather, render_brief

    over = {"meaning/meaning.json": res["meaning"], "meaning/orphans.json": {"orphans": res["orphans"]}}
    d = gather(source(files_over=over, events_over={"singing": res["singing"]}))
    return render_brief(d)[0]


def test_draft_written_character_name_is_not_presented_as_the_users() -> None:
    res = build(source(), INTENT_VOICES_ONLY, authored(), {})
    drafted = {c["id"]: c["name"] for c in authored()["characters"]}
    rows = {ln.split("|")[1].strip(): ln for ln in _brief(res).splitlines() if ln.startswith("| C")}
    bad = []
    for c in res["meaning"]["characters"]:
        if c["name"] != drafted.get(c["id"]):
            continue  # not the draft's name
        marked = "draft" in json.dumps(c.get("field_sources") or {}) or c["provenance"]["status"] != "user"
        labelled = "draft" in rows.get(c["id"], "").lower()
        if not (marked and labelled):
            bad.append(f"{c['id']} provenance={c['provenance']['status']}/{c['provenance']['source']} "
                       f"field_sources={c.get('field_sources')} brief row labelled={labelled}")
    assert not bad, "the draft's character names/descriptions are presented as the user's: " + "; ".join(bad)


@pytest.fixture(scope="module")
def mixed_song(tmp_path_factory) -> Path:
    if not (SYNTH / "meaning" / "intent.md").is_file():
        pytest.skip("tests/contract/synth is not built")
    from mvh.stages.meaning.devrun import DevRun

    work = tmp_path_factory.mktemp("m6b-rc2-mixed")
    song = work / "song"
    (song / "meaning").mkdir(parents=True)
    shutil.copyfile(SYNTH / "meaning" / "intent.md", song / "meaning" / "intent.md")
    shutil.copyfile(SYNTH / "meaning" / "authored.json", song / "meaning" / "authored.json")
    dr = DevRun(SYNTH, work, song_dir=song)
    dr.run("meaning")
    dr.publish(song)
    return song


def test_code_path_agents_can_tell_draft_fields_in_user_sections(mixed_song: Path) -> None:
    with open(mixed_song / "meaning" / "meaning.json", encoding="utf-8") as fh:
        m = json.load(fh)
    hidden = [s["section_id"] for s in m["sections"]
              if s["provenance"]["status"] == "user" and "draft" in (s.get("field_sources") or {}).values()]
    assert hidden, "precondition: some user section carries draft fields"
    skill = ""
    for p in (ROOT / "skill" / "mv-harness").rglob("*.md"):
        if p.name == "CONTRACT.md":
            continue  # the generated 25k-token copy is not what agents are pointed to for this
        skill += p.read_text(encoding="utf-8")
    assert "field_sources" in skill, (
        f"sections {hidden} have provenance.status 'user' but draft fields; SKILL.md/RECIPES.md tell agents only "
        "provenance.status === 'draft' marks agent text and never mention field_sources")
