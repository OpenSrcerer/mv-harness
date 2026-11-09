"""W4 verify-platform r2: W4VP-2 (minor, RUNTIME locks._song_lock_stale) is only partly fixed.

The fix reads the reused pid's creation time (GetProcessTimes) and calls the lock stale when that process started after
the lock was written. When the process cannot be opened (access denied: svchost and other service / SYSTEM processes,
about a third of the live processes on this machine as a normal user), pid_alive() still says "alive" but
pid_started() returns None, and the lock is treated as HELD forever. After a power cut and reboot the early pids go to
exactly these service processes, so a song.lock whose pid now belongs to one blocks every later run on the folder
(RUNS.md promises that stale locks clear themselves). The machine boot time (GetTickCount64, no access needed) settles
it: a lock written before the last boot can have no live owner.

Fast: real ingest + loudness on a 3 s tone, no models. Windows only.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows process access rules")


def _mvh(*args: str, **kw: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["MVH_OFFLINE"] = "1"
    env.pop("MVH_FIXTURE_DIR", None)
    env.pop("MVH_STAGE_STUBS", None)
    env.update(kw)
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "mvh.cli", *args], env=env, cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


def _unopenable_live_pid() -> int | None:
    from mvh.runner import locks

    out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout
    for row in csv.reader(io.StringIO(out)):
        try:
            pid = int(row[1])
        except (IndexError, ValueError):
            continue
        if pid > 8 and locks.pid_alive(pid) and locks.pid_started(pid) is None:
            return pid
    return None


def _boot_time() -> datetime:
    import ctypes

    k32 = ctypes.windll.kernel32
    k32.GetTickCount64.restype = ctypes.c_ulonglong
    return datetime.now(timezone.utc) - timedelta(milliseconds=k32.GetTickCount64())


def test_power_cut_lock_whose_pid_is_now_a_service_process_does_not_block(tmp_path):
    from mvh import testing

    pid = _unopenable_live_pid()
    if pid is None:
        pytest.skip("no live process that this user cannot open")
    src = testing.tone(tmp_path / "in" / "tone.flac", seconds=3.0, sr=44100)
    folder = tmp_path / "out" / "tone"
    r = _mvh("analyze", str(src), "--out", str(folder), "--only", "ingest,loudness")
    assert r.returncode == 0, r.stderr[-800:]
    # a lock written by a run that the power cut killed, one day before the last boot; its pid now belongs to a
    # service process that a normal user cannot query
    started = (_boot_time() - timedelta(days=1)).isoformat()
    with open(folder / ".cache" / "song.lock", "w", encoding="utf-8") as fh:
        json.dump({"owner": "mvh:tone", "pid": pid, "started": started}, fh)
    r = _mvh("analyze", str(folder), "--only", "ingest,loudness", MVH_SONG_LOCK_TIMEOUT="15")
    assert r.returncode == 0, (
        f"exit {r.returncode}: a lock written before the last boot, whose pid {pid} is now an unopenable service "
        "process, blocks the folder (with no timeout: forever). " + r.stderr.strip()[-300:]
    )
