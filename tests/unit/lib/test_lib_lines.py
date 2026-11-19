"""Song.soundtrack, Song.meaning and Song.lines_at(t) (karaoke with overlapping lines) in lib/mvh_load.py; the JS twin
is tests/unit/lib/lines.test.mjs (same folder)."""
from __future__ import annotations

import json
from pathlib import Path

LINES = [{"id": "L001", "t": 1.0, "d": 2.0, "text": "a b", "grade": "A"},
         {"id": "L002", "t": 2.5, "d": 1.5, "text": "c d", "grade": "D"}]
WORDS = [{"id": "L001.01", "line_id": "L001", "t": 1.0, "d": 0.5, "text": "a", "conf": 0.9},
         {"id": "L001.02", "line_id": "L001", "t": 2.0, "d": 0.9, "text": "b", "conf": 0.9},
         {"id": "L002.01", "line_id": "L002", "t": 2.5, "d": 0.4, "text": "c", "conf": 0.3},
         {"id": "L002.02", "line_id": "L002", "t": 3.2, "d": 0.5, "text": "d", "conf": 0.3}]
SINGING = [{"t": 1.0, "d": 2.0, "line_id": "L001", "voice_id": "V1", "character_id": "C1", "lead_backing": "lead"},
           {"t": 2.5, "d": 1.5, "line_id": "L002", "voice_id": "V2", "character_id": "C2", "lead_backing": "lead"}]


def _folder(tmp: Path, soundtrack: str | None) -> Path:
    for d in ("events", "lyrics", "meaning"):
        (tmp / d).mkdir(parents=True)
    man = {"schema": "mvh/manifest", "source": {"duration_s": 5.0}, "summary": {"duration_s": 5.0},
           "files": [{"path": "events/singing.json", "kind": "events", "stage": "x"}]}
    if soundtrack:
        man["timebase"] = {"soundtrack": soundtrack}
    (tmp / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (tmp / "lyrics" / "lyrics.json").write_text(json.dumps({"lines": LINES, "words": WORDS}), encoding="utf-8")
    (tmp / "events" / "singing.json").write_text(json.dumps({"kind": "segment", "items": SINGING}), encoding="utf-8")
    (tmp / "meaning" / "meaning.json").write_text(json.dumps(
        {"status": "pending", "characters": [{"id": "C1", "name": "One"}, {"id": "C2", "name": "Two"}], "do_not": []}),
        encoding="utf-8")
    return tmp


def test_soundtrack_and_meaning(ml, tmp_path):
    s = ml.load(_folder(tmp_path / "a", "audio/mix.wav"))
    assert s.soundtrack == "audio/mix.wav"
    assert [c["id"] for c in s.meaning["characters"]] == ["C1", "C2"]
    assert ml.load(_folder(tmp_path / "b", None)).soundtrack == "audio/mix.flac"


def test_lines_at_returns_every_line_sounding_at_t(ml, tmp_path):
    s = ml.load(_folder(tmp_path, None))
    assert s.lines_at(0.5) == []
    one = s.lines_at(1.2)
    assert [x["line"]["id"] for x in one] == ["L001"]
    assert [w["id"] for w in one[0]["words"]] == ["L001.01", "L001.02"]
    assert one[0]["word"]["id"] == "L001.01" and abs(one[0]["progress"] - 0.1) < 1e-9
    both = s.lines_at(2.7)                                   # the overlap: lyric_at shows only the later line
    assert [x["line"]["id"] for x in both] == ["L001", "L002"]
    assert [x["line"]["singer"] for x in both] == [["C1"], ["C2"]]
    assert s.lyric_at(2.7)["line"]["id"] == "L002"
    assert [x["word"]["id"] for x in both] == ["L001.02", "L002.01"]
    gap = s.lines_at(3.05)
    assert len(gap) == 1 and gap[0]["word"] is None and gap[0]["word_progress"] is None
    assert ml.HELPER_NEEDS["lines_at"] == ["lyrics", "events:singing"]
