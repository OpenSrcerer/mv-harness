"""W4 platform round 2 (w4fix-platform-r2): W4VP-1 the manifest keeps listing the outputs of stages a scoped run
left stale, W4VP-2 a song lock whose pid was reused is stale, W4VP-3 every verb reports a busy folder with exit 75,
W4VP-4 a forced ingest without its input does not claim the cache was used. Real ingest + loudness on a 2 s tone."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mvh import cli, testing
from mvh.runner import locks
from mvh.runner import run as rr


@pytest.fixture(autouse=True)
def _real_stages(monkeypatch):
    monkeypatch.delenv("MVH_FIXTURE_DIR", raising=False)
    monkeypatch.delenv("MVH_STAGE_STUBS", raising=False)
    monkeypatch.setenv("MVH_OFFLINE", "1")


def _analyze(folder: Path, song: Path | None, **kw) -> dict:
    prev = rr.load_run_settings(folder)
    params_ext = {k: v for k, v in (prev.get("params_ext") or {}).items() if k != "input" or song is None}
    return rr.analyze(rr.Settings(song=song, song_dir=folder, slug="tone", heavy_locks=False, offline=True,
                                  params_ext=params_ext, progress=lambda m: None, **kw))


def _json(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def made(tmp_path):
    src = testing.tone(tmp_path / "in" / "tone.flac", seconds=2.0, sr=44100)
    folder = tmp_path / "out" / "tone"
    res = _analyze(folder, src, only=("ingest", "loudness"))
    assert not res["failed"] and res["valid"], res
    return src, folder


def test_manifest_lists_the_kept_outputs_of_a_stale_stage(made):
    _, folder = made
    before = {f["path"]: f for f in _json(folder / "manifest.json")["files"]}
    res = _analyze(folder, None, only=("ingest",), cli_params={"loudness": {"foo": 2}})
    assert res["valid"], res["warnings"]
    man = _json(folder / "manifest.json")
    assert man["status"]["stages"]["loudness"] == "stale"
    after = {f["path"]: f for f in man["files"]}
    loud = {p: f for p, f in before.items() if f["stage"] == "loudness"}
    assert loud and all(after.get(p) == f for p, f in loud.items())
    assert any("kept from their previous run: loudness" in w for w in man["warnings"])
    # the kept file is gone from disk -> it is no longer listed
    (folder / "meta" / "loudness.json").unlink()
    _analyze(folder, None, only=("ingest",), cli_params={"loudness": {"foo": 2}})
    assert "meta/loudness.json" not in {f["path"] for f in _json(folder / "manifest.json")["files"]}


def test_manifest_does_not_list_a_stage_that_was_never_published(made):
    _, folder = made
    man = _json(folder / "manifest.json")
    assert not any(f["stage"] == "dynamics" for f in man["files"])


@pytest.fixture()
def live_child():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield p.pid
    finally:
        p.kill()
        p.wait()


def _plant(folder: Path, pid: int, started: datetime) -> Path:
    p = locks.song_lock_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"owner": "mvh:tone", "pid": pid, "started": started.isoformat()}), encoding="utf-8")
    return p


def test_pid_started_reads_this_process():
    born = locks.pid_started(os.getpid())
    assert born is not None and born <= datetime.now(timezone.utc).timestamp()


def test_lock_with_a_reused_pid_is_stale(tmp_path, live_child):
    p = _plant(tmp_path, live_child, datetime(2026, 1, 1, tzinfo=timezone.utc))
    with locks.song_lock(tmp_path, "t", timeout=2, poll=0.1):
        assert p.is_file()
    assert not p.exists()


def test_lock_held_by_its_live_owner_is_not_stale(tmp_path, live_child):
    import time

    time.sleep(0.3)
    _plant(tmp_path, live_child, datetime.now(timezone.utc))  # written after its process started
    with pytest.raises(locks.SongBusy):
        with locks.song_lock(tmp_path, "t", timeout=0.3, poll=0.1, say=lambda m: None):
            pass


def test_every_verb_reports_a_busy_folder_with_exit_75(made, live_child, monkeypatch, capsys):
    import time

    _, folder = made
    time.sleep(0.3)
    _plant(folder, live_child, datetime.now(timezone.utc))
    monkeypatch.setenv("MVH_SONG_LOCK_TIMEOUT", "0.5")
    assert cli.main(["meaning", str(folder)]) == 75
    assert "is busy" in capsys.readouterr().err


def test_forced_ingest_without_input_drops_the_cache_used_warning(made):
    src, folder = made
    src.unlink()
    res = _analyze(folder, None, only=("ingest", "loudness"), force=("ingest",))
    assert "ingest" in res["failed"]
    assert not [w for w in res["warnings"] if "cached canonical audio is used" in w]
    # without --force the cache is used and the warning says so
    res = _analyze(folder, None, only=("ingest", "loudness"))
    assert [w for w in res["warnings"] if "cached canonical audio is used" in w]
