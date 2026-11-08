# ruff: noqa: E501  (long lines)
"""mvh view server: security, static serving, atomic validated writes, affected stages, idle timeout."""
from __future__ import annotations

import http.client
import json
import re
import time

import pytest

from mvh.stages.viewer import intent_block as ib
from mvh.stages.viewer.server import affected_by_intent, affected_by_keys, changed_keys, make_server

PAGE = "<!doctype html><html><head><title>t</title><!--MVH-EDIT--></head><body>viewer</body></html>"


@pytest.fixture()
def folder(tmp_path):
    f = tmp_path / "song folder ünï"  # spaces and non-ASCII in the path
    (f / "audio").mkdir(parents=True)
    (f / "meaning").mkdir()
    (f / ".cache").mkdir()
    (f / "_intermediate").mkdir()
    (f / "viewer.html").write_text(PAGE, encoding="utf-8")
    (f / "audio" / "mix.flac").write_bytes(bytes(range(256)) * 40)
    (f / ".cache" / "secret.txt").write_text("nope", encoding="utf-8")
    (f / "_intermediate" / "x.txt").write_text("nope", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    return f


@pytest.fixture()
def srv(folder):
    s = make_server(folder, port=0, idle_timeout=0, allow_rerun=False)
    s.start()
    yield s
    s.shutdown()


def req(s, method, path, body=None, headers=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", s.port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{s.port}"}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    raw = r.read()
    c.close()
    return r.status, dict(r.getheaders()), raw


def post(s, path, body, token=True, **kw):
    h = {"X-MVH-Token": s.token} if token else {}
    h.update(kw.pop("headers", {}))
    st, _h, raw = req(s, "POST", path, body, h, **kw)
    return st, json.loads(raw.decode("utf-8")) if raw else {}


def test_binds_loopback_only(srv):
    assert srv.httpd.server_address[0] == "127.0.0.1" and srv.url.startswith("http://127.0.0.1:")


def test_page_gets_the_edit_token(srv):
    st, h, raw = req(srv, "GET", "/")
    assert st == 200 and h["Content-Type"].startswith("text/html")
    html = raw.decode("utf-8")
    assert "<!--MVH-EDIT-->" not in html
    m = re.search(r"window\.MVH_EDIT=(\{.*?\});", html)
    cfg = json.loads(m.group(1))
    assert cfg["token"] == srv.token and cfg["rerun"] is False
    assert h["Cache-Control"] == "no-store"


def test_read_only_server_has_no_token(folder):
    s = make_server(folder, edit=False, idle_timeout=0).start()
    try:
        st, _h, raw = req(s, "GET", "/")
        assert b"MVH_EDIT" not in raw
        st, body = post(s, "/api/overrides", {"overrides": {}})
        assert st == 403
    finally:
        s.shutdown()


def test_static_files_range_and_hidden_paths(srv, folder):
    st, h, raw = req(srv, "GET", "/audio/mix.flac")
    assert st == 200 and len(raw) == 256 * 40 and h["Accept-Ranges"] == "bytes" and h["Content-Type"] == "audio/flac"
    st, h, raw = req(srv, "GET", "/audio/mix.flac", headers={"Range": "bytes=10-19"})
    assert st == 206 and raw == bytes(range(10, 20)) and h["Content-Range"] == f"bytes 10-19/{256 * 40}"
    st, h, raw = req(srv, "GET", "/audio/mix.flac", headers={"Range": "bytes=-5"})
    assert st == 206 and raw == bytes(range(251, 256))
    st, h, raw = req(srv, "GET", "/audio/mix.flac", headers={"Range": "bytes=999999-"})
    assert st == 416
    for bad in ("/.cache/secret.txt", "/_intermediate/x.txt", "/../outside.txt", "/%2e%2e/outside.txt", "/audio/../../outside.txt",
                "/audio", "/nothing.json", "/C:/Windows/win.ini", "/..%5Coutside.txt"):
        st, _h, _r = req(srv, "GET", bad)
        assert st == 404, bad
    st, _h, raw = req(srv, "HEAD", "/audio/mix.flac")
    assert st == 200 and raw == b""


def test_host_header_is_checked(srv):
    st, _h, _r = req(srv, "GET", "/", host="evil.example:80")
    assert st == 403
    st, _h, _r = req(srv, "GET", "/", host=f"localhost:{srv.port}")
    assert st == 200


def test_post_needs_token_and_origin(srv):
    body = {"overrides": {"rhythm": {"bpm": 120}}}
    assert post(srv, "/api/overrides", body, token=False)[0] == 403
    st, _ = post(srv, "/api/overrides", body, headers={"X-MVH-Token": "wrong"})
    assert st == 403
    st, _ = post(srv, "/api/overrides", body, headers={"Origin": "http://evil.example"})
    assert st == 403
    assert not (srv.folder / "overrides.json").exists()
    st, res = post(srv, "/api/overrides", body, headers={"Origin": f"http://127.0.0.1:{srv.port}"})
    assert st == 200 and res["ok"]


def test_overrides_roundtrip_atomic_and_etag(srv):
    st, h, raw = req(srv, "GET", "/api/overrides")
    first = json.loads(raw)
    assert first == {"overrides": {}, "etag": "none"}
    doc = {"schema": "mvh/overrides", "schema_version": "1.0.0-rc.1", "rhythm": {"beat_offset_s": 0.012, "bpm": 123.5, "downbeat_phase": 1},
           "structure": {"boundaries": [{"action": "move", "t": 17.0, "to_t": 17.4}], "labels": [{"t": 13.0, "label": "pre-chorus"}]},
           "lyrics": {"lines": {"L001": {"dt": 0.05}}, "words": {"L001.02": {"t": 9.5, "d": 0.2}}}, "voices": {"lines": {"L003": "V2"}},
           "cues": {"pinned": [{"t": 12.0, "note": "cut"}]}}
    st, res = post(srv, "/api/overrides", {"overrides": doc, "etag": "none"})
    assert st == 200 and res["ok"] and res["etag"] != "none"
    on_disk = json.loads((srv.folder / "overrides.json").read_text(encoding="utf-8"))
    assert on_disk == doc
    assert set(res["changed"]) == {"rhythm.beat_offset_s", "rhythm.bpm", "rhythm.downbeat_phase", "structure.boundaries", "structure.labels",
                                   "lyrics.lines", "lyrics.words", "voices.lines", "cues.pinned"}
    assert not list(srv.folder.glob("overrides.json.*")) and not list(srv.folder.glob("*.tmp"))  # no temp files left behind
    # the stale etag (page loaded before another writer) is refused and nothing changes
    st, res2 = post(srv, "/api/overrides", {"overrides": {}, "etag": "none"})
    assert st == 409
    assert json.loads((srv.folder / "overrides.json").read_text(encoding="utf-8")) == doc
    # and the matching one is accepted
    st, res3 = post(srv, "/api/overrides", {"overrides": {"rhythm": {"bpm": 90}}, "etag": res["etag"]})
    assert st == 200


@pytest.mark.parametrize("bad", [
    {"rhythm": {"bpm": 0}},                                   # schema minimum
    {"rhythm": {"bpm": "fast"}},
    {"rhythm": {"downbeat_phase": 1.5}},
    {"structure": {"boundaries": [{"action": "explode", "t": 1}]}},
    {"structure": {"labels": [{"t": 1, "label": "Bad Label"}]}},
    {"lyrics": {"lines": {"line1": {"dt": 0.1}}}},
    {"voices": {"lines": {"L001": "voice1"}}},
    {"nonsense": {"a": 1}},                                   # unknown section: a typo must not be silently ignored
    {"rhythm": {"bmp": 120}},                                 # unknown field
])
def test_invalid_overrides_are_rejected_and_do_not_touch_the_file(srv, bad):
    good = {"rhythm": {"bpm": 100}}
    assert post(srv, "/api/overrides", {"overrides": good})[0] == 200
    before = (srv.folder / "overrides.json").read_bytes()
    st, res = post(srv, "/api/overrides", {"overrides": bad})
    assert st == 400 and res["errors"]
    assert (srv.folder / "overrides.json").read_bytes() == before


def test_bad_bodies(srv):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    c.request("POST", "/api/overrides", body=b"{not json", headers={"Host": f"127.0.0.1:{srv.port}", "X-MVH-Token": srv.token})
    r = c.getresponse()
    r.read()
    assert r.status == 400
    c.close()
    assert post(srv, "/api/overrides", {"nope": 1})[0] == 400
    assert post(srv, "/api/overrides", ["x"])[0] == 400
    assert post(srv, "/api/unknown", {})[0] == 404
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    c.request("POST", "/api/overrides", body=b"x" * 2_000_000, headers={"Host": f"127.0.0.1:{srv.port}", "X-MVH-Token": srv.token})
    r = c.getresponse()
    r.read()
    assert r.status == 413
    c.close()


def test_intent_endpoint_preserves_user_text(srv, folder):
    user = "# mine\n\nWhat it means to me.\n"
    (folder / "meaning" / "intent.md").write_text(user, encoding="utf-8")
    st, res = post(srv, "/api/intent", {"voices": {"V1": {"character_id": "C1", "name": "The Lamplighter"}},
                                        "sections": {"S02": {"t0": 9, "t1": 17, "label": "verse#1", "feel": "slow drift", "palette": "#112233"}}})
    assert st == 200 and res["ok"]
    text = (folder / "meaning" / "intent.md").read_text(encoding="utf-8")
    assert text.startswith(user)
    got = json.loads(req(srv, "GET", "/api/intent")[2])
    assert got["voices"]["V1"]["name"] == "The Lamplighter" and got["sections"]["S02"]["feel"] == "slow drift" and got["exists"]
    assert [a["stage"] for a in res["affected"]]  # tells which stages re-run
    # a bad patch is rejected and leaves the file alone
    st, res = post(srv, "/api/intent", {"voices": {"V1": {"character_id": "zzz"}}})
    assert st == 400 and (folder / "meaning" / "intent.md").read_text(encoding="utf-8") == text
    # an identical patch changes nothing and reports no stage
    st, res = post(srv, "/api/intent", {"voices": {"V1": {"character_id": "C1", "name": "The Lamplighter"}}})
    assert st == 200 and res["affected"] == []


def test_intent_file_is_created_when_absent(srv, folder):
    assert not (folder / "meaning" / "intent.md").exists()
    st, _ = post(srv, "/api/intent", {"voices": {"V2": {"character_id": "C2", "name": "The Tide"}}})
    assert st == 200 and ib.parse((folder / "meaning" / "intent.md").read_text(encoding="utf-8"))["voices"]["V2"]["name"] == "The Tide"


def test_rerun_disabled(srv):
    assert post(srv, "/api/rerun", {})[0] == 403


def test_ping_and_unknown_api(srv):
    assert req(srv, "GET", "/api/ping")[0] == 200
    assert req(srv, "GET", "/api/nothing")[0] == 404


def test_idle_timeout_stops_the_server(folder):
    s = make_server(folder, idle_timeout=0.8).start()
    t0 = time.monotonic()
    assert s.wait() == "idle"
    assert time.monotonic() - t0 < 8
    with pytest.raises(OSError):
        req(s, "GET", "/api/ping")


def test_requests_keep_the_server_alive(folder):
    s = make_server(folder, idle_timeout=1.2).start()
    try:
        for _ in range(4):
            time.sleep(0.5)
            assert req(s, "GET", "/api/ping")[0] == 200
        assert not s.stop.is_set()
    finally:
        s.shutdown()


# ------------------------------------------------------------------------------------------------ affected stages
def test_changed_keys():
    old = {"rhythm": {"bpm": 100, "beat_offset_s": 0.1}}
    new = {"rhythm": {"bpm": 120, "beat_offset_s": 0.1}, "cues": {"pinned": [{"t": 1}]}}
    assert sorted(changed_keys(old, new)) == ["cues.pinned", "rhythm.bpm"]
    assert changed_keys(new, new) == []


def test_affected_follow_the_dag():
    a = {x["stage"] for x in affected_by_keys(["rhythm.bpm"])}
    assert {"rhythm", "structure", "choreo", "cues", "brief", "viewer"} <= a  # everything downstream of rhythm
    assert "ingest" not in a and "separate_hq" not in a
    b = [x["stage"] for x in affected_by_keys(["cues.pinned"])]
    assert b[0] == "cues"
    assert "rhythm" not in b
    ly = {x["stage"] for x in affected_by_keys(["lyrics.lines"])}
    assert "lyrics" in ly and "viewer" in ly and "rhythm" not in ly
    assert affected_by_keys([]) == []
    reasons = {x["stage"]: x["reason"] for x in affected_by_keys(["rhythm.bpm"])}
    assert "rhythm.bpm" in reasons["rhythm"] and reasons["viewer"] == "an upstream stage re-runs"


def test_intent_affects_voices_and_meaning_when_declared():
    st = {x["stage"] for x in affected_by_intent()}
    assert st & {"voices", "meaning"} and "viewer" in st
