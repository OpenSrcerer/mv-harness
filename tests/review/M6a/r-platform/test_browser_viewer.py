"""R-PLATFORM review of M6a, real-browser checks (headless Edge/Chrome over the DevTools protocol, see cdp_viewer.mjs).

Each test is the evidence of one finding in docs/build/reports/r-platform-m6a.md and FAILS until the viewer is fixed.
"""

from __future__ import annotations

import json

import pytest
from rp_support import build_song_folder, drive

pytestmark = pytest.mark.usefixtures("browser_ok")


def test_playhead_follows_audio_after_pressing_play(served, tmp_path):
    """F-PLAYHEAD: pressing Play (button or Space) does not start the render loop. The audio plays but the playhead, the
    clock and every lane stay frozen until the pointer happens to move over a lane (setPlaying never calls requestDraw)."""
    res = drive(served.url, "playhead", tmp_path / "prof")
    assert res["state"] == "ready", res
    p = res["play"]
    assert p["playing"] and not p["paused"] and p["currentTime"] > 0.8, f"audio did not play in the test browser: {p}"
    assert abs(p["viewT"] - p["currentTime"]) < 0.3, (
        f"playhead not synced to audio: audio at {p['currentTime']:.2f} s, viewer time {p['viewT']:.2f} s, clock {p['clock']!r}")


def test_missing_optional_visemes_does_not_break_a_lane(tmp_path, synth_ok):
    """F-OPTIONAL-EVENTS: lipsync/visemes.json is optional (catalog required=False; lipsync is a Should). When it is
    absent the manifest does not list it, the viewer never ensures it, and the Vocal range lane throws on every draw
    ('events:visemes' is not loaded) -> 'lane error' painted in the lane + console errors. Served (edit) mode."""
    from mvh.stages.viewer.server import make_server

    folder = build_song_folder(tmp_path / "no visemes", exclude=("lipsync/",))
    srv = make_server(folder, port=0, idle_timeout=0, allow_rerun=False).start()
    try:
        res = drive(srv.url, "errors", tmp_path / "prof")
    finally:
        srv.shutdown()
    assert res["state"] == "ready", res
    assert res["laneErrors"] == [], f"lane errors: {res['laneErrors'][:2]}"
    assert not [e for e in res["consoleErrors"] if "visemes" in e], res["consoleErrors"][:3]


def test_file_mode_loads_when_an_events_file_is_absent(tmp_path, synth_ok):
    """F-FATAL-ABSENT: opened from the disk (file://), a song folder whose stages did not write events/singing.json (the
    real-* W0 fixtures, a degraded/partial run) shows only 'The viewer could not load this song': buildModel reads
    items('singing') for a name the inlined manifest does not list. The stage still reports status ok."""
    folder = build_song_folder(tmp_path / "no singing", exclude=("events/singing.json",))
    res = drive((folder / "viewer.html").as_uri(), "errors", tmp_path / "prof")
    assert res["state"] == "ready", f"viewer did not load from file://: {res.get('fatal')}"


def test_failed_save_is_reported_and_not_shown_as_applied(served, tmp_path):
    """F-SAVE-LOST: when POST api/overrides fails at the network level (server stopped by Ctrl+C or its idle timeout,
    or the atomic write giving up on a locked overrides.json and dropping the connection), Edit.save() throws before
    its error branch: the edit stays applied in the page (grid preview), the bar says 'saving…' forever and no error
    is shown, while overrides.json was never written. The user believes the correction is saved."""
    res = drive(served.url, "save-offline", tmp_path / "prof")
    assert res["state"] == "ready", res
    assert res["clicked"], "the +10 ms beat-offset button was not found in the Edit tab"
    assert not (served.folder / "overrides.json").exists()
    a = res["after"]
    shown = json.dumps(a["ovr"] or {})
    errors = [t for t in a["toasts"] if "bad" in t or "warn" in t]
    assert "beat_offset_s" not in shown and errors, (
        f"unsaved edit shown as applied without an error: ovr={shown} bar={a['bar']!r} toasts={a['toasts']}")
