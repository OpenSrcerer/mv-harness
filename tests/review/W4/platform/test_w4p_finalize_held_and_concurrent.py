"""W4 R-PLATFORM, finding W4P-2 (RUNTIME, major): the end of `mvh analyze` is not safe against a held curve file or a
second run on the same folder.

* finalize packs ``curves/<file>.f32`` through ``mvh.contract.curvefile._atomic_write``: a FIXED temp name
  (``core.f32.tmp``) and a bare ``os.replace`` (no retry, no PermissionError handling, unlike ``publish``, W1b M1).
  A reader holding ``curves/core.f32`` (a player, an editor, Defender, a second mvh run) makes the whole analyze exit 1
  with a traceback after every stage finished, and ``curves/core.f32.tmp`` is left in the song folder.
* There is no per-song lock: the viewer's Re-run button plus a terminal ``mvh analyze`` (or two terminals) on one folder
  race. Measured on a Newton copy: both runs exit 1; one crashes in finalize on the shared ``core.f32.tmp``, the other
  fails ``meaning`` ("publish failed: FileNotFoundError" because the other run replaced the cache entry), and the
  manifest then lists meaning / brief / viewer as pending.

Real ingest + loudness on a 3 s tone (seconds, no models).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["MVH_OFFLINE"] = "1"
    env.pop("MVH_FIXTURE_DIR", None)
    env.pop("MVH_STAGE_STUBS", None)
    return env


def _cmd(*args: str) -> list[str]:
    return [sys.executable, "-X", "utf8", "-m", "mvh.cli", "analyze", *args]


@pytest.fixture()
def folder(tmp_path):
    from mvh import testing

    src = testing.tone(tmp_path / "in" / "tone.flac", seconds=3.0, sr=44100)
    f = tmp_path / "out" / "tone"
    r = subprocess.run(_cmd(str(src), "--out", str(f), "--only", "ingest,loudness"), env=_env(), cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert r.returncode == 0, r.stderr[-800:]
    assert (f / "curves" / "core.f32").is_file()
    return f


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing semantics")
def test_held_curve_file_does_not_crash_analyze(folder):
    target = folder / "curves" / "core.f32"
    with open(target, "rb"):  # a reader holding the published curve file
        r = subprocess.run(_cmd(str(folder), "--force", "loudness", "--only", "ingest,loudness"), env=_env(),
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    leftovers = sorted(p.name for p in (folder / "curves").iterdir() if p.name.endswith(".tmp"))
    assert "Traceback" not in r.stderr, "analyze crashed in finalize: " + r.stderr.strip().splitlines()[-1][:300]
    assert r.returncode == 0
    assert not leftovers, f"temp files left in the song folder: {leftovers}"


def test_two_runs_on_one_folder_both_succeed(folder):
    """The second run must wait for (or cleanly refuse during) the first, never corrupt it."""
    procs = [subprocess.Popen(_cmd(str(folder), "--force", "ingest,loudness", "--only", "ingest,loudness"), env=_env(),
                              cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              encoding="utf-8", errors="replace") for _ in range(3)]
    outs = [p.communicate(timeout=600) for p in procs]
    crashed = [i for i, (o, e) in enumerate(outs) if "Traceback" in e]
    assert not crashed, "concurrent run crashed: " + outs[crashed[0]][1].strip().splitlines()[-1][:300]
    with open(folder / "run.json", encoding="utf-8") as fh:
        st = json.load(fh)["stages"]
    assert st["ingest"]["status"] == "done" and st["loudness"]["status"] == "done", {k: st[k]["status"] for k in ("ingest", "loudness")}
    leftovers = sorted(p.name for p in folder.rglob("*.tmp"))
    assert not leftovers, f"temp files left: {leftovers}"
