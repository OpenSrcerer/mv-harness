"""Finalize step (CONTRACT §1, D20/D21): pack the curve files from every stage's channels, write
manifest.json,
run.json and curves/index.json, copy lib/ (src/mvh/assets: mvh.js, mvh_load.py, mvh.glsl - whatever exists)
and
schema/, then validate the folder.

manifest.json and everything packed here are deterministic (NF1): no timestamps, hosts or timings - those go
to
run.json only.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

import mvh
from mvh.contract import catalog, curvefile, registry
from mvh.contract.events import dumps_json
from mvh.contract.schemas import SCHEMA_DIR
from mvh.io import atomic
from mvh.io.paths import repo_root

from .cache import MVH_DIR
from .overrides import USER_INPUTS

if TYPE_CHECKING:
    from .run import Runner

__all__ = ["finalize", "pack_curves", "copy_lib", "copy_schemas", "build_manifest", "ASSETS", "LIB_FILES"]

ASSETS = Path(mvh.__file__).resolve().parent / "assets"
LIB_FILES = ("mvh.js", "mvh.d.ts", "mvh_load.py", "mvh.glsl")   # D53: + the TypeScript declarations
OK = ("done", "degraded", "skipped")
_PKGS = (
    "numpy",
    "scipy",
    "librosa",
    "torch",
    "torchaudio",
    "onnxruntime",
    "ctranslate2",
    "faster-whisper",
    "beat-this",
    "all-in-one-infer",
    "madmom-infer",
    "demucs-onnx",
    "basic-pitch",
    "jsonschema",
    "httpx",
)


def _read(p: Path) -> Any:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def pack_curves(runner: "Runner") -> dict[str, Any] | None:
    entries: list[curvefile.ChannelData] = []
    for name in runner.order:
        st = runner.states[name]
        if st.status not in OK or not st.record:
            continue
        d = runner.cache.stage(name).dir(st.pre_key or "")
        for fid, chans in st.record.get("curves", {}).items():
            for cid, info in chans.items():
                v = np.fromfile(d / MVH_DIR / "curves" / fid / f"{cid}.f32", dtype="<f4")
                entries.append(curvefile.ChannelData(cid, v, dict(info.get("meta", {}))))
        for fid, info in st.record.get("matrices", {}).items():
            if not info.get("public"):
                continue
            cf = registry.CURVE_FILES[fid]
            a = np.fromfile(
                d / MVH_DIR / "matrices" / f"{fid}.bin", dtype=np.uint8 if cf.dtype == "u8" else "<f4"
            )
            entries.append(curvefile.ChannelData(fid, a.reshape(info["shape"]), dict(info.get("meta", {}))))
    song = runner.s.song_dir
    produced = {registry.channel(e.id).file for e in entries}
    for fid, cf in registry.CURVE_FILES.items():
        if fid not in produced and (song / cf.path).exists():
            atomic.unlink_retry(song / cf.path)
    if not entries:
        if (song / "curves" / "index.json").exists():
            atomic.unlink_retry(song / "curves" / "index.json")
        return None
    return curvefile.assemble(song, entries)


def copy_lib(song_dir: Path) -> list[str]:
    out = []
    for name in LIB_FILES:
        src = ASSETS / name
        if src.is_file():
            atomic.copy_file(src, song_dir / "lib" / name)
            out.append(f"lib/{name}")
    return out


def copy_schemas(song_dir: Path) -> int:
    n = 0
    for p in sorted(SCHEMA_DIR.rglob("*.schema.json")):
        rel = p.relative_to(SCHEMA_DIR).as_posix()
        dst = song_dir / "schema" / rel
        if not dst.is_file() or dst.read_bytes() != p.read_bytes():
            atomic.copy_file(p, dst)
        n += 1
    return n


def _meta(song: Path, rel: str) -> dict[str, Any] | None:
    p = song / rel
    if p.is_file():
        try:
            d = _read(p)
            return d if isinstance(d, dict) else None
        except ValueError:
            return None
    return None


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _computed(runner: "Runner", name: str, st: Any) -> dict[str, Any]:
    """D64: on a cache hit, the seconds the run that computed the entry took (``latest.json``), so a no-op
    re-run does not erase what each stage costs."""
    if st.cache != "hit" or not st.key:
        return {}
    try:
        lat = runner.cache.stage(name).latest() or {}
    except Exception:  # noqa: BLE001
        return {}
    c = lat.get("computed") if lat.get("key") == st.key else None
    if isinstance(c, dict) and c.get("seconds") is not None:
        return {"computed_seconds": c["seconds"]}
    return {}


def key_flags(key: dict[str, Any]) -> list[str]:
    """meta/key.json flags for the manifest. W3 seam S02: M4 already writes ``key:...`` flags, so only bare
    ones get the prefix (the manifest used to show ``key:key:modulation``)."""
    return [str(f) if str(f).startswith("key:") else f"key:{f}" for f in key.get("flags", []) or []]


def build_manifest(runner: "Runner", index: dict[str, Any] | None, lib: list[str]) -> dict[str, Any]:
    song = runner.s.song_dir
    src = _meta(song, "meta/source.json") or {}
    ident = _meta(song, "meta/identity.json") or {}
    tempo = _meta(song, "meta/tempo.json") or {}
    key = _meta(song, "meta/key.json") or {}
    loud = _meta(song, "meta/loudness.json") or {}
    vr = _meta(song, "meta/vocal_range.json") or {}
    inst = _meta(song, "meta/instruments.json") or {}
    sep = _meta(song, "meta/separation.json")
    meaning = _meta(song, "meaning/meaning.json") or {}
    lyrics = _meta(song, "lyrics/lyrics.json") or {}

    stage_status: dict[str, str] = {}
    stage_summaries: dict[str, Any] = {}
    flags: list[str] = []
    warnings: list[str] = []
    for name in runner.order:
        spec = runner.specs[name]
        st = runner.states[name]
        if spec.trigger != "analyze" and st.status not in OK:
            continue
        stage_status[name] = st.status if st.status != "running" else "pending"
        if st.record:
            res = st.record.get("result", {})
            if res.get("summary"):
                stage_summaries[name] = res["summary"]
            warnings += [f"{name}: {w}" for w in res.get("warnings", [])]
            flags += [f"fallback:{f}" for f in res.get("fallbacks", [])]
        if st.status == "degraded":
            flags.append(f"degraded:{name}")
        if st.status == "failed":
            flags.append(f"failed:{name}")
    flags += [str(f) for f in (tempo.get("qa") or {}).get("flags", [])]
    flags += key_flags(key)

    vocal_range = None
    if vr.get("present") and isinstance(vr.get("lowest"), dict) and isinstance(vr.get("highest"), dict):
        vocal_range = {"low": vr["lowest"].get("name"), "high": vr["highest"].get("name")}
    instr = [
        s["instrument"]
        for s in sorted(inst.get("summary", []), key=lambda s: -float(s.get("coverage", 0)))
        if isinstance(s, dict) and s.get("instrument")
    ][:16]

    files: list[dict[str, Any]] = []
    pub = runner.cache.published()
    for name in runner.order:
        st = runner.states[name]
        if st.status not in OK or not st.record:
            continue
        outs = st.record.get("outputs", {})
        for rel in pub.get(name, []):
            info = outs.get(rel, {})
            e: dict[str, Any] = {"path": rel, "kind": info.get("kind", "json"), "stage": name}
            ev = info.get("events")
            if info.get("kind") == "events" and ev:
                name_ev = ev
                if "{" in ev:
                    name_ev = Path(rel).name[:-5]
                if rel != f"events/{name_ev}.json":
                    e["events"] = name_ev
            files.append(e)
    if index:
        for fid, f in index["files"].items():
            files.append(
                {
                    "path": f["path"],
                    "kind": "matrix" if f["layout"] == "row-major" else "curve",
                    "stage": "_runner",
                }
            )
        files.append({"path": "curves/index.json", "kind": "json", "stage": "_runner"})
    for rel in lib:
        files.append({"path": rel, "kind": "text", "stage": "_runner"})
    for rel in USER_INPUTS:
        if (song / rel).is_file():
            files.append({"path": rel, "kind": "json" if rel.endswith(".json") else "text", "stage": "_user"})
    files.sort(key=lambda f: f["path"])

    man = {
        "schema": "mvh/manifest",
        "schema_version": catalog.CONTRACT_VERSION,
        "mvh_version": mvh.__version__,
        "contract_version": catalog.CONTRACT_VERSION,
        "slug": runner.s.slug,
        "source": {
            "file_name": src.get("file_name", ""),
            "pcm_sha256": src.get("pcm_sha256", "0" * 64),
            "duration_s": float(src.get("duration_s", 0.0)),
            "sample_rate": int(src.get("sample_rate", 1) or 1),
            "channels": int(src.get("channels", 1) or 1),
            "n_samples": int(src.get("n_samples", 0)),
        },
        "timebase": {
            "unit": "s",
            "origin": "first sample of audio/mix.flac",
            "soundtrack": src.get("soundtrack", "audio/mix.flac"),
            "curve_rate_hz": 100,
            "frame_rule": "centred",
        },
        "status": {
            "stages": stage_status,
            "meaning": meaning.get("status", "pending") if meaning else "pending",
            "lyrics_grade": lyrics.get("grade"),
            "stems": bool(sep) and not bool((sep or {}).get("degraded", False)),
            "visemes": (song / "lipsync" / "visemes.json").is_file(),
            "flags": list(dict.fromkeys(flags)),
        },
        "summary": {
            "title": ident.get("title"),
            "artist": ident.get("artist"),
            "duration_s": float(src.get("duration_s", 0.0)),
            "bpm": _num(tempo.get("bpm")),
            "feel": tempo.get("feel"),
            "meter": (tempo.get("meter") or {}).get("time_signature"),
            "key": (key.get("global") or {}).get("key"),
            "integrated_lufs": _num(loud.get("integrated_lufs")),
            "lra_lu": _num(loud.get("lra_lu")),
            "true_peak_dbtp": _num(loud.get("true_peak_dbtp")),
            "vocal_range": vocal_range,
            "instrumentation": instr,
            "palette": list(src.get("palette", []))[:12],
            "stages": stage_summaries,
        },
        "files": files,
        "warnings": list(dict.fromkeys(warnings + runner.warnings)),
    }
    return man


def dumps_manifest(man: dict[str, Any]) -> str:
    """Indented JSON with one compact line per ``files`` entry (keeps the manifest well under 3k tokens)."""
    head = {k: v for k, v in man.items() if k != "files"}
    txt = json.dumps(head, ensure_ascii=False, indent=1, allow_nan=False)
    files = man.get("files", [])
    body = ",\n".join("  " + json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in files)
    return txt[:-1].rstrip() + ',\n "files": [\n' + body + ("\n" if files else "") + " ]\n}\n"


#: target for the manifest (CONTRACT §1: <= 3k tokens, estimated as characters / 4), with headroom
MANIFEST_CHAR_BUDGET = 11600


def fit_manifest(man: dict[str, Any], budget: int = MANIFEST_CHAR_BUDGET) -> dict[str, Any]:
    """Keep the manifest under its token cap deterministically: drop the largest per-stage summaries first
    (they stay in each stage's provenance and in run.json) and flag the trim; then cap the warnings list."""
    stages = man["summary"].get("stages", {})
    trimmed = []
    while len(dumps_manifest(man)) > budget and stages:
        big = max(sorted(stages), key=lambda k: len(json.dumps(stages[k], ensure_ascii=False)))
        trimmed.append(big)
        del stages[big]
    if trimmed:
        man["status"]["flags"].append("manifest:stage_summaries_trimmed")
    while len(dumps_manifest(man)) > budget and len(man["warnings"]) > 3:
        n = len(man["warnings"])
        keep = max(3, n // 2)
        man["warnings"] = man["warnings"][:keep] + [f"... {n - keep} more warnings in run.json"]
        if n <= 4:
            break
    return man


def _ram_gb() -> float | None:
    if os.name != "nt":
        return None
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return round(m.ullTotalPhys / 2**30, 1)
    return None


def build_run(runner: "Runner") -> dict[str, Any]:
    from . import models as mdl

    pk: dict[str, str] = {"mvh": mvh.__version__}
    for p in _PKGS:
        try:
            pk[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    try:
        fi = runner.ffmpeg_info()
        ff = {"version": fi["version"], "buildconf": fi["buildconf"]}
    except Exception:  # noqa: BLE001
        ff = {"version": "unknown", "buildconf": []}
    stages: dict[str, Any] = {}
    used: dict[str, list[str]] = {}
    fallbacks: list[str] = []
    devices = set()
    for name in runner.order:
        spec = runner.specs[name]
        st = runner.states[name]
        if spec.trigger != "analyze" and st.status not in OK:
            # W3 (M6b CR-8): on-demand stages that did not run are listed, with how to run them
            stages[name] = {"status": "pending", "cache": "miss", "key": None, "seconds": None,
                            "threads": max(1, runner.threads_for(spec)), "device": runner.device_class(spec),
                            "env": spec.env, "variant": None, "fallbacks": [],
                            "warnings": [st.reason or f"on demand: run `mvh {name}` on the song folder"]}
            continue
        rec = st.record or {}
        res = rec.get("result", {})
        wr = rec.get("worker_runs", [])
        dev = rec.get("device", runner.device_class(spec))
        devices.add(dev)
        stages[name] = {
            "status": st.status if st.status != "running" else "pending",
            "cache": st.cache or "hit" if st.record else (st.cache or "miss"),
            "key": st.key,
            "seconds": round(st.seconds, 3) if st.seconds is not None else None,
            # W3 seam S08 (D64): the part of `seconds` spent waiting for a machine-wide heavy slot
            "wait_s": round(st.wait_s, 3) if st.wait_s is not None else None,
            **_computed(runner, name, st),
            "threads": max(1, st.threads or runner.threads_for(spec)),
            "device": dev,
            "env": spec.env,
            "variant": wr[-1]["variant"] if wr else None,
            "fallbacks": list(res.get("fallbacks", [])),
            "warnings": list(res.get("warnings", []))
            + ([st.reason] if st.status in ("failed", "pending") and st.reason else []),
        }
        fallbacks += res.get("fallbacks", [])
        if st.status in OK:
            for m in spec.models:
                used.setdefault(m, []).append(name)
    lic = []
    for mid, by in sorted(used.items()):
        try:
            lic.append({"model_id": mid, "licence": mdl.entry(mid).get("licence", ""), "used_by": by})
        except mdl.ModelError:
            lic.append({"model_id": mid, "licence": "unknown", "used_by": by})
    return {
        "schema": "mvh/run",
        "schema_version": catalog.CONTRACT_VERSION,
        "mvh_version": mvh.__version__,
        "contract_version": catalog.CONTRACT_VERSION,
        "started": runner.started.isoformat(),
        "finished": datetime.now(timezone.utc).isoformat(),
        "profile": runner.s.profile,
        "host": {
            "os": platform.platform(),
            "cpu": platform.processor() or platform.machine(),
            "threads": os.cpu_count() or 1,
            **({"ram_gb": _ram_gb()} if _ram_gb() else {}),
        },
        "device": {"class": "rocm" if "rocm" in devices else "cpu", "gpu": None},
        "versions": {"python": sys.version.split()[0], "ffmpeg": ff, "packages": pk},
        "stages": stages,
        "licences": lic,
        "fallbacks_used": sorted(set(fallbacks)),
        "warnings": list(runner.warnings),
    }


def finalize(runner: "Runner") -> dict[str, Any]:
    from . import validate as val

    song = runner.s.song_dir
    index = pack_curves(runner)
    lib = copy_lib(song)
    copy_schemas(song)
    man = fit_manifest(build_manifest(runner, index, lib))
    atomic.write_text(song / "manifest.json", dumps_manifest(man))
    atomic.write_text(song / "run.json", dumps_json(build_run(runner)))
    rep = val.validate_folder(song)
    pending = [
        n for n in runner.order if runner.specs[n].trigger == "analyze" and runner.states[n].status not in OK
    ]
    failed = [n for n in runner.order if runner.states[n].status == "failed"]
    warnings = list(man["warnings"]) + [f"validate: {e}" for e in rep.errors]
    return {
        "manifest": str(song / "manifest.json"),
        "brief": str(song / "brief.md") if (song / "brief.md").is_file() else None,
        "viewer": str(song / "viewer.html") if (song / "viewer.html").is_file() else None,
        "warnings": warnings,
        "pending": pending,
        "failed": failed,
        "valid": rep.ok,
        "song_dir": str(song),
        "repo": str(repo_root()),
    }
