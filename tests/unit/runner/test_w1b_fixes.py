"""Regression tests for the w1b-fixer changes (D37, D39, D42, D45)."""

from __future__ import annotations

import pytest

from mvh import cli
from mvh.contract import conventions as cv
from mvh.contract import schemas
from mvh.runner.spec import Output, StageSpec, check_dag


def _raw(t, kind, tier, src):
    return {"t": t, "kind": kind, "tier": tier, "strength": 0.5, "lead_in_s": None,
            "source": {"file": "events/x.json", "id": src}}


def test_merge_cues_one_cue_per_time_and_next_reaches_all():
    raw = [_raw(1.0, "section", 1, "S1"), _raw(1.0, "drop", 1, "R1"), _raw(1.0, "beat", 4, "beat:0"),
           _raw(2.0, "phrase", 2, "P1"), _raw(3.0, "section", 1, "S2")]
    cues = cv.merge_cues(raw)
    assert [c["id"] for c in cues] == ["Q0001", "Q0002", "Q0003"]
    first = cues[0]
    assert first["kind"] == "drop" and first["tier"] == 1
    assert first["kinds"] == ["drop", "section", "beat"] and first["sources"][0] == first["source"]
    assert first["next_major_in_s"] == 2.0
    seen, t = [], -1.0
    while (c := cv.event_next(cues, t, 1)) is not None:
        seen.append(c["id"])
        t = c["t"]
    assert seen == ["Q0001", "Q0003"]


def test_safe_message_never_quotes_strings():
    secret = "SYNTHETIC SECRET LYRIC"
    errs = schemas.validate({"schema": secret}, "mvh/envelope/manifest")
    assert errs and not any(secret in e for e in errs)


def test_check_dag_rejects_two_producers_of_one_path():
    a = StageSpec("a", (), "main", "0.0.1", outputs=(Output("x/y.json", "json"),))
    b = StageSpec("b", (), "main", "0.0.1", outputs=(Output("x/y.json", "json"),))
    with pytest.raises(ValueError, match="declared by both"):
        check_dag({"a": a, "b": b})


def test_unique_slug_for_non_latin_titles(tmp_path, monkeypatch):
    monkeypatch.setenv("MVH_OUT", str(tmp_path / "out"))
    a = tmp_path / "曲.flac"
    b = tmp_path / "песня.flac"
    assert cli._unique_slug("song", a).startswith("song-")
    assert cli._unique_slug("song", a) != cli._unique_slug("song", b)
    assert cli._unique_slug("plain", tmp_path / "plain.flac") == "plain"
