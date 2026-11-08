"""Child processes inside a Windows Job Object with KILL_ON_JOB_CLOSE (PLAN §3.3).

Every ffmpeg, sep-worker and stage child that mvh starts is assigned to one process-wide job, so when the mvh
process dies (Ctrl+C, a crash, a killed terminal) Windows kills the whole tree. No shell strings: argv lists
only.
Stdlib only. On non-Windows platforms the job part is a no-op.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from typing import Any, Mapping, Sequence

__all__ = ["job_handle", "assign", "popen", "run", "in_job", "CREATE_NO_WINDOW"]

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_JOB = None
_LOCK = threading.Lock()


if os.name == "nt":

    class _BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO(ctypes.Structure):
        _fields_ = [
            (n, ctypes.c_uint64)
            for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")
        ]

    class _EXT(ctypes.Structure):
        _fields_ = [
            ("Basic", _BASIC),
            ("Io", _IO),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _K32.CreateJobObjectW.restype = wintypes.HANDLE
    _K32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _K32.SetInformationJobObject.restype = wintypes.BOOL
    _K32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _K32.AssignProcessToJobObject.restype = wintypes.BOOL
    _K32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _K32.IsProcessInJob.restype = wintypes.BOOL
    _K32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]

_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFO = 9


def job_handle():
    """The process-wide job (created on first use). None on non-Windows or if creation failed."""
    global _JOB
    if os.name != "nt":
        return None
    with _LOCK:
        if _JOB is None:
            h = _K32.CreateJobObjectW(None, None)
            if not h:
                return None
            info = _EXT()
            info.Basic.LimitFlags = _KILL_ON_JOB_CLOSE
            if not _K32.SetInformationJobObject(
                h, _EXTENDED_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)
            ):
                return None
            _JOB = h
        return _JOB


def assign(proc: subprocess.Popen) -> bool:
    """Put a started child into the job. Returns False when that is not possible (non-Windows)."""
    h = job_handle()
    if h is None:
        return False
    ph = wintypes.HANDLE(int(proc._handle))  # type: ignore[attr-defined]
    return bool(_K32.AssignProcessToJobObject(h, ph))


def in_job(proc: subprocess.Popen) -> bool:
    if os.name != "nt" or _JOB is None:
        return False
    res = wintypes.BOOL()
    ph = wintypes.HANDLE(int(proc._handle))  # type: ignore[attr-defined]
    _K32.IsProcessInJob(ph, _JOB, ctypes.byref(res))
    return bool(res.value)


def popen(
    args: Sequence[str | os.PathLike], *, env: Mapping[str, str] | None = None, cwd=None, **kw: Any
) -> subprocess.Popen:
    """subprocess.Popen(argv) assigned to the kill-on-close job; never a shell."""
    if kw.get("shell"):
        raise ValueError("shell strings are not allowed")
    flags = kw.pop("creationflags", 0) | (CREATE_NO_WINDOW if os.name == "nt" else 0)
    p = subprocess.Popen(
        [os.fspath(a) for a in args],
        env=dict(env) if env is not None else None,
        cwd=cwd,
        creationflags=flags,
        **kw,
    )
    try:
        assign(p)
    except Exception:  # noqa: BLE001  (the job is a safety net; never fail the call over it)
        pass
    return p


def run(
    args: Sequence[str | os.PathLike],
    *,
    input: bytes | None = None,
    capture: bool = True,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
    cwd=None,
    text: bool = False,
) -> subprocess.CompletedProcess:
    """Run to completion inside the job. Text mode decodes as UTF-8 with errors='replace' (PLAN §3.4)."""
    kw: dict[str, Any] = {}
    if capture:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input is not None:
        kw["stdin"] = subprocess.PIPE
    else:
        kw["stdin"] = subprocess.DEVNULL
    if text:
        kw.update(encoding="utf-8", errors="replace")
    p = popen(args, env=env, cwd=cwd, **kw)
    try:
        out, err = p.communicate(input=input if not text or input is None else input, timeout=timeout)
    except BaseException:
        p.kill()
        p.wait()
        raise
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


if __name__ == "__main__":  # tiny self-check: python -m mvh.io.proc
    r = run([sys.executable, "-c", "print('ok')"], text=True)
    print(r.returncode, r.stdout.strip(), "job" if job_handle() else "no-job")
