"""R-PLATFORM review of M6a: the ``mvh view`` server's POST validation and the safety of the user's files.

Each test is the evidence of one finding in docs/build/reports/r-platform-m6a.md and FAILS until the server is fixed.
Synthetic inputs only (no lyric text); every server binds 127.0.0.1 on port 0 and is stopped by the fixture.
"""

from __future__ import annotations

import http.client
import json

import pytest

from mvh.stages.viewer.server import make_server

LS, NEL = chr(0x2028), chr(0x85)  # LINE SEPARATOR, NEXT LINE
PAGE = "<!doctype html><html><head><title>t</title><!--MVH-EDIT--></head><body>viewer</body></html>"


@pytest.fixture()
def srv(tmp_path):
    f = tmp_path / "sông ☃ folder"
    (f / "meaning").mkdir(parents=True)
    (f / "viewer.html").write_text(PAGE, encoding="utf-8")
    s = make_server(f, port=0, idle_timeout=0, allow_rerun=False).start()
    yield s
    s.shutdown()


def _req(s, method, path, raw: bytes | None = None, token=True):
    c = http.client.HTTPConnection("127.0.0.1", s.port, timeout=10)
    h = {"Host": f"127.0.0.1:{s.port}", "Content-Type": "application/json"}
    if token:
        h["X-MVH-Token"] = s.token
    c.request(method, path, body=raw, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def _strict_loads(text: str):
    def bad(c):
        raise ValueError(f"non-standard JSON constant {c}")

    return json.loads(text, parse_constant=bad)


@pytest.mark.parametrize(("field", "value"), [("bpm", "NaN"), ("bpm", "Infinity"), ("beat_offset_s", "-Infinity"), ("bpm", "1e999")])
def test_post_overrides_rejects_non_finite_numbers(srv, field, value):
    """F-NAN: Python's json.loads accepts NaN/Infinity (and 1e999 -> inf), the schema's number/minimum checks let them
    through (NaN < 1 is False), and json.dumps writes them back. overrides.json then holds non-standard JSON: the next
    page load of the viewer itself fails (`r.json()` on api/overrides -> 'The viewer could not load this song'), as do
    JS/strict readers. The server must answer 400 and leave the file untouched."""
    body = ('{"overrides": {"schema": "mvh/overrides", "rhythm": {"%s": %s}}, "etag": null}' % (field, value)).encode("utf-8")
    st, _raw = _req(srv, "POST", "/api/overrides", body)
    p = srv.folder / "overrides.json"
    written = p.read_text(encoding="utf-8") if p.is_file() else None
    if written is not None:
        try:
            _strict_loads(written)
        except ValueError as e:
            pytest.fail(f"POST {value} -> HTTP {st}; overrides.json is no longer valid JSON ({e})")
    assert st == 400, f"POST {field}={value} answered {st} (expected 400)"


def test_unparseable_overrides_on_disk_is_not_silently_overwritten(srv):
    """F-CLOBBER: overrides.json is also written by hand (CONTRACT §1). When the user's file does not parse (a trailing
    comma), GET api/overrides answers {"overrides": {}} with no error, and the first edit in the viewer replaces the
    file: the hand-written corrections are gone without a word. The server must refuse (or keep a copy) and say so."""
    broken = '{"rhythm": {"bpm": 98.5,}, "structure": {"labels": [{"t": 10.0, "label": "chorus"}]}}\n'
    p = srv.folder / "overrides.json"
    p.write_text(broken, encoding="utf-8", newline="\n")
    st, raw = _req(srv, "GET", "/api/overrides")
    got = json.loads(raw)
    st2, _ = _req(srv, "POST", "/api/overrides",
                  json.dumps({"overrides": {"rhythm": {"beat_offset_s": 0.01}}, "etag": got.get("etag")}).encode("utf-8"))
    kept = [q.name for q in srv.folder.iterdir() if q.is_file() and q.read_bytes() == broken.encode("utf-8")]
    assert kept, (f"GET answered {st} {got} (no error reported); POST answered {st2}; the user's hand-written "
                  f"overrides.json was replaced and no copy of it remains")


def test_intent_values_with_unicode_line_separators_survive(srv):
    """F-INTENT-LS: values written to the managed block of meaning/intent.md are made single-line by replacing only
    \\r and \\n, but the block is parsed back with str.splitlines(), which also splits on U+2028/U+2029, NEL (U+0085),
    VT, FF and U+001C-1E (common in text pasted from web pages and Word). The user's meaning is silently truncated at
    the separator and the rest can inject lines: '- do not: ...' becomes a new do-not rule, '### S..' a new section."""
    patch = {"sections": {"S02": {"t0": 9.0, "t1": 17.0, "meaning": "the tide answers" + LS + "and the town wakes",
                                  "feel": "calm\x85- do not: show the moon"}}}
    st, raw = _req(srv, "POST", "/api/intent", json.dumps(patch).encode("utf-8"))
    assert st == 200, raw
    back = srv.read_intent()["sections"]["S02"]
    assert "and the town wakes" in back.get("meaning", ""), f"meaning truncated to {back.get('meaning')!r}"
    assert back.get("do_not") == [], f"a do-not rule was injected from the feel text: {back.get('do_not')}"
