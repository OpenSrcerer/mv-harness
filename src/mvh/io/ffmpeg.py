r"""ffmpeg resolver (PLAN §3.4): ``MVH_FFMPEG``, then ``%LOCALAPPDATA%\mvh\config.json`` (utf-8-sig), then
PATH.

The resolved bin directory is put FIRST on PATH for every child (``child_env``), so an ffmpeg spawned by a
library
(audio-separator, pydub, ...) is the same 9.0.2 build. Stdlib only.
"""

from __future__ import annotations

import os
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from . import proc
from .paths import config

__all__ = [
    "FfmpegNotFound",
    "resolve_ffmpeg",
    "resolve_ffprobe",
    "bin_dir",
    "child_env",
    "info",
    "run_ffmpeg",
    "FLAG_NAMES",
]

#: buildconf features doctor reports and the cache key records
FLAG_NAMES = ("whisper", "vulkan", "chromaprint", "libsoxr", "libopus", "libmp3lame")


class FfmpegNotFound(RuntimeError):
    pass


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def resolve_ffmpeg() -> Path:
    env = os.environ.get("MVH_FFMPEG")
    if env and Path(env).is_file():
        return Path(env)
    cfg = config().get("ffmpeg")
    if cfg and Path(cfg).is_file():
        return Path(cfg)
    w = shutil.which("ffmpeg")
    if w:
        return Path(w)
    raise FfmpegNotFound(
        'ffmpeg not found: set MVH_FFMPEG, write %LOCALAPPDATA%/mvh/config.json {"ffmpeg": ...} '
        "(scripts/bootstrap.ps1 does) or put ffmpeg on PATH"
    )


def resolve_ffprobe() -> Path:
    env = os.environ.get("MVH_FFPROBE")
    if env and Path(env).is_file():
        return Path(env)
    try:
        sib = resolve_ffmpeg().with_name(_exe("ffprobe"))
        if sib.is_file():
            return sib
    except FfmpegNotFound:
        pass
    cfg = config().get("ffprobe")
    if cfg and Path(cfg).is_file():
        return Path(cfg)
    w = shutil.which("ffprobe")
    if w:
        return Path(w)
    raise FfmpegNotFound("ffprobe not found (expected next to ffmpeg)")


def bin_dir() -> Path:
    return resolve_ffmpeg().parent


def child_env(base: Mapping[str, str] | None = None, **extra: str) -> dict[str, str]:
    """A copy of the environment: ffmpeg bin first on PATH, PYTHONUTF8=1, MVH_FFMPEG/MVH_FFPROBE set."""
    env = dict(os.environ if base is None else base)
    try:
        b = str(bin_dir())
        parts = [
            p
            for p in env.get("PATH", "").split(os.pathsep)
            if p and os.path.normcase(p) != os.path.normcase(b)
        ]
        env["PATH"] = os.pathsep.join([b] + parts)
        env["MVH_FFMPEG"] = str(resolve_ffmpeg())
        env["MVH_FFPROBE"] = str(resolve_ffprobe())
    except FfmpegNotFound:
        pass
    env["PYTHONUTF8"] = "1"
    env.update(extra)
    return env


@lru_cache(maxsize=4)
def _info(path: str, mtime: float) -> dict:
    r = proc.run([path, "-hide_banner", "-version"], text=True, timeout=60)
    first = (r.stdout or "").splitlines()[0] if r.stdout else ""
    m = re.match(r"ffmpeg version (\S+)", first)
    rb = proc.run([path, "-hide_banner", "-buildconf"], text=True, timeout=60)
    flags = sorted({ln.strip() for ln in (rb.stdout or "").splitlines() if ln.strip().startswith("--")})
    enabled = {f[len("--enable-") :] for f in flags if f.startswith("--enable-")}
    return {
        "path": path,
        "version": m.group(1) if m else first,
        "version_line": first,
        "buildconf": flags,
        "has": {k: (k in enabled) for k in FLAG_NAMES},
    }


def info(ffmpeg: Path | None = None) -> dict:
    """{path, version, version_line, buildconf[], has{<FLAG_NAMES>: bool}}."""
    p = Path(ffmpeg) if ffmpeg else resolve_ffmpeg()
    return dict(_info(str(p), p.stat().st_mtime))


def run_ffmpeg(
    args: list[str | os.PathLike],
    *,
    input: bytes | None = None,
    timeout: float | None = None,
    cwd=None,
    loglevel: str = "warning",
):
    """Run ffmpeg (bytes out/err) in the job object: ``-nostdin -hide_banner -v <loglevel>`` + args."""
    pre: list[str | os.PathLike] = [resolve_ffmpeg(), "-hide_banner", "-v", loglevel]
    if input is None:
        pre.insert(1, "-nostdin")
    return proc.run(pre + list(args), input=input, timeout=timeout, cwd=cwd, env=child_env())
