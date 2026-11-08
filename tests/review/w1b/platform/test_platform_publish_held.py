"""R-PLATFORM (W1b) finding: publishing a re-run stage while a reader holds one of its published files crashes
``mvh analyze`` and leaves temp files in the song folder.

On Windows a reader that opened a file without FILE_SHARE_DELETE (CPython ``open()``, many players and
editors; e.g. the user listening to ``audio/mix.flac`` or a stem, or a video agent's dev server) makes
``os.replace`` onto that path fail. ``Runner.publish`` retries (~13 s) and raises; ``Runner.run`` turns that
into a validation failure and calls ``unpublish``, which is OUTSIDE the try block and raises the same
PermissionError out of ``Runner.run`` -> ``analyze`` crashes with a traceback, finalize never runs (no
manifest/run.json update), the ``.<name>.<hex>.lnk`` temp link stays in the song folder, and ``failed.json``
is written for a key whose cache entry is actually complete.

Expected (PLAN §3.3 "atomic, retried with backoff on PermissionError"): a held published file must not crash
the run; the stage result stays cached, the run finishes (the stage or file reported with a warning), and no
temp files are left in the song folder.
"""

from __future__ import annotations

import pytest

from mvh.io import atomic
from mvh.runner import run as rr


@pytest.fixture
def fx(monkeypatch, skeleton, no_heavy_locks):
    monkeypatch.setenv("MVH_FIXTURE_DIR", str(skeleton))
    return skeleton


def _settings(song, song_dir, **kw):
    return rr.Settings(
        song=song, song_dir=song_dir, slug="tone", progress=lambda m: None, heavy_locks=False, **kw
    )


def test_rerun_while_a_published_file_is_open_does_not_crash(tmp_path, tone48, fx, monkeypatch):
    monkeypatch.setattr(atomic, "_sleep", lambda k: None)  # keep the 12 retries, skip the ~13 s of backoff
    song_dir = tmp_path / "song"
    res = rr.analyze(_settings(tone48, song_dir))
    assert res["failed"] == []

    held = song_dir / "audio" / "mix.flac"
    fh = open(held, "rb")  # a reader (player, viewer, agent) keeps the soundtrack open
    try:
        try:
            res = rr.analyze(_settings(tone48, song_dir, force=("ingest",)))
            crashed = None
        except PermissionError as e:  # what happens today
            crashed = e
    finally:
        fh.close()

    leftovers = sorted(p.name for p in (song_dir / "audio").iterdir() if p.name.endswith(".lnk"))
    assert crashed is None, f"mvh analyze crashed while audio/mix.flac was open: {crashed!r}"
    assert leftovers == [], f"temp links left in the song folder: {leftovers}"
