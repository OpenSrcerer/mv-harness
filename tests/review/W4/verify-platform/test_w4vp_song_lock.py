"""W4 verify-platform r1: W4P-2 (RUNTIME, runner/locks.song_lock) after the w4fix-platform fix.

W4VP-2 (minor): a song.lock left by a power cut is "stale only when its process is gone" (pid liveness only, no age
limit, no process-start check). After a reboot the recorded pid is often reused by an unrelated live process; then
every later `mvh analyze` / `mvh meaning` / `mvh frames` / viewer Re-run on that folder waits FOREVER ("another mvh
run is working on this song folder ... waiting") although no mvh run exists. RUNS.md §6 promises "stale locks clear
themselves" after a power cut. The lock records `started`; a live pid whose process started after that time (or
any pid when the machine booted after it) cannot be the owner.

W4VP-3 (minor): `mvh meaning` and `mvh frames` call runner.analyze without catching SongBusy: with
MVH_SONG_LOCK_TIMEOUT set they die with a traceback (exit 1) instead of the clean message and exit 75 that
`mvh analyze` gives.

Fast: real ingest + loudness on a 3 s tone, no models.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def _env(**kw: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["MVH_OFFLINE"] = "1"
    env.pop("MVH_FIXTURE_DIR", None)
    env.pop("MVH_STAGE_STUBS", None)
    env.update(kw)
    return env


def _mvh(*args: str, **kw: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "mvh.cli", *args], env=_env(**kw), cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


@pytest.fixture()
def folder(tmp_path):
    from mvh import testing

    src = testing.tone(tmp_path / "in" / "tone.flac", seconds=3.0, sr=44100)
    f = tmp_path / "out" / "tone"
    r = _mvh("analyze", str(src), "--out", str(f), "--only", "ingest,loudness")
    assert r.returncode == 0, r.stderr[-800:]
    return f


@pytest.fixture()
def unrelated_live_pid():
    """A live process that is NOT an mvh run (stands in for a pid reused after a reboot)."""
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    try:
        yield p.pid
    finally:
        p.kill()
        p.wait()


def _plant_power_cut_lock(folder: Path, pid: int) -> None:
    with open(folder / ".cache" / "song.lock", "w", encoding="utf-8") as fh:
        json.dump({"owner": "mvh:tone", "pid": pid, "started": "2026-11-01T10:00:00+00:00"}, fh)


def _plant_held_lock(folder: Path, pid: int) -> None:
    """r2: a genuinely held lock, written after its (live) process started, as a real run writes it. The r1 version
    planted the power-cut lock here, which the W4VP-2 fix rightly treats as stale (the r1 test contradicted itself)."""
    from datetime import datetime, timezone

    with open(folder / ".cache" / "song.lock", "w", encoding="utf-8") as fh:
        json.dump({"owner": "mvh:tone", "pid": pid, "started": datetime.now(timezone.utc).isoformat()}, fh)


def test_power_cut_lock_with_a_reused_pid_does_not_block_forever(folder, unrelated_live_pid):
    _plant_power_cut_lock(folder, unrelated_live_pid)
    # bounded here so the test ends; without MVH_SONG_LOCK_TIMEOUT the run waits forever
    r = _mvh("analyze", str(folder), "--only", "ingest,loudness", MVH_SONG_LOCK_TIMEOUT="20")
    assert r.returncode == 0, (
        f"exit {r.returncode}: a lock from 2026-11-01 whose pid now belongs to an unrelated process started later "
        "blocks the folder (with no timeout: forever). " + r.stderr.strip()[-300:]
    )


@pytest.mark.parametrize("verb", [["meaning"], ["frames", "--fps", "24"]])
def test_meaning_and_frames_report_a_busy_folder_cleanly(folder, unrelated_live_pid, verb):
    # a held lock: its pid is alive and started before the lock was written, so it is another run
    _plant_held_lock(folder, unrelated_live_pid)
    r = _mvh(verb[0], str(folder), *verb[1:], MVH_SONG_LOCK_TIMEOUT="3")
    assert "Traceback" not in r.stderr, f"mvh {verb[0]} crashed on a busy folder: " + r.stderr.strip().splitlines()[-1][:300]
    assert r.returncode == 75, f"mvh {verb[0]} exit {r.returncode} (mvh analyze exits 75 when the folder is busy)"
