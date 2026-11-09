"""Fixtures for the R-PLATFORM review tests of M6a (viewer)."""

from __future__ import annotations

import pytest
from rp_support import SYNTH, build_song_folder, find_browser, find_node


@pytest.fixture(scope="session")
def synth_ok() -> None:
    if not (SYNTH / ".done.json").is_file():
        pytest.skip("tests/contract/synth is not built")


@pytest.fixture(scope="session")
def browser_ok(synth_ok) -> None:
    if not find_node() or not find_browser():
        pytest.skip("needs node and a Chromium browser (Edge or Chrome) for the real-browser checks")


@pytest.fixture()
def served(tmp_path, synth_ok):
    """A full synthetic song folder (path with spaces and non-ASCII) served by mvh view in edit mode."""
    from mvh.stages.viewer.server import make_server

    folder = build_song_folder(tmp_path / "sông ☃ folder")
    srv = make_server(folder, port=0, idle_timeout=0, allow_rerun=False).start()
    yield srv
    srv.shutdown()
