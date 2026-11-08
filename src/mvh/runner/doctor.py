"""``mvh doctor`` (PLAN §3.3): the resolved ffmpeg and its buildconf flags, the envs and whether their locks
are in
sync, ROCm health in sep-rocm, Vulkan whisper, Rhubarb, the models' SHA-256 values, free disk space, heavy
locks.

Each check returns ``Check(name, level, detail)`` with level OK | WARN | FAIL. Nothing here changes the
machine.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tomllib
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable

from mvh.io import proc
from mvh.io.ffmpeg import FfmpegNotFound, child_env, info, resolve_ffprobe
from mvh.io.paths import config, home, repo_root

from . import locks, models
from .sepworker import DEFAULT_VARIANTS, sep_python

__all__ = ["Check", "run_checks", "CHECKS", "ROCM_SMOKE"]

ROCM_SMOKE = (
    "import torch; assert torch.cuda.is_available(), 'cuda (HIP) not available'; "
    "a=torch.randn(256,256,device='cuda'); print(float((a@a).sum()), torch.version.hip, torch.__version__, "
    "torch.cuda.get_device_name(0))"
)


@dataclass
class Check:
    name: str
    level: str  # OK | WARN | FAIL
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


def _ffmpeg() -> list[Check]:
    try:
        fi = info()
    except FfmpegNotFound as e:
        return [Check("ffmpeg", "FAIL", str(e))]
    out = [Check("ffmpeg", "OK", f"{fi['path']} (version {fi['version']})")]
    has = fi["has"]
    for flag, need in (
        ("whisper", "WARN"),
        ("vulkan", "WARN"),
        ("chromaprint", "FAIL"),
        ("libopus", "FAIL"),
        ("libsoxr", "WARN"),
    ):
        out.append(
            Check(
                f"ffmpeg --enable-{flag}",
                "OK" if has.get(flag) else need,
                "present" if has.get(flag) else "missing",
            )
        )
    try:
        out.append(Check("ffprobe", "OK", str(resolve_ffprobe())))
    except FfmpegNotFound as e:
        out.append(Check("ffprobe", "FAIL", str(e)))
    return out


def _pname(n: str) -> str:
    return n.lower().replace("_", "-").replace(".", "-")


def _lock_packages(lock: Path) -> dict[str, str]:
    """{package: version} of a uv.lock, plus the project's direct dependency names under the key '__direct__'
    (a comma-joined string). The lock is universal (other platforms, extras), so only direct deps must be
    present."""
    with open(lock, "rb") as fh:
        d = tomllib.load(fh)
    out: dict[str, str] = {}
    direct: set[str] = set()
    for p in d.get("package", []):
        src = p.get("source", {})
        if "editable" in src or "virtual" in src:
            direct |= {
                _pname(x["name"])
                for x in p.get("dependencies", [])
                if "never" not in str(x.get("marker", ""))
                and "darwin" not in str(x.get("marker", ""))
                and "linux" not in str(x.get("marker", ""))
            }
            continue
        out[_pname(p["name"])] = str(p.get("version", ""))
    out["__direct__"] = ",".join(sorted(direct))
    return out


def _norm(v: str) -> str:
    return v.split("+")[0]


def _compare(lock: dict[str, str], installed: dict[str, str]) -> tuple[list[str], list[str]]:
    """(missing direct deps, version drift of installed locked packages)."""
    installed = {_pname(k): v for k, v in installed.items()}
    direct = [x for x in lock.get("__direct__", "").split(",") if x]
    missing = sorted(n for n in direct if n not in installed)
    wrong = sorted(
        f"{n} {installed[n]} != {v}"
        for n, v in lock.items()
        if n != "__direct__" and n in installed and _norm(installed[n]) != _norm(v)
    )
    return missing, wrong


def _main_env() -> list[Check]:
    lock = repo_root() / "uv.lock"
    if not lock.is_file():
        return [Check("env main", "FAIL", "uv.lock missing")]
    want = _lock_packages(lock)
    have = {
        d.metadata["Name"].lower().replace("_", "-"): d.version
        for d in metadata.distributions()
        if d.metadata["Name"]
    }
    missing, wrong = _compare(want, have)
    lvl = "OK" if not missing and not wrong else "WARN"
    det = f"{len(want) - 1} locked packages; python {sys.version.split()[0]}"
    if missing or wrong:
        det += f"; missing {missing[:5]} ({len(missing)}); version drift {wrong[:5]} ({len(wrong)})"
    return [Check("env main (uv.lock in sync)", lvl, det)]


_INSTALLED_SNIPPET = (
    "import importlib.metadata as m, json; "
    "print(json.dumps({d.metadata['Name'].lower().replace('_','-'): d.version "
    "for d in m.distributions() if d.metadata['Name']}))"
)


def _sep_env(rocm_smoke: bool) -> list[Check]:
    out = []
    root = repo_root() / "envs" / "sep"
    for v in DEFAULT_VARIANTS:
        py = sep_python(v)
        if py is None:
            out.append(
                Check(
                    f"env sep-{v}",
                    "WARN" if v == "rocm" else "FAIL",
                    "venv missing (envs/sep/.venv-" + v + ")",
                )
            )
            continue
        lock = root / v / "uv.lock"
        copy = root / f"uv.{v}.lock"
        notes = []
        if lock.is_file() and copy.is_file() and lock.read_bytes() != copy.read_bytes():
            notes.append(f"uv.{v}.lock differs from {v}/uv.lock")
        try:
            r = proc.run(
                [py, "-X", "utf8", "-c", _INSTALLED_SNIPPET], text=True, timeout=120, env=child_env()
            )
            have = json.loads(r.stdout or "{}")
            want = _lock_packages(lock) if lock.is_file() else {}
            missing, wrong = _compare(want, have)
            lvl = "OK" if not missing and not wrong and not notes else "WARN"
            det = f"{py} ({max(0, len(want) - 1)} locked)"
            if missing or wrong:
                det += f"; missing {missing[:5]} ({len(missing)}); drift {wrong[:5]} ({len(wrong)})"
        except Exception as e:  # noqa: BLE001
            lvl, det = "FAIL", f"{py}: {type(e).__name__}: {e}"
        out.append(Check(f"env sep-{v} (lock in sync)", lvl, "; ".join([det] + notes)))
        if v == "rocm" and rocm_smoke:
            env = child_env()
            env["HF_HUB_OFFLINE"] = "1"
            try:
                r = proc.run([py, "-X", "utf8", "-c", ROCM_SMOKE], text=True, timeout=300, env=env)
                if r.returncode == 0:
                    out.append(
                        Check(
                            "ROCm health (sep-rocm torch.cuda matmul)", "OK", (r.stdout or "").strip()[:200]
                        )
                    )
                else:
                    tail = (r.stderr or "").strip().splitlines()[-1:] or ["?"]
                    out.append(
                        Check(
                            "ROCm health (sep-rocm torch.cuda matmul)",
                            "WARN",
                            f"not available ({tail[0][:200]}); separate_hq falls back to sep-cpu",
                        )
                    )
            except Exception as e:  # noqa: BLE001
                out.append(
                    Check("ROCm health (sep-rocm torch.cuda matmul)", "WARN", f"{type(e).__name__}: {e}")
                )
    return out


def _whisper() -> list[Check]:
    try:
        has = info()["has"]
    except FfmpegNotFound:
        return [Check("Vulkan whisper", "FAIL", "no ffmpeg")]
    ggml = [e for e in models.entries() if e["id"].startswith("ggml.")]
    present = [e["id"] for e in ggml if all(models.local_path(f["path"]).is_file() for f in e["files"])]
    ok = has.get("whisper") and has.get("vulkan") and present
    return [
        Check(
            "Vulkan whisper (ffmpeg whisper filter + ggml models)",
            "OK" if ok else "WARN",
            f"whisper={has.get('whisper')} vulkan={has.get('vulkan')} ggml models present: {present}",
        )
    ]


def _rhubarb() -> list[Check]:
    cand = [
        os.environ.get("MVH_RHUBARB"),
        config().get("rhubarb"),
        str(home() / "bin" / "rhubarb" / "Rhubarb-Lip-Sync-1.14.0-Windows" / "rhubarb.exe"),
    ]
    for c in cand:
        if c and Path(c).is_file():
            try:
                r = proc.run([c, "--version"], text=True, timeout=60)
                return [Check("Rhubarb", "OK", f"{c} ({(r.stdout or r.stderr or '').strip()[:60]})")]
            except Exception as e:  # noqa: BLE001
                return [Check("Rhubarb", "WARN", f"{c}: {e}")]
    return [
        Check(
            "Rhubarb",
            "WARN",
            "not found (lipsync visemes are a Should; run mvh models fetch --only rhubarb_lip_sync)",
        )
    ]


def _models(full: bool, progress: Callable[[str], None] | None) -> list[Check]:
    try:
        rows = models.verify(full=full, progress=progress)
    except Exception as e:  # noqa: BLE001
        return [Check("models", "FAIL", f"{type(e).__name__}: {e}")]
    bad = [r for r in rows if r.status != "ok"]
    n_ids = len({r.model_id for r in rows})
    if not bad:
        return [
            Check(
                f"models ({'sha256' if full else 'size'})",
                "OK",
                f"{len(rows)} files in {n_ids} entries verified",
            )
        ]
    det = "; ".join(f"{r.model_id}/{r.path}: {r.status}" for r in bad[:8])
    return [Check(f"models ({'sha256' if full else 'size'})", "FAIL", f"{len(bad)}/{len(rows)} bad: {det}")]


def _disk() -> list[Check]:
    out = []
    seen = set()
    for label, p in (("repo", repo_root()), ("mvh home", home())):
        try:
            drive = os.path.splitdrive(str(p.resolve()))[0] or str(p)
            if drive in seen:
                continue
            seen.add(drive)
            u = shutil.disk_usage(p if p.exists() else p.parent)
            gb = u.free / 2**30
            out.append(
                Check(
                    f"free disk ({label}, {drive})",
                    "OK" if gb > 20 else "WARN" if gb > 5 else "FAIL",
                    f"{gb:.1f} GB free",
                )
            )
        except OSError as e:
            out.append(Check(f"free disk ({label})", "WARN", str(e)))
    return out


def _locks() -> list[Check]:
    st = locks.status()
    det = ", ".join(
        f"{k}: {'free' if v is None else str(v.get('owner')) + (' STALE' if v.get('stale') else '')}"
        for k, v in st.items()
    )
    return [Check("heavy locks", "OK", det)]


def _misc() -> list[Check]:
    out = [Check("python", "OK", f"{sys.executable} {sys.version.split()[0]}")]
    for v in (
        "MVH_THREADS",
        "HF_HOME",
        "TORCH_HOME",
        "NUMBA_CACHE_DIR",
        "NLTK_DATA",
        "AUDIO_SEPARATOR_MODEL_DIR",
    ):
        if v == "AUDIO_SEPARATOR_MODEL_DIR" and os.environ.get(v):
            from . import models as _m

            want = _m.separator_dir()
            got = Path(os.environ[v])
            files = [
                _m.local_path(f["path"])
                for e in _m.entries()
                for f in e["files"]
                if f["path"].startswith("separator/")
            ]
            if os.path.normcase(str(got)) != os.path.normcase(str(want)) and not all(
                (got / p.name).is_file() for p in files
            ):
                out.append(
                    Check(
                        f"env {v}",
                        "FAIL",
                        f"{got} lacks the pinned separator models (they are in {want}); "
                        "audio-separator would download unpinned ones. Fix mvh-env or unset it "
                        "(the runner always sets the right folder for children)",
                    )
                )
                continue
        out.append(
            Check(
                f"env {v}",
                "OK" if os.environ.get(v) else "WARN",
                os.environ.get(v) or "not set (mvh-env.ps1 sets it)",
            )
        )
    if os.environ.get("KMP_DUPLICATE_LIB_OK"):
        out.append(Check("env KMP_DUPLICATE_LIB_OK", "WARN", "set: it can hide an OpenMP clash; unset it"))
    return out


CHECKS = ("misc", "ffmpeg", "env", "rocm", "whisper", "rhubarb", "models", "disk", "locks")


def run_checks(
    *,
    quick: bool = False,
    rocm: bool = True,
    progress: Callable[[str], None] | None = None,
    only: set[str] | None = None,
) -> list[Check]:
    out: list[Check] = []
    want = only or set(CHECKS)
    if "misc" in want:
        out += _misc()
    if "ffmpeg" in want:
        out += _ffmpeg()
    if "env" in want:
        out += _main_env()
    if "env" in want or "rocm" in want:
        out += _sep_env(rocm_smoke=rocm and "rocm" in want and not quick)
    if "whisper" in want:
        out += _whisper()
    if "rhubarb" in want:
        out += _rhubarb()
    if "models" in want:
        out += _models(full=not quick, progress=progress)
    if "disk" in want:
        out += _disk()
    if "locks" in want:
        out += _locks()
    return out
