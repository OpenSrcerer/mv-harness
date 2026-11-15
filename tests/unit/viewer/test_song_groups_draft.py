"""D81 in the viewer: the whole-song box and group meaning in the managed block of intent.md, read back by the
meaning parser, and dismissing a draft's suggestions (draft_edit, POST /api/draft). Synthetic text only."""
from __future__ import annotations

import json

import pytest
from test_server import folder, post, req, srv  # noqa: F401  (fixtures)

from mvh.stages.meaning.intent import parse_intent
from mvh.stages.viewer import draft_edit as de
from mvh.stages.viewer import intent_block as ib

USER = "# What this song means to me\n\nTwo figures keep a harbour lit.\n"
SONG = {"logline": "A night watch", "summary": "They light the lamps.\nThen the tide comes in.", "tone": "",
        "themes": "keeping watch\nthe sea", "palette": "#0E2346, rust red", "do_not": "no faces\nno fire"}
SECS = [{"id": "S01", "t": 0.0, "d": 10.0, "label": "intro"}, {"id": "S02", "t": 10.0, "d": 10.0, "label": "drop"},
        {"id": "S03", "t": 20.0, "d": 10.0, "label": "break"}, {"id": "S04", "t": 30.0, "d": 10.0, "label": "drop"}]


def test_song_and_groups_roundtrip_and_leave_user_text_alone():
    st = ib.merge(ib.empty(), {"song": SONG, "groups": {"all": {"camera": "wide"}, "Drop": {"feel": "flare", "palette": "#AABBCC"}}})
    assert st["song"] == {"logline": "A night watch", "summary": "They light the lamps. / Then the tide comes in.",
                          "themes": ["keeping watch", "the sea"], "palette": "#0E2346, rust red", "do_not": ["no faces", "no fire"]}
    assert st["groups"] == {"all": {"camera": "wide"}, "drop": {"feel": "flare", "palette": "#aabbcc"}}
    out = ib.apply(USER, st)
    assert out.startswith(USER) and "### Song\n- logline: A night watch\n" in out
    assert "### Every section\n- camera: wide\n" in out and "### Every drop\n- feel: flare\n- palette: #aabbcc\n" in out
    assert ib.parse(out) == st


def test_the_meaning_parser_reads_what_the_viewer_wrote():
    st = ib.merge(ib.empty(), {"song": SONG, "groups": {"all": {"camera": "wide"}, "drop": {"feel": "flare"}}})
    it = parse_intent(ib.apply(USER, st))
    assert it["logline"] == "A night watch" and it["themes"] == ["keeping watch", "the sea"]
    assert it["palette"][0] == "#0e2346" and it["do_not"] == ["no faces", "no fire"]
    assert [(c["key"], c["feel"], c["camera"]) for c in it["sections"]] == [("every section", None, "wide"), ("every drop", "flare", None)]
    assert it["notes"] == ["# What this song means to me\n\nTwo figures keep a harbour lit."] or it["notes"]


def test_song_patch_replaces_the_record_and_null_clears():
    st = ib.merge(ib.empty(), {"song": SONG, "voices": {"V1": {"character_id": "C1", "name": "A"}}})
    st = ib.merge(st, {"song": {"logline": "Only this"}})
    assert st["song"] == {"logline": "Only this"} and st["voices"]                 # the rest of the block stays
    st = ib.merge(st, {"groups": {"drop": {"feel": "x"}}})
    assert ib.merge(st, {"groups": {"drop": {"feel": ""}}})["groups"] == {}        # an empty group is removed
    st = ib.merge(st, {"song": None, "groups": {"drop": None}, "voices": {"V1": None}})
    assert ib.apply(ib.apply(USER, ib.merge(ib.empty(), {"song": SONG})), st) == USER


@pytest.mark.parametrize("patch", [
    {"song": "text"},
    {"song": {"logline": "x" * 5000}},
    {"groups": {"S01": {"feel": "x"}}},
    {"groups": {"section": {"feel": "x"}}},
    {"groups": {"drop": {"palette": "red"}}},
    {"groups": {"drop": "x"}},
])
def test_rejects_bad_song_and_group_patches(patch):
    with pytest.raises(ib.IntentError):
        ib.merge(ib.empty(), patch)


# ------------------------------------------------------------------------------------------------ dismiss
def _draft():
    return {"status": "draft", "logline": "A light", "tone": "dark", "themes": [{"text": "night"}, {"text": "sea"}],
            "palette": ["#112233"], "do_not": ["no rain", "no faces"],
            "sections": [{"section_id": s["id"], "t0": s["t"], "t1": s["t"] + s["d"], "feel": "f-" + s["label"],
                          "movement_hint": "m", "camera_hint": "c", "palette_hint": ["#445566"]} for s in SECS]}


def test_dismiss_song_section_and_group():
    d = _draft()
    n = de.dismiss(d, [{"scope": "song", "field": "logline"}, {"scope": "song", "field": "do_not", "value": "no rain"},
                       {"scope": "song", "field": "themes", "value": "sea"}, {"scope": "song", "field": "palette"}], SECS)
    assert n == 4 and d["logline"] is None and d["tone"] == "dark" and d["do_not"] == ["no faces"]
    assert d["themes"] == [{"text": "night"}] and d["palette"] == []
    assert de.dismiss(d, [{"scope": "section", "id": "S01", "field": "movement"}], SECS) == 1
    assert d["sections"][0]["movement_hint"] is None and d["sections"][0]["feel"] == "f-intro"
    assert de.dismiss(d, [{"scope": "group", "key": "drop", "field": "feel"}, {"scope": "group", "key": "drop", "field": "palette"}], SECS) == 4
    assert [s["feel"] for s in d["sections"]] == ["f-intro", None, "f-break", None]
    assert d["sections"][1]["palette_hint"] == [] and d["sections"][2]["palette_hint"] == ["#445566"]
    assert de.dismiss(d, [{"scope": "group", "key": "all", "field": "camera"}], SECS) == 4
    assert de.dismiss(d, [{"scope": "group", "key": "all", "field": "camera"}], SECS) == 0       # already gone


def test_dismiss_follows_a_section_that_moved():
    d = _draft()
    moved = [dict(s) for s in SECS]
    moved[1].update(t=11.0, d=9.0)                                     # the drop now starts a second later
    assert de.dismiss(d, [{"scope": "section", "id": "S02", "field": "feel"}], moved) == 1
    assert d["sections"][1]["feel"] is None


@pytest.mark.parametrize("items", [None, [], ["x"], [{"scope": "song", "field": "status"}], [{"scope": "nope", "field": "feel"}],
                                   [{"scope": "section", "id": "S99", "field": "feel"}], [{"scope": "section", "id": "S01", "field": "label"}]])
def test_dismiss_rejects_bad_items(items):
    with pytest.raises(de.DraftError):
        de.dismiss(_draft(), items, SECS)


# ------------------------------------------------------------------------------------------------ server
def test_song_box_is_saved_through_the_intent_endpoint(srv, folder):  # noqa: F811
    (folder / "meaning" / "intent.md").write_text(USER, encoding="utf-8")
    st, res = post(srv, "/api/intent", {"song": SONG, "groups": {"drop": {"feel": "flare"}}})
    assert st == 200 and res["intent"]["song"]["logline"] == "A night watch" and res["intent"]["groups"] == {"drop": {"feel": "flare"}}
    text = (folder / "meaning" / "intent.md").read_text(encoding="utf-8")
    assert text.startswith(USER) and parse_intent(text)["logline"] == "A night watch"
    got = json.loads(req(srv, "GET", "/api/intent")[2])
    assert got["song"]["themes"] == ["keeping watch", "the sea"] and got["groups"]["drop"]["feel"] == "flare"
    st, res = post(srv, "/api/intent", {"groups": {"S01": {"feel": "x"}}})
    assert st == 400 and (folder / "meaning" / "intent.md").read_text(encoding="utf-8") == text


def test_draft_endpoint_removes_only_what_was_dismissed(srv, folder):  # noqa: F811
    st, res = post(srv, "/api/draft", {"dismiss": [{"scope": "song", "field": "logline"}]})
    assert st == 404                                                    # no draft yet
    (folder / "events").mkdir()
    (folder / "events" / "sections.json").write_text(json.dumps({"items": SECS}), encoding="utf-8")
    p = folder / "meaning" / "authored.json"
    p.write_text(json.dumps(_draft()), encoding="utf-8")
    (folder / "meaning" / "intent.md").write_text(USER, encoding="utf-8")
    st, res = post(srv, "/api/draft", {"dismiss": [{"scope": "song", "field": "logline"}, {"scope": "group", "key": "drop", "field": "feel"}]})
    assert st == 200 and res["removed"] == 3 and "meaning" in [a["stage"] for a in res["affected"]]
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["logline"] is None and d["tone"] == "dark" and [s["feel"] for s in d["sections"]] == ["f-intro", None, "f-break", None]
    assert (folder / "meaning" / "intent.md").read_text(encoding="utf-8") == USER       # the user's file is not touched
    before = p.read_bytes()
    st, res = post(srv, "/api/draft", {"dismiss": [{"scope": "song", "field": "nope"}]})
    assert st == 400 and p.read_bytes() == before
    st, res = post(srv, "/api/draft", {"dismiss": [{"scope": "song", "field": "logline"}]})
    assert st == 200 and res["removed"] == 0 and res["affected"] == [] and p.read_bytes() == before
    assert post(srv, "/api/draft", {"dismiss": [{"scope": "song", "field": "tone"}]}, token=False)[0] == 403
