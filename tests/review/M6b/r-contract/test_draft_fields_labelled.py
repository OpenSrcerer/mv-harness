"""R-CONTRACT (M6b) F2: draft claims are presented as the user's when a section mixes user and draft fields.

PLAN §1/§8: a draft "fills only the gaps, is labelled as a draft". The meaning stage merges per field (meaning.json
``sections[].field_sources``), but stamps ONE section-level ``provenance.status``: ``user`` as soon as any field is the
user's. ``mvh brief --section`` then prints every field under ``## Meaning (user, ...)`` with no per-field label, so
the agent reads the draft's camera and movement directions as the user's (RECIPES.md also tells agents that only
``provenance.status === 'draft'`` marks agent-written text).

Synthetic fixture with its own intent.md (the user wrote only a feel line for S01/S02/S04/S05) and authored.json
(the draft): S05's movement and camera come from the draft (field_sources) but are shown unlabelled under "user".
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SYNTH = ROOT / "tests" / "contract" / "synth"

FIELDS = (("feel", "feel"), ("meaning", "meaning"), ("movement_hint", "movement"), ("camera_hint", "camera"))


@pytest.fixture(scope="module")
def song(tmp_path_factory) -> Path:
    if not (SYNTH / "meaning" / "intent.md").is_file():
        pytest.skip("tests/contract/synth is not built")
    from mvh.stages.meaning.devrun import DevRun

    work = tmp_path_factory.mktemp("m6b-rc-prov")
    song = work / "song"
    (song / "meaning").mkdir(parents=True)
    shutil.copyfile(SYNTH / "meaning" / "intent.md", song / "meaning" / "intent.md")
    shutil.copyfile(SYNTH / "meaning" / "authored.json", song / "meaning" / "authored.json")
    dr = DevRun(SYNTH, work, song_dir=song)
    dr.run("meaning")
    dr.run("brief")
    dr.publish(song)
    return song


def _meaning(song: Path) -> dict:
    with open(song / "meaning" / "meaning.json", encoding="utf-8") as fh:
        return json.load(fh)


def test_fixture_really_mixes_user_and_draft(song: Path) -> None:
    m = _meaning(song)
    mixed = [s["section_id"] for s in m["sections"]
             if "user" in (s.get("field_sources") or {}).values() and "draft" in (s.get("field_sources") or {}).values()]
    assert mixed, "precondition: some section merges user and draft fields"


def test_section_zoom_labels_every_draft_field(song: Path) -> None:
    from mvh.stages.brief.build import gather, render_section
    from mvh.stages.meaning.source import FolderSource

    m = _meaning(song)
    d = gather(FolderSource(song), [])
    unlabelled = []
    for s in m["sections"]:
        fs = s.get("field_sources") or {}
        text = render_section(d, s["section_id"])
        for key, lab in FIELDS:
            if fs.get(key) != "draft" or not s.get(key):
                continue
            line = next((ln for ln in text.splitlines() if ln.startswith(f"- {lab}:")), None)
            heading = next((ln for ln in text.splitlines() if ln.startswith("## Meaning")), "")
            if line is not None and "draft" not in line.lower() and "draft" not in heading.lower():
                unlabelled.append(f"{s['section_id']} {lab} (heading {heading!r})")
    assert not unlabelled, ("draft-sourced meaning fields shown as the user's in `mvh brief --section`: "
                            + "; ".join(unlabelled))
