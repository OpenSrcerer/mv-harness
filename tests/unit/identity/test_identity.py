"""identity: tag normalisation, the MusicBrainz rules (version tag retry, duration window, ranking, credits) on
synthetic recorded HTTP, and the stage run offline (tags win, fallback identity:offline). No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.synth.m5.fakehttp import FakeHttp, load_fixture

from mvh.stages.identity import core

REPO = Path(__file__).resolve().parents[3]
SYNTH = REPO / "tests" / "contract" / "synth"


def test_normalise_tags():
    n = core.normalise_tags({"TITLE": "Glass River (Redux Version)", "artist": "The Fixtures", "date": "2009-05-01",
                             "track": "6/12", "isrc": "xx-a00-00-00001", "album": "River (Legacy Edition)"})
    assert n["title"] == "Glass River (Redux Version)" and n["artist"] == "The Fixtures"
    assert n["year"] == 2009 and n["track_no"] == 6 and n["isrc"] == "XXA000000001"
    assert core.normalise_tags({})["title"] is None


def test_strip_version_tag_and_keys():
    assert core.strip_version_tag("Jeremy (Redux Version)") == "Jeremy"
    assert core.strip_version_tag("Song [Remastered 2011]") == "Song"
    assert core.strip_version_tag("Song feat. Somebody") == "Song"
    assert core.strip_version_tag("Plain") is None
    assert core.title_key("Café (Live)") == "cafe"
    assert core.text_sim("Sir Isaac Newton vs Bill Nye", "Sir Isaac Newton vs. Bill Nye") >= 90


def test_credits_from_tags():
    c = core.credits_from_tags({"composer": "A One; B Two", "lyricist": "C Three", "artist": "X", "producer": "D/E"})
    assert {"role": "composer", "name": "B Two"} in c and {"role": "lyricist", "name": "C Three"} in c
    assert {"role": "producer", "name": "E"} in c
    assert all(x["role"] != "artist" for x in c)


def test_musicbrainz_version_tag_retry_and_ranking():
    http = FakeHttp(load_fixture("musicbrainz_versioned.json"))
    r = core.musicbrainz_lookup(http, title="Glass River (Redux Version)", artist="The Fixtures",
                                album="River (Legacy Edition)", isrc=None, duration_s=200.0)
    best = r["best"]
    assert best is not None and best.id.endswith("000000000002")      # 0.09 s off on the matching release
    assert abs(best.duration_diff_s) < 0.1
    assert r["queries"][:2] == ["title+dur", "base_title+dur"]          # full title first, then without the tag
    q = [s["params"]["query"] for s in http.seen if s["url"].endswith("/recording")]
    assert "dur:[197000 TO 203000]" in q[0] and "Redux" not in q[1]
    # both candidates pass the gates (2.4 s <= 3 s); the release-title match and |Δdur| decide
    assert sum(1 for c in r["candidates"] if c.accepted) == 2
    cr = core.recording_credits(http, best.id)
    roles = {(c["role"], c["name"]) for c in cr["credits"]}
    assert ("vocal (lead vocals)", "Ada Example") in roles and ("composer", "Cy Example") in roles
    assert cr["isrcs"] == ["XXA000000001"]


def test_musicbrainz_rejects_far_durations():
    cands = core.parse_recordings({"recordings": [{"id": "a", "score": 100, "title": "Glass River", "length": 210000,
                                                   "artist-credit": [{"name": "The Fixtures"}]}]})
    ranked = core.rank_candidates(cands, title="Glass River", artist="The Fixtures", album=None, duration_s=200.0)
    assert not ranked[0].accepted                                         # 10 s off
    cands = core.parse_recordings({"recordings": [{"id": "b", "score": 80, "title": "Glass River", "length": 200000,
                                                   "artist-credit": [{"name": "The Fixtures"}]}]})
    assert not core.rank_candidates(cands, title="Glass River", artist="The Fixtures", album=None, duration_s=200.0)[0].accepted


def test_musicbrainz_503_is_not_fatal():
    http = FakeHttp([{"method": "GET", "url_endswith": "/ws/2/recording", "status": 503, "body": {"error": "rate"}}])
    r = core.musicbrainz_lookup(http, title="X (Live)", artist="Y", album=None, isrc=None, duration_s=100.0)
    assert r["best"] is None and all(x["status"] == 503 for x in r["log"])
    assert len(r["log"]) <= core.MB_MAX_REQUESTS


def test_stage_offline_keeps_tags(tmp_path):
    from tests.synth.m5.harness import Harness

    h = Harness(SYNTH, tmp_path)
    rec = h.run("identity")
    d = h.json("identity", "meta/identity.json")
    assert d["title"] == "Lanterns on the Tide" and d["artist"] == "mv-harness fixture" and d["album"] == "Synthetic Sessions"
    assert d["source"] == "tags" and 0.85 <= d["conf"] <= 1.0
    assert d["duration_s"] == pytest.approx(56.5)
    assert "identity:offline" in rec["result"]["fallbacks"]
    assert d["lookup"]["musicbrainz"]["status"] == "offline"
    # no lyric-tag text and no network data leaked into the summary
    assert json.dumps(rec["result"]["summary"]).count("Lanterns") == 1


def test_stage_draft_profile_does_not_look_up(tmp_path):
    from tests.synth.m5.harness import Harness

    h = Harness(SYNTH, tmp_path, profile="draft")
    rec = h.run("identity")
    assert h.json("identity", "meta/identity.json")["lookup"]["musicbrainz"]["status"] == "skipped"
    assert rec["result"]["fallbacks"] == []
