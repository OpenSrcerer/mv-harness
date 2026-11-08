"""R-PLATFORM (W1b) finding: published outputs are hard links INTO the stage cache, so an in-place edit of a
song-folder file silently rewrites the cached result, and every later ``mvh analyze`` re-publishes the edit.

D30 publishes public outputs by ``os.link`` from ``.cache/<stage>/<key>/``. Many Windows editors and tools
save in place (truncate + write: Notepad, VS Code, a script doing ``open(p, "r+")``/``"w"``), and an agent
may "fix" ``brief.md``, ``meaning/meaning.json`` or ``lyrics/lines.tsv`` directly. Because the song-folder
file and the cache file are the same file, the cache entry now differs from the sha256 recorded in its
``done.json``; the next run is a cache HIT that re-links the edited bytes, ``mvh status`` says ``done``,
nothing is re-validated, and only ``--force`` heals it (NF1/NF2 broken without any signal).

Expected: the cache is immutable from the song folder (publish by copy, or mark cache files read-only /
verify the recorded sha256 on a hit and re-publish or re-run on mismatch).
"""

from __future__ import annotations

import hashlib

import pytest

from mvh.runner import run as rr


@pytest.fixture
def fx(monkeypatch, skeleton, no_heavy_locks):
    monkeypatch.setenv("MVH_FIXTURE_DIR", str(skeleton))
    return skeleton


def _settings(song, song_dir, **kw):
    return rr.Settings(
        song=song, song_dir=song_dir, slug="tone", progress=lambda m: None, heavy_locks=False, **kw
    )


def test_in_place_edit_of_a_published_file_does_not_change_the_cache(tmp_path, tone48, fx):
    song_dir = tmp_path / "song"
    assert rr.analyze(_settings(tone48, song_dir))["failed"] == []
    published = song_dir / "brief.md"
    original = published.read_bytes()
    with open(published, "r+b") as fh:  # an editor that saves in place
        fh.seek(0)
        fh.write(b"EDITED IN PLACE\n")
        fh.truncate()

    r = rr.Runner(_settings(tone48, song_dir))
    r.run()
    st = r.states["brief"]
    cached = r.cache.stage("brief").dir(st.pre_key) / "brief.md"
    recorded = st.record["outputs"]["brief.md"]["sha256"]
    assert hashlib.sha256(cached.read_bytes()).hexdigest() == recorded, (
        "the cache entry was rewritten through the song folder (hard link); its done.json sha256 no longer "
        f"matches, yet the run reported a cache {st.cache!r} and status {st.status!r}"
    )
    assert published.read_bytes() == original, "the cache hit re-published the edited bytes"
