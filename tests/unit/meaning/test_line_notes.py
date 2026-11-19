"""D87: optional notes on single lyric lines. The viewer block (### Lines), the meaning parser, how a note reaches a
line (own key, a repeat's shared note, 'only' for one line, split bars), lost keys, and the stage output."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.meaning.stage import resolve_line_notes
from mvh.stages.viewer import intent_block as B


def test_the_viewer_block_round_trips_line_notes():
    st = B.merge(B.empty(), {"lines": {"r12": {"note": "a two-line\nnote", "repeats": True}, "r3p1": {"note": "b", "repeats": False}}})
    text = B.apply("", st)
    assert "### Lines" in text and "- r3p1 only: b" in text and "- r12: a two-line / note" in text
    assert B.parse(text)["lines"] == {"r3p1": {"note": "b", "repeats": False}, "r12": {"note": "a two-line / note", "repeats": True}}
    assert parse_intent(text)["line_notes"] == B.parse(text)["lines"]
    st = B.merge(B.parse(text), {"lines": {"r12": None, "r3p1": {"note": ""}}})   # null or empty removes a note
    assert B.apply(text, st).count("### Lines") == 0


@pytest.mark.parametrize("key", ["S01", "r1w2", "12", "", "x"])
def test_bad_line_keys_are_refused(key):
    with pytest.raises(B.IntentError):
        B.merge(B.empty(), {"lines": {key: {"note": "n"}}})


def _lines():
    return [
        {"id": "L001", "t": 1.0, "d": 1.0, "ref": "r0", "legacy_id": "L001", "repeat_group": "LG01"},
        {"id": "L002", "t": 3.0, "d": 1.0, "ref": "r1", "legacy_id": "L002", "repeat_group": None},
        {"id": "L003", "t": 5.0, "d": 1.0, "ref": "r2", "legacy_id": "L003", "repeat_group": "LG01"},
        {"id": "L004", "t": 7.0, "d": 1.0, "ref": "r3p0", "legacy_id": "L004", "repeat_group": None},
        {"id": "L005", "t": 8.0, "d": 1.0, "ref": "r3p1", "legacy_id": "L004", "repeat_group": None},
        {"id": "L006", "t": 9.0, "d": 1.0, "ref": "r4", "legacy_id": "L005", "repeat_group": "LG01"},
    ]


def _by_line(out):
    return {x["line_id"]: (x["note"], x["shared"], x["from_line"]) for x in out}


def test_a_note_covers_every_repeat_unless_a_repeat_has_its_own():
    out, lost = resolve_line_notes({"r0": {"note": "hook", "repeats": True}, "r2": {"note": "twist", "repeats": False}}, _lines())
    assert not lost
    assert _by_line(out) == {"L001": ("hook", False, "L001"), "L003": ("twist", False, "L003"), "L006": ("hook", True, "L001")}


def test_a_note_for_one_line_only_does_not_spread():
    out, _ = resolve_line_notes({"r2": {"note": "only here", "repeats": False}}, _lines())
    assert _by_line(out) == {"L003": ("only here", False, "L003")}


def test_split_bars_and_lost_keys():
    out, lost = resolve_line_notes({"r3": {"note": "whole", "repeats": True}, "r3p1": {"note": "part", "repeats": True},
                                    "r9": {"note": "gone", "repeats": True}}, _lines())
    assert _by_line(out) == {"L004": ("whole", False, "L004"), "L005": ("part", False, "L005")}
    assert lost == ["r9"]


def test_the_stage_writes_line_notes_and_counts_them_as_the_users_meaning(make_devrun):
    dr = make_devrun()
    synth = Path(__file__).resolve().parents[2] / "contract" / "synth"   # the fixture the dev run reads
    lyr = json.loads((synth / "lyrics" / "lyrics.json").read_text(encoding="utf-8"))
    first = lyr["lines"][0]
    key = first.get("ref") or first["id"]
    (dr.song_dir / "meaning" / "intent.md").write_text(B.apply("", B.merge(B.empty(), {"lines": {key: {"note": "a note"}}})),
                                                       encoding="utf-8")
    res = dr.run("meaning")
    assert res["status"] in ("ok", "degraded"), res
    m = json.loads(Path(dr.upstream["meaning"]["dir"], "meaning", "meaning.json").read_text(encoding="utf-8"))
    assert m["status"] == "user"
    own = [x for x in m["line_notes"] if not x["shared"]]
    assert [(x["line_id"], x["note"]) for x in own] == [(first["id"], "a note")]
    md = Path(dr.upstream["meaning"]["dir"], "meaning", "meaning.md").read_text(encoding="utf-8")
    assert "## Line notes (user)" in md
