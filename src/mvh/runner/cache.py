"""Stage cache (PLAN §3.3, NF2): ``out/<slug>/.cache/<stage>/<key>/``.

Key = sha256 of the canonical JSON of the stage's *key inputs*:
  stage name, stage version, contract version, resolved params (with the fixed thread count ``threads``), the
  SHA-256s of every declared model file, the upstream keys, the subset of overrides the stage declares, the
  content hashes of its external inputs (input file, lyrics file, intent.md, authored.json, ...), the ffmpeg
  version and buildconf (``uses_ffmpeg``), the env lock hash (full sha256 of uv.lock and models.lock.json;
  the sep
  locks for env 'sep') and the device class (``gpu``).
Network stages: the key above (``pre_key``) names the cache dir; the hashes of the cached responses the
stage used
are folded in after the run (``key`` = sha256(pre_key + response hashes)); downstream keys use ``key``.

Cache dir layout: every output at its relative path (public and cache-only) plus ``_mvh/`` (done.json, curves,
matrices, provenance). ``<stage>/latest.json`` points at the most recent successful key (for ``mvh status``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from mvh.io import atomic
from mvh.io.paths import repo_root

__all__ = [
    "canon",
    "sha256_text",
    "sha256_file",
    "file_hash",
    "env_lock_hash",
    "key_of",
    "StageCache",
    "SongCache",
    "MVH_DIR",
    "DONE",
    "diff_inputs",
]

MVH_DIR = "_mvh"
DONE = "_mvh/done.json"


def canon(obj: Any) -> str:
    """Canonical JSON (sorted keys, no whitespace, UTF-8 text) used for hashing."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str
    )


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p: Path | str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


_FILE_HASH_CACHE: dict[tuple[str, int, float], str] = {}


def file_hash(p: Path | str) -> str:
    """sha256 of a file, memoised on (path, size, mtime) within this process."""
    p = Path(p)
    st = p.stat()
    k = (str(p.resolve()), st.st_size, st.st_mtime)
    if k not in _FILE_HASH_CACHE:
        _FILE_HASH_CACHE[k] = sha256_file(p)
    return _FILE_HASH_CACHE[k]


@lru_cache(maxsize=4)
def _env_lock_hash(env: str, root: str) -> dict[str, str | None]:
    r = Path(root)

    def h(p: Path) -> str | None:
        return sha256_file(p) if p.is_file() else None

    out: dict[str, str | None] = {"models.lock.json": h(r / "models.lock.json")}
    if env == "sep":
        out["envs/sep/uv.rocm.lock"] = h(r / "envs/sep/uv.rocm.lock")
        out["envs/sep/uv.cpu.lock"] = h(r / "envs/sep/uv.cpu.lock")
    else:
        out["uv.lock"] = h(r / "uv.lock")
    return out


def env_lock_hash(env: str = "main") -> dict[str, str | None]:
    """Full sha256 of an env's lock files (main: uv.lock + models.lock.json; sep: both sep locks + models)."""
    return dict(_env_lock_hash(env, str(repo_root())))


def key_of(inputs: Mapping[str, Any]) -> str:
    return sha256_text(canon(inputs))


def diff_inputs(old: Mapping[str, Any] | None, new: Mapping[str, Any]) -> list[str]:
    """Human-readable reasons why two key-input documents differ (for ``mvh status``)."""
    if not old:
        return ["never run"]
    out = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if canon(a) == canon(b):
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            subs = sorted(s for s in set(a) | set(b) if canon(a.get(s)) != canon(b.get(s)))
            out.append(f"{k} changed: {', '.join(subs)}" if subs else f"{k} changed")
        elif isinstance(a, (int, float, str)) and isinstance(b, (int, float, str)) and len(f"{a}{b}") <= 60:
            out.append(f"{k} changed: {a} -> {b}")
        else:
            out.append(f"{k} changed")
    return out or ["no difference"]


def _read_json(p: Path) -> Any:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(p: Path, obj: Any) -> None:
    atomic.write_text(
        p, json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False, sort_keys=False) + "\n"
    )


@dataclass
class StageCache:
    """One stage's cache folder ``.cache/<stage>/``."""

    root: Path  # .cache/<stage>
    stage: str

    def dir(self, key: str) -> Path:
        return self.root / key

    def done(self, key: str) -> dict[str, Any] | None:
        p = self.dir(key) / DONE
        if p.is_file():
            try:
                return _read_json(p)
            except (OSError, ValueError):
                return None
        return None

    def latest(self) -> dict[str, Any] | None:
        p = self.root / "latest.json"
        if p.is_file():
            try:
                return _read_json(p)
            except (OSError, ValueError):
                return None
        return None

    def set_latest(self, record: Mapping[str, Any]) -> None:
        _write_json(self.root / "latest.json", dict(record))

    def failed(self) -> dict[str, Any] | None:
        p = self.root / "failed.json"
        if p.is_file():
            try:
                return _read_json(p)
            except (OSError, ValueError):
                return None
        return None

    def set_failed(self, record: Mapping[str, Any] | None) -> None:
        p = self.root / "failed.json"
        if record is None:
            atomic.unlink_retry(p)
        else:
            _write_json(p, dict(record))

    def staging(self, key: str, token: str) -> Path:
        return self.root / f".tmp-{key[:12]}-{token}"

    def commit(self, staging: Path, key: str) -> Path:
        """Move a finished staging dir to ``<key>/`` (replacing an older copy)."""
        dst = self.dir(key)
        if dst.exists():
            old = self.root / f".old-{key[:12]}-{staging.name[-8:]}"
            atomic.replace_retry(dst, old)
            atomic.replace_retry(staging, dst)
            atomic.rmtree_retry(old)
        else:
            atomic.replace_retry(staging, dst)
        return dst

    def prune(self, keep: set[str]) -> None:
        """Remove cache dirs of this stage other than ``keep`` and leftover staging dirs."""
        if not self.root.is_dir():
            return
        for p in self.root.iterdir():
            if p.is_dir() and p.name not in keep:
                atomic.rmtree_retry(p)


@dataclass
class SongCache:
    song_dir: Path
    stages: dict[str, StageCache] = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return self.song_dir / ".cache"

    def stage(self, name: str) -> StageCache:
        if name not in self.stages:
            self.stages[name] = StageCache(self.root / name, name)
        return self.stages[name]

    @property
    def logs(self) -> Path:
        return self.root / "_logs"

    @property
    def http(self) -> Path:
        return self.root / "_http"

    @property
    def published_path(self) -> Path:
        return self.root / "_published.json"

    def published(self) -> dict[str, list[str]]:
        p = self.published_path
        if p.is_file():
            try:
                return _read_json(p)
            except (OSError, ValueError):
                return {}
        return {}

    def set_published(self, d: Mapping[str, list[str]]) -> None:
        _write_json(self.published_path, {k: sorted(v) for k, v in sorted(d.items())})
