"""D79 (UD2): Song.kick_source / Song.kicks() / events("kick") / pulse("kick") in lib/mvh_load.py; the JS twin is
tests/unit/lib/kick.test.mjs (same folder layout)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DRUM_HITS = [{"t": 0.5, "drum": "kick", "vel": 0.9, "conf": 0.8}, {"t": 0.5, "drum": "hat", "vel": 0.4, "conf": 0.9},
             {"t": 1.0, "drum": "kick", "vel": 0.7, "conf": 1.0}, {"t": 1.25, "drum": "snare", "vel": 0.7, "conf": 1.0}]
HITS_KICK = [{"t": 0.502, "strength": 1.4, "env": 0.95, "kick_conf": 0.9}, {"t": 1.26, "strength": 0.4, "env": 0.3}]


def _song(tmp: Path, kick_source: str | None, files=("drum_hits", "hits.kick")) -> Path:
    (tmp / "events").mkdir(parents=True)
    man = {"schema": "mvh/manifest", "source": {"duration_s": 2.0}, "summary": {"duration_s": 2.0},
           "files": [{"path": f"events/{n}.json", "kind": "events", "stage": "x"} for n in files]}
    if kick_source:
        man["summary"]["kick_source"] = kick_source
    (tmp / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    for n, items in (("drum_hits", DRUM_HITS), ("hits.kick", HITS_KICK)):
        if n in files:
            (tmp / "events" / f"{n}.json").write_text(json.dumps({"kind": "event", "items": items}), encoding="utf-8")
    return tmp


@pytest.mark.parametrize("ks,expect", [("drums", [0.5, 1.0]), ("mix", [0.502, 1.26])])
def test_kicks_follow_the_manifest_kick_source(ml, tmp_path, ks, expect):
    song = ml.load(_song(tmp_path, ks))
    assert song.kick_source == ks
    k = song.kicks()
    assert [it["t"] for it in k.items] == expect and all(it["source"] == ks for it in k.items)
    assert song.events("kick") is k and k.exists and k.name == "kick"
    assert song.resolve("kick") == [f"events:{'drum_hits' if ks == 'drums' else 'hits.kick'}"]
    assert song.pulse("kick", expect[0]) == pytest.approx(k.items[0]["vel"])
    assert k.next(0.6)["t"] == expect[1]


def test_kick_source_inferred_for_older_folders(ml, tmp_path):
    assert ml.load(_song(tmp_path / "a", None)).kick_source == "drums"
    s = ml.load(_song(tmp_path / "b", None, files=("hits.kick",)))
    assert s.kick_source == "mix" and [it["t"] for it in s.kicks().items] == [0.502, 1.26]
    e = ml.load(_song(tmp_path / "c", "drums", files=())).kicks()
    assert not e.exists and e.items == []
