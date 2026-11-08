# ruff: noqa: E501  (long lines)
"""R-PLATFORM review of M6a, ROUND 2 (r-platform-m6a-r2): new majors found after the round-1 fixes.

Each test is the evidence of one finding in docs/build/reports/r-platform-m6a-r2.md and FAILS until the viewer is fixed.
"""

from __future__ import annotations

import http.client
import json

import pytest
from rp_support import build_song_folder, drive, find_browser, find_node

# Windows "ANSI" (cp1252) text, as saved by older editors / Notepad's ANSI option, with CRLF line ends.
CP1252_INTENT = "# What this song means to me\r\n\r\nA café by the harbour – “lanterns” at night.\r\n".encode("cp1252")


def _get(srv, path: str):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=20)
    try:
        c.request("GET", path, headers={"Host": f"127.0.0.1:{srv.port}"})
        r = c.getresponse()
        return r.status, r.read()
    except (http.client.HTTPException, ConnectionError) as e:
        return None, repr(e).encode()
    finally:
        c.close()


def _replace(p, data: bytes) -> None:
    """Write a new file (never through a hard link into tests/contract)."""
    if p.exists():
        p.unlink()
    p.write_bytes(data)


@pytest.mark.parametrize("enc", ["cp1252", "utf-16"])
def test_intent_md_in_a_windows_encoding_does_not_kill_the_api(tmp_path, synth_ok, enc):
    """F-R2-INTENT-ENC (server): meaning/intent.md is the USER's own file. When it is not UTF-8 (Notepad 'ANSI' or
    'UTF-16 LE'), read_intent() raises UnicodeDecodeError inside the handler: GET /api/intent gets no response at all
    (connection closed, traceback on stderr). It must answer (e.g. 200 with an error, or 422) so the page can say why."""
    from mvh.stages.viewer.server import make_server

    folder = build_song_folder(tmp_path / "enc song")
    data = CP1252_INTENT if enc == "cp1252" else "# Mine\r\n\r\nA café.\r\n".encode("utf-16")
    _replace(folder / "meaning" / "intent.md", data)
    srv = make_server(folder, port=0, idle_timeout=0, allow_rerun=False).start()
    try:
        status, body = _get(srv, "/api/intent")
    finally:
        srv.shutdown()
    assert status is not None, f"GET /api/intent with a {enc} intent.md got no HTTP response: {body[:120]!r}"
    assert (folder / "meaning" / "intent.md").read_bytes() == data, "the user's intent.md was modified"


@pytest.mark.usefixtures("browser_ok")
def test_edit_mode_loads_when_intent_md_is_not_utf8(tmp_path, synth_ok):
    """F-R2-INTENT-ENC (browser): with a cp1252 meaning/intent.md the whole edit-mode viewer (`mvh view`) shows
    'The viewer could not load this song / TypeError: Failed to fetch' (boot awaits api/intent). Nothing else in the
    folder is wrong; file:// mode of the same folder loads."""
    from mvh.stages.viewer.server import make_server

    folder = build_song_folder(tmp_path / "sông ansi intent")
    _replace(folder / "meaning" / "intent.md", CP1252_INTENT)
    srv = make_server(folder, port=0, idle_timeout=0, allow_rerun=False).start()
    try:
        res = drive(srv.url, "errors", tmp_path / "prof")
    finally:
        srv.shutdown()
    assert res["state"] == "ready", f"edit-mode viewer did not load with a non-UTF-8 intent.md: {res.get('fatal')!r}"


@pytest.mark.usefixtures("browser_ok")
def test_undo_restores_the_previous_state_each_time(served, tmp_path):
    """F-R2-UNDO: Edit.undo() pops the history entry it restores, and then pops ANOTHER one (`st.history.pop()` after
    `await save(...)`, while save() never pushes). From the second Undo on, every Undo jumps two steps back and
    overrides.json is rewritten with a state the user never asked for (a correction is silently discarded).
    Three +10 ms edits (10, 20, 30 ms) then two Undos must leave 10 ms on disk."""
    assert find_node() and find_browser()
    res = drive(served.url, "undo", tmp_path / "prof")
    assert res["state"] == "ready", res
    steps = res["steps"]
    assert all(s["clicked"] for s in steps), f"a button was not found / was disabled: {json.dumps(steps)}"
    edits = [s["disk"] for s in steps[:3]]
    assert edits == [0.01, 0.02, 0.03], f"the +10 ms edits did not save as expected: {edits}"
    undos = [s["disk"] for s in steps[3:]]
    assert undos == [0.02, 0.01], f"Undo restored the wrong states: after 10/20/30 ms, Undo, Undo gave {undos} (expected [0.02, 0.01])"
