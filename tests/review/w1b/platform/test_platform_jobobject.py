"""R-PLATFORM (W1b) verification: the sep worker and its ffmpeg grandchild die with their parent (Job Object
KILL_ON_JOB_CLOSE, PLAN §3.3). This is a regression test that PASSES today; it is kept so a later refactor of
``mvh.io.proc`` / ``sepworker`` cannot silently lose the kill-on-close behaviour.

Chain under test: parent python (plays the stage child, main env) -> ``sepworker.run_worker`` -> the real
sep-cpu venv python running ``-m mvh.worker`` -> an ffmpeg it starts itself. The parent is killed with
TerminateProcess mid-job; neither the worker python nor the ffmpeg may survive.

The worker handler is a test-only stage package in a COPY of ``src/mvh`` under tmp_path (``root=``), and
``envs/sep/.venv-cpu`` of that fake root is a directory junction to the real venv (no admin rights needed).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from mvh.runner import sepworker
from mvh.runner.locks import pid_alive

REPO = Path(__file__).resolve().parents[4]

SLEEPER = textwrap.dedent(
    """
    import json, os, subprocess, sys, time
    from pathlib import Path

    def run_job(job, out_dir):
        ff = os.environ["MVH_FFMPEG"]
        p = subprocess.Popen([ff, "-nostdin", "-v", "error", "-re", "-f", "lavfi", "-i", "anullsrc",
                              "-t", "600", "-f", "null", "-"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(job["params"]["pidfile"]).write_text(
            json.dumps({"worker": os.getpid(), "ffmpeg": p.pid}), encoding="utf-8")
        time.sleep(600)
        return {}
    """
)

PARENT = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from mvh.runner import sepworker
    sepworker.run_worker("zz_r_platform_sleeper", stage_version="0.0.0",
                         params={"pidfile": sys.argv[3]}, inputs={}, scratch=Path(sys.argv[4]),
                         threads=1, variants=("cpu",), hold_slot=False, root=Path(sys.argv[2]))
    """
)


def _fake_root(tmp_path: Path) -> Path:
    import _winapi

    real_py = sepworker.sep_python("cpu")
    if real_py is None:
        pytest.skip("sep-cpu venv not built")
    root = tmp_path / "fake root ü"
    shutil.copytree(REPO / "src" / "mvh", root / "src" / "mvh", ignore=shutil.ignore_patterns("__pycache__"))
    pkg = root / "src" / "mvh" / "stages" / "zz_r_platform_sleeper"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "worker.py").write_text(SLEEPER, encoding="utf-8")
    (root / "envs" / "sep").mkdir(parents=True)
    _winapi.CreateJunction(str(real_py.parents[1]), str(root / "envs" / "sep" / ".venv-cpu"))
    return root


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Objects")
def test_killing_the_parent_kills_worker_and_its_ffmpeg(tmp_path):
    root = _fake_root(tmp_path)
    pidfile = tmp_path / "pids.json"
    script = tmp_path / "parent.py"
    script.write_text(PARENT, encoding="utf-8")
    parent = subprocess.Popen(
        [sys.executable, str(script), str(REPO / "src"), str(root), str(pidfile), str(tmp_path / "scr")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pids: dict = {}
    try:
        t0 = time.time()
        while not pidfile.is_file() and time.time() - t0 < 60:
            assert parent.poll() is None, "parent exited before the worker started"
            time.sleep(0.2)
        assert pidfile.is_file(), "the worker never started"
        time.sleep(0.3)
        pids = json.loads(pidfile.read_text(encoding="utf-8"))
        assert pid_alive(pids["worker"]) and pid_alive(pids["ffmpeg"])
        parent.kill()  # TerminateProcess: no cleanup code runs in the parent
        parent.wait(10)
        t0 = time.time()
        while time.time() - t0 < 10 and (pid_alive(pids["worker"]) or pid_alive(pids["ffmpeg"])):
            time.sleep(0.2)
        assert not pid_alive(pids["worker"]), "orphan sep worker python survived its parent"
        assert not pid_alive(pids["ffmpeg"]), "orphan ffmpeg (started by the worker) survived"
    finally:
        if parent.poll() is None:
            parent.kill()
        for pid in pids.values():
            if pid_alive(pid):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        junction = root / "envs" / "sep" / ".venv-cpu"
        if os.path.isjunction(junction):
            os.rmdir(junction)  # removes the link only, never the real venv
