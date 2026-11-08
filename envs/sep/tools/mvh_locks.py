r"""Machine-wide heavy/gpu slot locks (%LOCALAPPDATA%\mvh\locks), exclusive-create, stale detection (dead pid or >3 h)."""
import json, os, time, ctypes
from pathlib import Path

LOCKS = Path(os.environ["LOCALAPPDATA"]) / "mvh" / "locks"
STALE_S = 3 * 3600

def _pid_alive(pid):
    if not pid:
        return False
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE

def _try(path, owner):
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            info = json.loads(path.read_text(encoding="utf-8") or "{}")
        except Exception:
            info = {}
        age = time.time() - path.stat().st_mtime
        if age > STALE_S or (info.get("pid") and not _pid_alive(info["pid"])):
            try:
                path.unlink()
            except OSError:
                pass
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"owner": owner, "pid": os.getpid(), "started": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
    return True

class Slot:
    """with Slot(owner, gpu=False) as s: ...   s.waited seconds, s.name, s.others (other lock owners at acquire)"""
    def __init__(self, owner, gpu=False, poll=15):
        self.owner, self.gpu, self.poll = owner, gpu, poll
        self.paths = []
    def __enter__(self):
        LOCKS.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            for n in (0, 1):
                p = LOCKS / f"heavy-{n}.lock"
                if _try(p, self.owner):
                    self.paths.append(p); self.name = p.name
                    break
            if self.paths:
                if not self.gpu:
                    break
                g = LOCKS / "gpu.lock"
                if _try(g, self.owner):
                    self.paths.append(g)
                    break
                self.paths.pop().unlink(missing_ok=True); self.paths = []  # don't hog a slot while waiting for the gpu
            time.sleep(self.poll)
        self.waited = time.time() - t0
        self.others = []
        for p in LOCKS.glob("*.lock"):
            if p not in self.paths:
                try:
                    self.others.append(json.loads(p.read_text(encoding="utf-8")).get("owner"))
                except Exception:
                    pass
        return self
    def touch(self):
        for p in self.paths:
            os.utime(p, None)
    def __exit__(self, *a):
        for p in self.paths:
            p.unlink(missing_ok=True)
