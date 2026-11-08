"""Machine-wide heavy-work slots for mv-harness (HEAVY-WORK PROTOCOL).  Stdlib only; works with any python.

Real model inference / separation may run only while holding one of TWO slots
    %LOCALAPPDATA%\\mvh\\locks\\heavy-0.lock  /  heavy-1.lock
GPU work additionally takes   %LOCALAPPDATA%\\mvh\\locks\\gpu.lock
A lock file is created exclusively (O_CREAT|O_EXCL) and contains {"owner","pid","started"}.
A lock is STALE if its pid is dead or it is older than 3 h; stale locks are removed by the next acquirer.
If both slots are taken, retry every 15 s.  Inside a slot use at most 6 threads.

Python use (context manager):
    import sys; sys.path.insert(0, r"<repo>/scripts")
    from heavy_lock import heavy
    with heavy("env-sep", gpu=False) as slot:        # slot.threads == 6 (env vars already exported)
        ...inference...
    # set the env vars BEFORE importing numpy/torch/onnxruntime:  apply_thread_limits(6)

CLI:
    python scripts/heavy_lock.py status
    python scripts/heavy_lock.py run --owner NAME [--gpu] [--threads 6] [--timeout SEC] -- <command ...>
    python scripts/heavy_lock.py acquire --owner NAME [--gpu]      # prints the slot path; holds until killed (Ctrl+C releases)
    python scripts/heavy_lock.py release <path>                   # manual release of a lock you own
    python scripts/heavy_lock.py cleanup                          # remove stale locks only
"""
from __future__ import annotations

import argparse
import atexit
import contextlib
import ctypes
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOCK_DIR = Path(os.environ.get("MVH_HOME") or (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "mvh")) / "locks"
SLOTS = ("heavy-0.lock", "heavy-1.lock")
GPU_LOCK = "gpu.lock"
STALE_AFTER_S = 3 * 3600
POLL_S = 15
MAX_THREADS = 6
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")


def apply_thread_limits(n: int = MAX_THREADS) -> int:
    """Export the thread env vars (call before importing numpy/torch/numba) and tune torch/ORT if already imported."""
    n = max(1, min(int(n), MAX_THREADS))
    for v in THREAD_VARS:
        os.environ[v] = str(n)
    os.environ["MVH_THREADS"] = str(n)
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            torch.set_num_threads(n)
        except Exception:  # noqa: BLE001
            pass
    return n


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return k32.GetLastError() == 5  # access denied: exists
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  (half-written or unreadable)
        return None


def _is_stale(path: Path) -> bool:
    info = _read(path)
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return False
    if info is None:
        return age > 30  # grace period for a writer that is mid-create
    if not _pid_alive(int(info.get("pid", 0))):
        return True
    try:
        started = datetime.fromisoformat(info["started"]).timestamp()
    except Exception:  # noqa: BLE001
        started = path.stat().st_mtime
    return time.time() - started > STALE_AFTER_S


def _try_create(path: Path, owner: str) -> bool:
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except PermissionError:  # Windows: file pending delete
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"owner": owner, "pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat()}, f)
    return True


def _release(path: Path):
    info = _read(path)
    if info is not None and int(info.get("pid", -1)) != os.getpid():
        return  # not ours
    for k in range(10):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.2 * (k + 1))


def _acquire_one(names, owner, timeout, poll, what):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    warned = False
    while True:
        for n in names:
            p = LOCK_DIR / n
            if p.exists() and _is_stale(p):
                with contextlib.suppress(OSError):
                    p.unlink()
            if _try_create(p, owner):
                return p
        if timeout is not None and time.time() - t0 > timeout:
            raise TimeoutError(f"no free {what} slot after {timeout}s: " + describe())
        if not warned:
            print(f"[heavy_lock] waiting for a {what} slot ({owner}); retry every {poll}s", file=sys.stderr, flush=True)
            warned = True
        time.sleep(poll)


class Slot:
    def __init__(self, paths, threads):
        self.paths, self.threads = paths, threads

    def release(self):
        for p in reversed(self.paths):
            _release(p)
        self.paths = []


def acquire(owner: str, gpu: bool = False, timeout: float | None = None, threads: int = MAX_THREADS, poll: float = POLL_S) -> Slot:
    """Acquire a heavy slot (and the gpu lock when gpu=True).  Order: heavy first, then gpu (never the reverse)."""
    heavy_p = _acquire_one(SLOTS, owner, timeout, poll, "heavy")
    paths = [heavy_p]
    try:
        if gpu:
            paths.append(_acquire_one((GPU_LOCK,), owner, timeout, poll, "gpu"))
    except BaseException:
        for p in paths:
            _release(p)
        raise
    slot = Slot(paths, apply_thread_limits(threads))
    atexit.register(slot.release)
    return slot


@contextlib.contextmanager
def heavy(owner: str, gpu: bool = False, timeout: float | None = None, threads: int = MAX_THREADS):
    slot = acquire(owner, gpu=gpu, timeout=timeout, threads=threads)
    try:
        yield slot
    finally:
        slot.release()


def describe() -> str:
    parts = []
    for n in (*SLOTS, GPU_LOCK):
        p = LOCK_DIR / n
        if p.exists():
            info = _read(p) or {}
            parts.append(f"{n}: owner={info.get('owner')} pid={info.get('pid')} started={info.get('started')}"
                         f"{' STALE' if _is_stale(p) else ''}")
        else:
            parts.append(f"{n}: free")
    return "; ".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("cleanup")
    r = sub.add_parser("run")
    r.add_argument("--owner", required=True)
    r.add_argument("--gpu", action="store_true")
    r.add_argument("--threads", type=int, default=MAX_THREADS)
    r.add_argument("--timeout", type=float)
    r.add_argument("command", nargs=argparse.REMAINDER)
    a_ = sub.add_parser("acquire")
    a_.add_argument("--owner", required=True)
    a_.add_argument("--gpu", action="store_true")
    a_.add_argument("--timeout", type=float)
    rl = sub.add_parser("release")
    rl.add_argument("path")
    a = ap.parse_args(argv)

    if a.cmd == "status":
        for part in describe().split("; "):
            print(part)
        return 0
    if a.cmd == "cleanup":
        n = 0
        for nm in (*SLOTS, GPU_LOCK):
            p = LOCK_DIR / nm
            if p.exists() and _is_stale(p):
                p.unlink(missing_ok=True)
                n += 1
                print("removed stale", p)
        print(f"{n} stale lock(s) removed")
        return 0
    if a.cmd == "release":
        p = Path(a.path)
        if not p.is_absolute():
            p = LOCK_DIR / p
        # a manual release by a different process: only allowed when the lock is stale or owned by a dead pid
        info = _read(p) or {}
        if _pid_alive(int(info.get("pid", 0))) and int(info.get("pid", 0)) != os.getpid():
            print(f"refusing: {p} is held by live pid {info.get('pid')} ({info.get('owner')})", file=sys.stderr)
            return 2
        p.unlink(missing_ok=True)
        return 0
    if a.cmd == "acquire":
        slot = acquire(a.owner, gpu=a.gpu, timeout=a.timeout)
        print(" ".join(str(p) for p in slot.paths), flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            slot.release()
        return 0
    if a.cmd == "run":
        cmd = a.command[1:] if a.command and a.command[0] == "--" else a.command
        if not cmd:
            ap.error("run needs a command after --")
        with heavy(a.owner, gpu=a.gpu, timeout=a.timeout, threads=a.threads) as slot:
            print(f"[heavy_lock] holding {[p.name for p in slot.paths]} threads={slot.threads}", file=sys.stderr, flush=True)
            return subprocess.call(cmd, env=os.environ.copy())
    return 1


if __name__ == "__main__":
    sys.exit(main())
