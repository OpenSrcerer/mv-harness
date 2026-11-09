"""W4 platform fixes (w4fix-platform): kept curves of stale stages (W4D-1), held curve files (W4P-2), the per-song
lock (W4P-2) and content-keyed song input (W4P-1). Real ingest + loudness on a 2 s tone; seconds, no models."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mvh import testing
from mvh.runner import finalize, locks
from mvh.runner import run as rr


@pytest.fixture(autouse=True)
def _real_stages(monkeypatch):
    monkeypatch.delenv("MVH_FIXTURE_DIR", raising=False)
    monkeypatch.delenv("MVH_STAGE_STUBS", raising=False)
    monkeypatch.setenv("MVH_OFFLINE", "1")


def _settings(folder: Path, song: Path | None, **kw) -> rr.Settings:
    prev = rr.load_run_settings(folder)
    params_ext = {k: v for k, v in (prev.get("params_ext") or {}).items() if k != "input" or song is None}
    return rr.Settings(song=song, song_dir=folder, slug="tone", heavy_locks=False, offline=True,
                       params_ext=params_ext, progress=lambda m: None, **kw)


def _analyze(folder: Path, song: Path | None, **kw) -> dict:
    return rr.analyze(_settings(folder, song, **kw))


def _stages(folder: Path) -> dict:
    with open(folder / "run.json", encoding="utf-8") as fh:
        return json.load(fh)["stages"]


@pytest.fixture()
def made(tmp_path):
    src = testing.tone(tmp_path / "in" / "a song.flac", seconds=2.0, sr=44100)
    folder = tmp_path / "out" / "tone"
    res = _analyze(folder, src, only=("ingest", "loudness"))
    assert not res["failed"] and res["valid"], res
    return src, folder


def test_held_curve_file_with_new_bytes_keeps_its_previous_version_and_index(made, monkeypatch):
    _, folder = made
    core = folder / "curves" / "core.f32"
    with open(folder / "curves" / "index.json", encoding="utf-8") as fh:
        old_idx = json.load(fh)
    core.write_bytes(b"\0" * core.stat().st_size)  # the folder copy differs from what finalize will pack
    real = finalize.atomic.write_bytes

    def held(path, data):
        if Path(path).name == "core.f32":
            raise PermissionError(13, "held by a reader")
        return real(path, data)

    monkeypatch.setattr(finalize.atomic, "write_bytes", held)
    res = _analyze(folder, None, only=("ingest", "loudness"), force=("loudness",))
    assert not res["failed"]
    assert any("core.f32 is open in another program" in w for w in res["warnings"])
    with open(folder / "curves" / "index.json", encoding="utf-8") as fh:
        idx = json.load(fh)
    assert idx["files"]["core"] == old_idx["files"]["core"]
    assert [c for c in idx["channels"] if c["file"] == "core"] == [c for c in old_idx["channels"] if c["file"] == "core"]
    assert not [p.name for p in (folder / "curves").iterdir() if p.name.endswith(".tmp")]


def test_scoped_run_keeps_the_curves_of_a_stale_stage(made):
    _, folder = made
    before = (folder / "curves" / "core.f32").read_bytes()
    res = _analyze(folder, None, only=("ingest",), cli_params={"loudness": {"foo": 2}})
    assert (folder / "curves" / "core.f32").read_bytes() == before
    assert any("kept from their previous run: loudness" in w for w in res["warnings"])


def test_song_lock_is_reentrant_and_removes_a_dead_owner(tmp_path):
    p = locks.song_lock_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"owner": "dead", "pid": 2**22 + 12345, "started": "2026-01-01T00:00:00+00:00"}),
                 encoding="utf-8")
    with locks.song_lock(tmp_path, "t", timeout=5):
        with locks.song_lock(tmp_path, "t", timeout=0):  # same process: re-entered, no wait
            assert p.is_file()
        assert p.is_file()
    assert not p.exists()


def test_song_lock_held_by_a_live_process_times_out(tmp_path):
    p = locks.song_lock_path(tmp_path)
    p.parent.mkdir(parents=True)
    # written after this (live) process started: its real owner (W4VP-2 treats a lock older than its pid's
    # process as a reused pid)
    from datetime import datetime, timezone

    p.write_text(json.dumps({"owner": "other", "pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat()}),
                 encoding="utf-8")
    msgs: list[str] = []
    with pytest.raises(locks.SongBusy):
        with locks.song_lock(tmp_path, "t", timeout=0.3, poll=0.1, say=msgs.append):
            pass
    assert msgs and "waiting" in msgs[0]
    assert p.is_file()  # never removes a live owner's lock


def test_ingest_key_ignores_the_file_name(made, tmp_path):
    src, folder = made
    key0 = _stages(folder)["ingest"]["key"]
    other = testing.tone(tmp_path / "x" / "renamed.flac", seconds=2.0, sr=44100)
    assert other.read_bytes() == src.read_bytes()
    _analyze(folder, other, only=("ingest", "loudness"))
    st = _stages(folder)
    assert st["ingest"]["key"] == key0 and st["ingest"]["cache"] == "hit" and st["loudness"]["cache"] == "hit"


def test_legacy_named_key_is_reused_without_a_cascade(made):
    """A folder made before W4P-1 has an ingest entry keyed on {sha256, name}: same content -> same entry/key."""
    _, folder = made
    st0 = _stages(folder)
    sc = folder / ".cache" / "ingest"
    with open(sc / "latest.json", encoding="utf-8") as fh:
        lat = json.load(fh)
    legacy_pre = "legacy" + lat["pre_key"][6:]
    (sc / lat["pre_key"]).rename(sc / legacy_pre)
    lat["pre_key"] = legacy_pre
    lat["key_inputs"]["external"]["input"] = {**lat["key_inputs"]["external"]["input"], "name": "old name.flac"}
    (sc / "latest.json").write_text(json.dumps(lat), encoding="utf-8")
    _analyze(folder, None, only=("ingest", "loudness"))
    st = _stages(folder)
    assert st["ingest"]["status"] == "done" and st["ingest"]["key"] == st0["ingest"]["key"]
    assert st["loudness"]["cache"] == "hit"
    # a forced ingest re-runs into the established entry (for a real legacy entry its key IS that pre_key, so
    # nothing downstream re-runs; this fake entry's recorded key differs from its directory name)
    _analyze(folder, None, only=("ingest",), force=("ingest",))
    st = _stages(folder)
    assert st["ingest"]["cache"] == "forced" and st["ingest"]["key"] == legacy_pre
    assert sorted(p.name for p in sc.iterdir() if p.is_dir()) == [legacy_pre]


def test_missing_input_reuses_the_cache_and_a_forced_ingest_names_the_relink_command(made):
    src, folder = made
    src.unlink()
    res = _analyze(folder, None, only=("ingest", "loudness"))
    st = _stages(folder)
    assert st["ingest"]["status"] == "done" and st["loudness"]["cache"] == "hit"
    assert any("is missing" in w and "a song.flac" in w for w in res["warnings"])
    res = _analyze(folder, None, only=("ingest", "loudness"), force=("ingest",))
    st = _stages(folder)
    assert st["ingest"]["status"] == "failed"
    assert "Relink it: mvh analyze" in " ".join(st["ingest"]["warnings"])


def test_pack_copies_the_web_subset_only(made, tmp_path):
    from mvh import cli

    _, folder = made
    (folder / "stems").mkdir(exist_ok=True)
    (folder / "stems" / "drums.flac").write_bytes(b"x")
    (folder / "viewer.html").write_text("<html></html>", encoding="utf-8")
    dest = tmp_path / "site" / "public" / "song"
    assert cli.main(["pack", str(folder), str(dest)]) == 0
    got = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    assert {"manifest.json", "curves/core.f32", "curves/index.json", "lib/mvh.js"} <= got
    assert not any(g.startswith((".cache", "stems/")) or g == "viewer.html" for g in got)
    assert cli.main(["pack", str(folder), str(dest)]) == 2  # not empty without --force
    assert cli.main(["pack", str(folder), str(folder / "sub")]) == 2  # never inside the song folder


def test_relinking_a_renamed_song_keeps_the_folder_slug(made, tmp_path):
    from mvh import cli

    src, folder = made
    other = tmp_path / "x" / "Completely Different Name.flac"
    other.parent.mkdir(parents=True)
    other.write_bytes(src.read_bytes())
    assert cli.main(["analyze", str(other), "--out", str(folder), "--only", "ingest,loudness", "--no-heavy-locks"]) == 0
    with open(folder / "manifest.json", encoding="utf-8") as fh:
        assert json.load(fh)["slug"] == "tone"
    assert _stages(folder)["loudness"]["cache"] == "hit"
    assert rr.load_run_settings(folder)["params_ext"]["input"] == str(other.resolve())
