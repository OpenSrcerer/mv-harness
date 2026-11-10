r"""Machine-wide heavy-work slots, compatible with ``scripts/heavy_lock.py`` (same files, same JSON, same
rules).

Two slots ``%LOCALAPPDATA%\mvh\locks\heavy-0.lock`` / ``heavy-1.lock``, plus ``gpu.lock`` for GPU work. A
lock file
is created exclusively (O_CREAT|O_EXCL) and holds ``{"owner", "pid", "started"}`` (ISO 8601, UTC). A lock is
stale
when its pid is dead or it is older than 3 h; the next acquirer removes stale locks. The heavy slot is always
taken before the gpu lock. At most 6 threads inside a slot.

Stdlib only (the sep worker may import it).
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

__all__ = [
    "SLOTS",
    "GPU_LOCK",
    "STALE_AFTER_S",
    "MAX_THREADS",
    "Slot",
    "lock_dir",
    "acquire",
    "heavy",
    "status",
    "cleanup",
    "pid_alive",
    "pid_started",
    "is_stale",
    "SONG_LOCK",
    "SongBusy",
    "song_lock",
    "song_lock_path",
]

SLOTS = ("heavy-0.lock", "heavy-1.lock")
GPU_LOCK = "gpu.lock"
STALE_AFTER_S = 3 * 3600
POLL_S = 2.0   # W3 (M3a CR): 15 s waiters starved behind 2 s re-acquirers (separate_fast waited 31 min)
MAX_THREADS = 6


def lock_dir() -> Path:
    base = os.environ.get("MVH_HOME") or str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "mvh")
    return Path(base) / "locks"


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return k32.GetLastError() == 5  # access denied: the process exists
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


def pid_started(pid: int) -> float | None:
    """Creation time of process ``pid`` (epoch seconds), or None when it cannot be read."""
    if pid <= 0:
        return None
    if os.name == "nt":
        from ctypes import wintypes

        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            ft = [wintypes.FILETIME() for _ in range(4)]
            if not k32.GetProcessTimes(wintypes.HANDLE(h), *(ctypes.byref(f) for f in ft)):
                return None
            t = (ft[0].dwHighDateTime << 32) | ft[0].dwLowDateTime  # 100 ns since 1601-01-01
            return t / 1e7 - 11644473600.0 if t else None
        finally:
            k32.CloseHandle(wintypes.HANDLE(h))
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            ticks = int(fh.read().rsplit(")", 1)[1].split()[19])
        with open("/proc/stat", encoding="utf-8") as fh:
            btime = next(int(ln.split()[1]) for ln in fh if ln.startswith("btime "))
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration, AttributeError):
        return None


#: a lock's process must have started before the lock was written; this much clock slack is allowed
PID_REUSE_SLACK_S = 2.0


def boot_time() -> float | None:
    """Epoch seconds of the last machine boot (needs no process access), or None."""
    try:
        if os.name == "nt":
            k32 = ctypes.windll.kernel32
            k32.GetTickCount64.restype = ctypes.c_ulonglong
            return time.time() - k32.GetTickCount64() / 1000.0
        with open("/proc/stat", encoding="utf-8") as fh:
            return float(next(int(ln.split()[1]) for ln in fh if ln.startswith("btime ")))
    except (OSError, ValueError, StopIteration, AttributeError):
        return None


def _read(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def is_stale(path: Path) -> bool:
    info = _read(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return False
    if info is None:
        return time.time() - mtime > 30  # grace period for a writer that is mid-create
    if not pid_alive(int(info.get("pid", 0) or 0)):
        return True
    try:
        started = datetime.fromisoformat(str(info["started"])).timestamp()
    except (KeyError, ValueError):
        started = mtime
    return time.time() - started > STALE_AFTER_S


def _try_create(path: Path, owner: str) -> bool:
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):  # PermissionError: Windows "delete pending"
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"owner": owner, "pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat()}, fh)
    return True


def _release(path: Path) -> None:
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


def _acquire_one(
    names: tuple[str, ...],
    owner: str,
    timeout: float | None,
    poll: float,
    what: str,
    cancel: threading.Event | None = None,
) -> Path:
    d = lock_dir()
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    warned = False
    while True:
        for n in names:
            p = d / n
            if p.exists() and is_stale(p):
                with contextlib.suppress(OSError):
                    p.unlink()
            if _try_create(p, owner):
                return p
        if timeout is not None and time.time() - t0 > timeout:
            raise TimeoutError(f"no free {what} slot after {timeout}s: {status_line()}")
        if cancel is not None and cancel.is_set():
            raise TimeoutError(f"cancelled while waiting for a {what} slot")
        if not warned:
            print(
                f"[mvh.locks] waiting for a {what} slot ({owner}); retry every {poll:g}s",
                file=sys.stderr,
                flush=True,
            )
            warned = True
        if cancel is not None:
            cancel.wait(poll)
        else:
            time.sleep(poll)


@dataclass
class Slot:
    owner: str
    paths: list[Path] = field(default_factory=list)
    threads: int = MAX_THREADS

    @property
    def gpu(self) -> bool:
        return any(p.name == GPU_LOCK for p in self.paths)

    def release(self) -> None:
        for p in reversed(self.paths):
            _release(p)
        self.paths = []

    def __enter__(self) -> "Slot":
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def acquire(
    owner: str,
    gpu: bool = False,
    timeout: float | None = None,
    threads: int = MAX_THREADS,
    poll: float = POLL_S,
    cancel: threading.Event | None = None,
) -> Slot:
    """A heavy slot (and the gpu lock when ``gpu``): heavy first, then gpu, never the reverse."""
    heavy_p = _acquire_one(SLOTS, owner, timeout, poll, "heavy", cancel)
    paths = [heavy_p]
    try:
        if gpu:
            paths.append(_acquire_one((GPU_LOCK,), owner, timeout, poll, "gpu", cancel))
    except BaseException:
        for p in paths:
            _release(p)
        raise
    return Slot(owner, paths, max(1, min(int(threads), MAX_THREADS)))


@contextlib.contextmanager
def heavy(
    owner: str,
    gpu: bool = False,
    timeout: float | None = None,
    threads: int = MAX_THREADS,
    poll: float = POLL_S,
) -> Iterator[Slot]:
    slot = acquire(owner, gpu=gpu, timeout=timeout, threads=threads, poll=poll)
    try:
        yield slot
    finally:
        slot.release()


def status() -> dict[str, dict | None]:
    out: dict[str, dict | None] = {}
    for n in (*SLOTS, GPU_LOCK):
        p = lock_dir() / n
        if p.exists():
            info = dict(_read(p) or {})
            info["stale"] = is_stale(p)
            out[n] = info
        else:
            out[n] = None
    return out


def status_line() -> str:
    parts = []
    for n, info in status().items():
        if info is None:
            parts.append(f"{n}: free")
        else:
            stale = " STALE" if info.get("stale") else ""
            parts.append(f"{n}: owner={info.get('owner')} pid={info.get('pid')}{stale}")
    return "; ".join(parts)


def cleanup() -> int:
    n = 0
    for nm in (*SLOTS, GPU_LOCK):
        p = lock_dir() / nm
        if p.exists() and is_stale(p):
            with contextlib.suppress(OSError):
                p.unlink()
                n += 1
    return n


# ------------------------------------------------------------------------------------------- per-song lock
SONG_LOCK = "song.lock"
_held_songs: dict[str, int] = {}
_held_guard = threading.Lock()


class SongBusy(RuntimeError):
    """Another mvh process holds the song folder's lock and the wait timed out."""


def song_lock_path(song_dir: Path | str) -> Path:
    return Path(song_dir) / ".cache" / SONG_LOCK


def _song_lock_stale(path: Path) -> bool:
    """A song lock is stale when its process is gone (a song run can wait hours for heavy slots, so there is
    no age limit, unlike the machine-wide slots), or when its pid now belongs to a process that started after
    the lock was written (W4VP-2: a pid reused after a power cut or reboot can never be the owner). An
    unreadable lock gets a 30 s grace for its writer."""
    info = _read(path)
    if info is None:
        try:
            return time.time() - path.stat().st_mtime > 30
        except FileNotFoundError:
            return False
    pid = int(info.get("pid", 0) or 0)
    if not pid_alive(pid):
        return True
    try:
        locked = datetime.fromisoformat(str(info["started"])).timestamp()
    except (KeyError, ValueError, TypeError):
        return False
    born = pid_started(pid)
    if born is None:  # the process cannot be queried (a service / SYSTEM process): the boot time settles it
        boot = boot_time()
        return boot is not None and locked < boot - PID_REUSE_SLACK_S
    return born > locked + PID_REUSE_SLACK_S


def _song_timeout() -> float | None:
    v = os.environ.get("MVH_SONG_LOCK_TIMEOUT", "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


@contextlib.contextmanager
def song_lock(
    song_dir: Path | str,
    owner: str,
    timeout: float | None = None,
    poll: float = 1.0,
    say=None,
) -> Iterator[Path]:
    """W4P-2: one mvh run per song folder at a time (``<song>/.cache/song.lock``).

    ``mvh analyze``, ``mvh meaning``, ``mvh frames`` and the viewer's Re-run all go through the runner, which
    takes this lock: a second run on the same folder waits for the first (a message on stderr) instead of
    racing it. Reentrant within one process. ``timeout`` (or MVH_SONG_LOCK_TIMEOUT seconds) bounds the wait
    and raises SongBusy. A lock whose process died (crash, power cut), or whose pid was reused since, is
    removed by the next run."""
    path = song_lock_path(song_dir)
    key = os.path.normcase(str(path.resolve()))
    with _held_guard:
        if _held_songs.get(key):
            _held_songs[key] += 1
            reentered = True
        else:
            reentered = False
    if reentered:
        try:
            yield path
        finally:
            with _held_guard:
                _held_songs[key] -= 1
        return
    if timeout is None:
        timeout = _song_timeout()
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    warned = False
    while True:
        if path.exists() and _song_lock_stale(path):
            with contextlib.suppress(OSError):
                path.unlink()
        if _try_create(path, owner):
            break
        info = _read(path) or {}
        if timeout is not None and time.time() - t0 > timeout:
            raise SongBusy(
                f"{Path(song_dir)} is busy: another mvh run (pid {info.get('pid')}, {info.get('owner')}, "
                f"since {info.get('started')}) holds {path}; try again when it has finished"
            )
        if not warned:
            msg = (f"another mvh run is working on this song folder (pid {info.get('pid')}, "
                   f"{info.get('owner')}, since {info.get('started')}); waiting for it to finish")
            (say or (lambda m: print(f"[mvh] {m}", file=sys.stderr, flush=True)))(msg)
            warned = True
        time.sleep(poll)
    with _held_guard:
        _held_songs[key] = 1
    try:
        yield path
    finally:
        with _held_guard:
            _held_songs.pop(key, None)
        _release(path)
