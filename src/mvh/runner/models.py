r"""Model registry over the root ``models.lock.json`` (PLAN §3.3 "Models"). ``mvh models fetch`` is THE only
downloader.

Lock entry: ``{id, envs[], files[{path, url, revision, sha256, size}], licence, used_by[]}``.
Local layout (ported from scripts/fetch_models.py):
  ``<path>``                   -> %MVH_MODELS_DIR% (default %LOCALAPPDATA%\mvh\models) / path
  ``nltk/<rel>``               -> %LOCALAPPDATA%\mvh\nltk\<rel>
  ``downloads/<rel>``          -> %LOCALAPPDATA%\mvh\downloads\<rel>
  ``venv:<rel>``               -> <repo>\.venv\<rel>   (files shipped inside a wheel: verify only, never
  downloaded)
Downloads go to ``<file>.<pid>.part``, are SHA-256-verified against the lock, then ``os.replace``d into
place under a
per-file lock (``<file>.lock``, exclusive create). A SHA mismatch is an error, never a silent re-pin.
audio-separator's own ``download_checks.json`` is ignored. Stdlib only.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from mvh.io import atomic
from mvh.io.paths import home, models_dir, repo_root

from .locks import pid_alive

__all__ = [
    "ModelError",
    "lock_path",
    "load_lock",
    "lock_sha256",
    "local_path",
    "entry",
    "env_class",
    "handle",
    "fetch",
    "verify",
    "list_models",
    "FileStatus",
    "HF_CACHE_IDS",
    "UNZIP",
]

UA = {"User-Agent": "mv-harness/0.1 (personal, non-commercial; models fetch)"}
#: entries that libraries load through hf_hub_download: hard-link them into the HF cache layout under HF_HOME
HF_CACHE_IDS = {"allin1_harmonix", "demucs_onnx_htdemucs", "demucs_onnx_htdemucs_6s"}
#: entries that are archives to unpack (relative to %LOCALAPPDATA%\mvh)
UNZIP = {"rhubarb_lip_sync": "bin/rhubarb"}


class ModelError(RuntimeError):
    pass


def lock_path() -> Path:
    p = os.environ.get("MVH_MODELS_LOCK")
    return Path(p) if p else repo_root() / "models.lock.json"


_LOCK_CACHE: dict[tuple[str, float], dict] = {}


def load_lock(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else lock_path()
    key = (str(p), p.stat().st_mtime)
    if key not in _LOCK_CACHE:
        with open(p, encoding="utf-8") as fh:
            _LOCK_CACHE[key] = json.load(fh)
    return _LOCK_CACHE[key]


def lock_sha256(path: Path | None = None) -> str:
    return sha256_file(Path(path) if path else lock_path())


def separator_dir() -> Path:
    """The folder `mvh models fetch` fills with the SHA-pinned separator models (AUDIO_SEPARATOR_MODEL_DIR)."""
    return local_path("separator/x").parent


def entries(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_lock(path).get("models", []))


def entry(model_id: str) -> dict[str, Any]:
    for e in entries():
        if e["id"] == model_id:
            return e
    raise ModelError(f"model {model_id!r} is not in {lock_path().name}")


def env_class(envs: Iterable[str]) -> set[str]:
    """Normalise lock env labels (sep-rocm, sep-cpu, ffmpeg-whisper, main) to {main, sep, ffmpeg}."""
    out = set()
    for e in envs:
        out.add("sep" if e.startswith("sep") else "ffmpeg" if e.startswith("ffmpeg") else e)
    return out


def local_path(lock_rel: str) -> Path:
    if lock_rel.startswith("venv:"):
        return repo_root() / ".venv" / lock_rel[5:]
    head, _, rest = lock_rel.partition("/")
    if head in ("nltk", "downloads"):
        return home() / head / rest
    return models_dir() / lock_rel


# ---------------------------------------------------------------------------------------------- hashing
_SHA_CACHE_FILE = "sha-cache.json"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _sha_cache_path() -> Path:
    return home() / "models" / _SHA_CACHE_FILE


def _load_sha_cache() -> dict[str, Any]:
    try:
        with open(_sha_cache_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def cached_sha(p: Path, cache: dict[str, Any], use_cache: bool = True) -> str:
    st = p.stat()
    k = str(p)
    hit = cache.get(k)
    if use_cache and hit and hit.get("size") == st.st_size and hit.get("mtime") == st.st_mtime:
        return hit["sha256"]
    s = sha256_file(p)
    cache[k] = {"size": st.st_size, "mtime": st.st_mtime, "sha256": s}
    return s


def _save_sha_cache(cache: dict[str, Any]) -> None:
    with contextlib.suppress(OSError):
        atomic.write_text(
            _sha_cache_path(), json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True) + "\n"
        )


# ---------------------------------------------------------------------------------------------- status
@dataclass
class FileStatus:
    model_id: str
    path: str  # lock path
    local: Path
    status: str  # ok | missing | size | mismatch | fetched
    sha256: str | None = None
    detail: str = ""


def verify(
    ids: Iterable[str] | None = None,
    *,
    full: bool = True,
    use_cache: bool = True,
    progress: Callable[[str], None] | None = None,
) -> list[FileStatus]:
    """Check every file of the selected entries. ``full`` hashes (with a size/mtime cache); else size only."""
    want = set(ids) if ids else None
    cache = _load_sha_cache()
    rows: list[FileStatus] = []
    for e in entries():
        if want and e["id"] not in want:
            continue
        for f in e["files"]:
            lp = local_path(f["path"])
            if not lp.is_file():
                rows.append(FileStatus(e["id"], f["path"], lp, "missing"))
                continue
            if lp.stat().st_size != int(f.get("size", -1)):
                rows.append(
                    FileStatus(
                        e["id"], f["path"], lp, "size", None, f"{lp.stat().st_size} != {f.get('size')}"
                    )
                )
                continue
            if not full:
                row = FileStatus(e["id"], f["path"], lp, "ok")
            else:
                if progress:
                    progress(f"{e['id']}: {f['path']}")
                s = cached_sha(lp, cache, use_cache)
                row = FileStatus(e["id"], f["path"], lp, "ok" if s == f["sha256"] else "mismatch", s)
            if row.status == "ok" and e["id"] in HF_CACHE_IDS:
                for hf, dst, _ref, _rev in _hf_targets({"files": [f]}):
                    same = dst.is_file() and os.path.samefile(lp, dst)
                    if not same and (not full or not _hf_ok(lp, dst, f["sha256"], cache)):
                        row.status = "mismatch" if dst.is_file() else "missing"
                        row.detail = f"HF snapshot {dst} is not the verified file (run: mvh models fetch)"
            rows.append(row)
    if full:
        _save_sha_cache(cache)
    return rows


def list_models() -> list[dict[str, Any]]:
    out = []
    for e in entries():
        present = all(local_path(f["path"]).is_file() for f in e["files"])
        out.append(
            {
                "id": e["id"],
                "envs": e.get("envs", []),
                "n_files": len(e["files"]),
                "size": sum(int(f.get("size", 0)) for f in e["files"]),
                "licence": e.get("licence", ""),
                "used_by": e.get("used_by", []),
                "present": present,
                "bundled": all(f["path"].startswith("venv:") for f in e["files"]),
            }
        )
    return out


# ---------------------------------------------------------------------------------------------- handles
def handle(model_id: str, *, check: bool = True):
    """A ModelHandle (mvh.runner.spec) with explicit local paths. ``check`` verifies presence and size
    (cheap);
    full SHA-256 verification is ``mvh models verify`` / ``mvh doctor``."""
    from .spec import ModelHandle

    e = entry(model_id)
    files: dict[str, Path] = {}
    shas: dict[str, str] = {}
    for f in e["files"]:
        lp = local_path(f["path"])
        if check:
            if not lp.is_file():
                raise ModelError(
                    f"model file missing: {model_id}/{f['path']} (run: mvh models fetch --only {model_id})"
                )
            if lp.stat().st_size != int(f.get("size", -1)):
                raise ModelError(
                    f"model file has the wrong size: {model_id}/{f['path']} (run: mvh models verify)"
                )
        files[f["path"]] = lp
        shas[f["path"]] = f["sha256"]
    revs = {f.get("revision") for f in e["files"]}
    return ModelHandle(model_id, files, shas, e.get("licence", ""), revs.pop() if len(revs) == 1 else None)


# ---------------------------------------------------------------------------------------------- fetch
def _offline() -> bool:
    return os.environ.get("MVH_OFFLINE") == "1" or os.environ.get("HF_HUB_OFFLINE") == "1"


@contextlib.contextmanager
def _file_lock(target: Path, timeout: float = 3600.0):
    lk = target.with_name(target.name + ".lock")
    lk.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        try:
            fd = os.open(str(lk), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"pid": os.getpid()}, fh)
            break
        except (FileExistsError, PermissionError):
            try:
                with open(lk, encoding="utf-8") as fh:
                    pid = int(json.load(fh).get("pid", 0))
            except (OSError, ValueError):
                pid = -1
            if pid == 0 or (pid > 0 and not pid_alive(pid)):
                with contextlib.suppress(OSError):
                    lk.unlink()
                continue
            if time.time() - t0 > timeout:
                raise ModelError(f"timed out waiting for {lk}")
            time.sleep(1.0)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lk.unlink()


def _download(url: str, part: Path, tries: int = 4, log: Callable[[str], None] = print) -> None:
    last: Exception | None = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as fh:
                shutil.copyfileobj(r, fh, 1 << 20)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  retry {k + 1}/{tries} {part.name}: {e}")
            time.sleep(3 * (k + 1))
    raise ModelError(f"download failed: {url}: {last}")


def _fetch_file(e: dict, f: dict, log: Callable[[str], None]) -> FileStatus:
    lp = local_path(f["path"])
    if f["path"].startswith("venv:"):
        st = "ok" if lp.is_file() and sha256_file(lp) == f["sha256"] else "missing"
        return FileStatus(
            e["id"], f["path"], lp, st, detail="bundled in a wheel (re-sync the env if missing)"
        )
    with _file_lock(lp):
        if lp.is_file() and lp.stat().st_size == int(f.get("size", -1)) and sha256_file(lp) == f["sha256"]:
            return FileStatus(e["id"], f["path"], lp, "ok", f["sha256"])
        if _offline():
            raise ModelError(
                f"offline (MVH_OFFLINE/HF_HUB_OFFLINE) and {e['id']}/{f['path']} is missing or wrong"
            )
        lp.parent.mkdir(parents=True, exist_ok=True)
        part = lp.with_name(f"{lp.name}.{os.getpid()}.part")
        log(f"[{e['id']}] fetching {f['path']}")
        try:
            _download(f["url"], part, log=log)
            s = sha256_file(part)
            if s != f["sha256"]:
                raise ModelError(f"SHA MISMATCH {e['id']}/{f['path']}: lock {f['sha256']} != download {s}")
            atomic.replace_retry(part, lp)
        finally:
            if part.exists():
                atomic.unlink_retry(part)
        return FileStatus(e["id"], f["path"], lp, "fetched", f["sha256"])


def _hf_targets(e: dict) -> list[tuple[dict, Path, Path, str]]:
    """(lock file, HF snapshot path, refs/main path, revision) of every file the library loads through the HF cache."""
    out = []
    for f in e["files"]:
        url = f["url"]
        if "huggingface.co/" not in url or "/resolve/" not in url:
            continue
        repo, _, tail = url.split("huggingface.co/", 1)[1].partition("/resolve/")
        rev, _, rel = tail.partition("/")
        hf_home = Path(os.environ.get("HF_HOME") or (home() / "hf"))
        base = hf_home / "hub" / ("models--" + repo.replace("/", "--"))
        out.append((f, base / "snapshots" / rev / rel, base / "refs" / "main", rev))
    return out


def _hf_ok(src: Path, dst: Path, sha: str, cache: dict[str, Any] | None = None) -> bool:
    """True when the snapshot file is the models/ file itself (same inode) or has the lock's SHA-256."""
    if not dst.is_file():
        return False
    try:
        if os.path.samefile(src, dst):
            return True
    except OSError:
        return False
    return cached_sha(dst, cache if cache is not None else {}) == sha


def _hf_link(e: dict) -> None:
    """Hard-link files into HF_HOME/hub/models--org--name/snapshots/<rev>/ (offline hf_hub_download).
    A snapshot that is neither the models/ file nor a copy with the lock's SHA-256 is replaced (a corrupted
    model that was re-fetched must not stay corrupt under its second name)."""
    for f, dst, ref, rev in _hf_targets(e):
        ref.parent.mkdir(parents=True, exist_ok=True)
        if not ref.exists():
            atomic.write_text(ref, rev)
        src = local_path(f["path"])
        if _hf_ok(src, dst, f["sha256"]):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink():
            atomic.unlink_retry(dst)
        try:
            os.link(src, dst)
        except OSError:
            atomic.copy_file(src, dst)


def _unzip(e: dict, rel_target: str) -> None:
    target = home() / rel_target
    marker = target / ".unzipped"
    if marker.exists():
        return
    zpath = local_path(e["files"][0]["path"])
    tmpd = home() / (rel_target + f".{os.getpid()}.tmp")
    tmpd.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(tmpd)
    if target.exists():
        atomic.rmtree_retry(target)
    atomic.replace_retry(tmpd, target)
    atomic.write_text(marker, "ok\n")


def fetch(
    ids: Iterable[str] | None = None,
    *,
    envs: Iterable[str] | None = None,
    jobs: int = 3,
    log: Callable[[str], None] | None = None,
) -> list[FileStatus]:
    """Download (or confirm) every file of the selected entries; returns one status per file. Raises
    ModelError
    on a SHA mismatch or a failed download (after the other files finished)."""
    log = log or (lambda s: print(s, file=sys.stderr, flush=True))
    want = set(ids) if ids else None
    want_env = set(envs) if envs else None
    sel = [
        e
        for e in entries()
        if (not want or e["id"] in want) and (not want_env or env_class(e.get("envs", [])) & want_env)
    ]
    if want:
        unknown = want - {e["id"] for e in entries()}
        if unknown:
            raise ModelError(f"unknown model ids: {sorted(unknown)}")
    rows: list[FileStatus] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        futs = [(e, ex.submit(_fetch_file, e, f, log)) for e in sel for f in e["files"]]
        for e, fu in futs:
            try:
                rows.append(fu.result())
            except Exception as err:  # noqa: BLE001
                errors.append(str(err))
    for e in sel:
        if all(r.status in ("ok", "fetched") for r in rows if r.model_id == e["id"]):
            if e["id"] in HF_CACHE_IDS:
                _hf_link(e)
            if e["id"] in UNZIP:
                _unzip(e, UNZIP[e["id"]])
    if errors:
        raise ModelError("; ".join(errors))
    return rows
