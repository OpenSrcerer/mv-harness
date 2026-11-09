"""Re-anchoring per-section claims when the sections move (PLAN §8.5)."""
from __future__ import annotations

from mvh.stages.meaning.anchor import anchor_claim, norm_label

SECS = [
    {"id": "S01", "t": 0.0, "d": 10.0, "label": "intro", "occurrence": 1},
    {"id": "S02", "t": 10.0, "d": 10.0, "label": "verse", "occurrence": 1},
    {"id": "S03", "t": 20.0, "d": 10.0, "label": "chorus", "occurrence": 1},
    {"id": "S04", "t": 30.0, "d": 10.0, "label": "verse", "occurrence": 2},
    {"id": "S05", "t": 40.0, "d": 10.0, "label": "chorus", "occurrence": 2},
]
ROLES = [{"id": "R01", "t": 40.0, "d": 10.0, "role": "drop", "section_id": "S05"}]


def test_id_unchanged():
    a = anchor_claim({"key": "S03", "t0": 20.0, "t1": 30.0}, SECS)
    assert a["section_ids"] == ["S03"] and not a["reanchored"] and a["orphan_reason"] is None


def test_shifted_ids_follow_time():
    # the user wrote about S03 when it was 20-30 s; a new boundary renumbered sections (now it is S04)
    secs = [{"id": "S00x", "t": 0.0, "d": 5.0}] + SECS  # S00x is not an id; only time counts
    secs = [dict(s, id=f"S{k + 1:02d}") for k, s in enumerate(secs)]
    a = anchor_claim({"key": "S03", "t0": 20.0, "t1": 30.0}, secs)
    assert a["section_ids"] == ["S04"] and a["reanchored"]


def test_split_section_keeps_note_on_both_halves():
    secs = SECS[:2] + [{"id": "S03", "t": 20.0, "d": 5.0, "label": "chorus", "occurrence": 1},
                       {"id": "S04", "t": 25.0, "d": 5.0, "label": "chorus", "occurrence": 2}] + \
        [dict(s, id=f"S{int(s['id'][1:]) + 1:02d}") for s in SECS[3:]]
    a = anchor_claim({"key": "S03", "t0": 20.0, "t1": 30.0}, secs)
    assert a["section_ids"] == ["S03", "S04"]


def test_merged_sections():
    secs = [SECS[0], {"id": "S02", "t": 10.0, "d": 20.0, "label": "verse", "occurrence": 1}]
    a = anchor_claim({"key": "S03", "t0": 20.0, "t1": 30.0}, secs)
    assert a["section_ids"] == ["S02"]


def test_orphan_when_no_overlap():
    a = anchor_claim({"key": "S09", "t0": 100.0, "t1": 110.0}, SECS)
    assert a["section_ids"] == [] and a["old_section_id"] == "S09" and "50 %" in a["orphan_reason"]
    b = anchor_claim({"key": "S09"}, SECS)  # no times and the id is gone
    assert b["section_ids"] == [] and "no longer exists" in b["orphan_reason"]


def test_labels_occurrences_ordinals_roles():
    assert anchor_claim({"key": "chorus"}, SECS)["section_ids"] == ["S03", "S05"]
    assert anchor_claim({"key": "choruses"}, SECS)["section_ids"] == ["S03", "S05"]
    assert anchor_claim({"key": "chorus#2"}, SECS)["section_ids"] == ["S05"]
    assert anchor_claim({"key": "verse 2"}, SECS)["section_ids"] == ["S04"]
    assert anchor_claim({"key": "last chorus"}, SECS)["section_ids"] == ["S05"]
    assert anchor_claim({"key": "first verse"}, SECS)["section_ids"] == ["S02"]
    assert anchor_claim({"key": "drop"}, SECS, ROLES)["section_ids"] == ["S05"]
    r = anchor_claim({"key": "build"}, SECS, ROLES)
    assert r["section_ids"] == [] and r["orphan_reason"]
    assert norm_label("Choruses") == "chorus" and norm_label("hook") == "chorus"
