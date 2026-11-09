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


def _last_good(runner: "Runner", name: str) -> tuple[Path, dict[str, Any]] | None:
    """The stage's last committed cache entry (``latest.json``) when this run did not leave it current: a
    stale, pending (not run) or failed stage keeps its previous outputs in the song folder (publish is never
    undone for them), so its curves stay too (W4D-1)."""
    sc = runner.cache.stage(name)
    lat = sc.latest() or {}
    pre = lat.get("pre_key")
    if not isinstance(pre, str) or not pre:
        return None
    rec = sc.done(pre)
    if not rec or (rec.get("status", "ok") not in ("ok", "done", "degraded", "skipped")):
        return None
    if name not in runner.cache.published():
        return None  # unpublished (e.g. after a validation failure): its outputs left the folder
    return sc.dir(pre), rec


def _timebase(song: Path) -> tuple[int, int] | None:
    """(n_samples, sample_rate) of the current canonical audio (meta/source.json), if any."""
    src = _meta(song, "meta/source.json") or {}
    try:
        n, sr = int(src["n_samples"]), int(src["sample_rate"])
    except (KeyError, TypeError, ValueError):
        return None
    return (n, sr) if sr > 0 else None


def _fits(entries: list[curvefile.ChannelData], tb: tuple[int, int]) -> bool:
    """Every kept channel has the length its file's rate implies for the current audio."""
    from mvh.contract.conventions import n_curve_frames

    for e in entries:
        cf = registry.CURVE_FILES[registry.channel(e.id).file]
        if _n_frames(e) != n_curve_frames(tb[0], tb[1], int(cf.rate_hz)):
            return False
    return True


def _stage_entries(d: Path, rec: dict[str, Any]) -> list[curvefile.ChannelData]:
    out: list[curvefile.ChannelData] = []
    for fid, chans in rec.get("curves", {}).items():
        for cid, info in chans.items():
            v = np.fromfile(d / MVH_DIR / "curves" / fid / f"{cid}.f32", dtype="<f4")
            out.append(curvefile.ChannelData(cid, v, dict(info.get("meta", {}))))
    for fid, info in rec.get("matrices", {}).items():
        if not info.get("public"):
            continue
        cf = registry.CURVE_FILES[fid]
        dt = np.uint8 if cf.dtype == "u8" else "<f4"
        a = np.fromfile(d / MVH_DIR / "matrices" / f"{fid}.bin", dtype=dt)
        out.append(curvefile.ChannelData(fid, a.reshape(info["shape"]), dict(info.get("meta", {}))))
    return out


def _n_frames(e: curvefile.ChannelData) -> int:
    v = np.asarray(e.values)
    return int(v.shape[0]) if v.ndim == 2 else int(v.size)


def pack_curves(runner: "Runner") -> dict[str, Any] | None:
    """Pack curves/*.f32|u8 + curves/index.json from every stage's channels.

    * Current stages (done / degraded / skipped in this run) contribute their entry; a stage this run left
      stale, pending or failed contributes its last committed entry, matching the events and meta files it
      keeps in the folder (W4D-1: a scoped run on a stale folder used to delete every such curve file).
      Kept channels whose length no longer fits the current timebase (a different song in the folder) are
      dropped with a warning. build_manifest lists the kept stages' files and names the stages (W4VP-1).
    * A file is deleted only when no stage, current or kept, produces it any more.
    * Files are written through mvh.io.atomic (unique temp names, retried replace) and only when their bytes
      changed. A file held open by another program keeps its previous version, and curves/index.json keeps
      that file's previous entries, so the folder stays self-consistent (W4P-2); a warning names the file.
    """
    song = runner.s.song_dir
    entries: list[curvefile.ChannelData] = []
    tb = _timebase(song)
    for name in runner.order:
        st = runner.states[name]
        if st.status in OK and st.record:
            entries += _stage_entries(runner.cache.stage(name).dir(st.pre_key or ""), st.record)
            continue
        if st.status in OK:
            continue
        lg = _last_good(runner, name)
        if lg is None:
            continue
        try:
            old = _stage_entries(*lg)
        except (OSError, KeyError, ValueError) as e:
            runner.warnings.append(f"{name}: previous curves unreadable ({type(e).__name__}); dropped")
            continue
        if not old:
            continue
        if tb is not None and not _fits(old, tb):
            runner.warnings.append(
                f"{name}: previous curves do not fit the current audio; dropped until it runs"
            )
            continue
        entries += old
    produced = {registry.channel(e.id).file for e in entries}
    for fid, cf in registry.CURVE_FILES.items():
        if fid not in produced and (song / cf.path).exists():
            try:
                atomic.unlink_retry(song / cf.path)
            except PermissionError:
                runner.warnings.append(f"_runner: stale {cf.path} is open in another program; not removed")
    idx_p = song / "curves" / "index.json"
    if not entries:
        if idx_p.exists():
            try:
                atomic.unlink_retry(idx_p)
            except PermissionError:
                runner.warnings.append(
                    "_runner: stale curves/index.json is open in another program; not removed"
                )
        return None
    index, blobs = curvefile.pack(entries)
    held: list[str] = []
    for rel, data in blobs.items():
        if not _write_if_changed(song / rel, data):
            held.append(rel)
    if held:
        index = _keep_held_entries(song, index, held, runner)
    if not _write_if_changed(idx_p, curvefile.index_bytes(index)):
        runner.warnings.append(
            "_runner: curves/index.json is open in another program and keeps its previous version; the curve "
            "files may not match it until mvh analyze runs again"
        )
    return index


def _write_if_changed(path: Path, data: bytes) -> bool:
    """False when the file is held open by another program (its previous version stays)."""
    try:
        if path.is_file() and path.stat().st_size == len(data) and path.read_bytes() == data:
            return True
    except OSError:
        pass
    try:
        atomic.write_bytes(path, data)
    except PermissionError:
        return False
    return True


def _keep_held_entries(
    song: Path, index: dict[str, Any], held: list[str], runner: "Runner"
) -> dict[str, Any]:
    """Swap the index entries of held curve files for their previous ones (the held file is the old one)."""
    try:
        old = _read(song / "curves" / "index.json")
    except (OSError, ValueError):
        old = None
    fid_of = {cf.path: fid for fid, cf in registry.CURVE_FILES.items()}
    for rel in held:
        fid = fid_of.get(rel)
        if old and fid in old.get("files", {}):
            index["files"][fid] = old["files"][fid]
            index["channels"] = [c for c in index["channels"] if c.get("file") != fid] + [
                c for c in old.get("channels", []) if c.get("file") == fid
            ]
            runner.warnings.append(
                f"_runner: {rel} is open in another program; the song folder keeps its previous version "
                "(close the program and run mvh analyze again)"
            )
        else:
            index["files"].pop(fid, None)
            index["channels"] = [c for c in index["channels"] if c.get("file") != fid]
            runner.warnings.append(f"_runner: {rel} is open in another program and could not be written")
    order = list(registry.CURVE_FILES)
    index["files"] = {f: index["files"][f] for f in order if f in index["files"]}
    index["channels"].sort(key=lambda c: (order.index(c["file"]) if c.get("file") in order else 1 << 30,
                                          curvefile.channel_order_key(c["id"])))
    return index


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


def kick_info(song: Path) -> tuple[str | None, dict[str, Any] | None, list[str]]:
    """D79 (user decision UD2): the agent-facing kick source from meta/drums.json (the drums stage's per-song
    choice), the agreement of the two kick timelines and the QA flags. Without meta/drums.json (no drums stage
    output) the mix kick (events/hits.kick) is the source when it exists."""
    d = _meta(song, "meta/drums.json")
    if d and d.get("kick_source") in ("drums", "mix"):
        a = d.get("agreement") or {}
        agree = {"mix_in_drums": a.get("mix_in_drums"), "drums_in_mix": a.get("drums_in_mix"),
                 "tol_ms": a.get("tol_ms", 30.0)}
        # a mix choice is already flagged by the drums stage's fallback (fallback:drums:kick_source_mix)
        return d["kick_source"], agree, ["qa:kick_sources_disagree"] if a.get("low") else []
    if (song / "events" / "hits.kick.json").is_file():
        return "mix", None, ["fallback:drums:kick_source_mix"]
    return None, None, []


def _kept_curves(index: dict[str, Any] | None, rec: dict[str, Any]) -> bool:
    """The packed index carries at least one channel of this (kept) cache entry."""
    if not index:
        return False
    ids = {c.get("id") for c in index.get("channels", [])}
    mine = {cid for chans in rec.get("curves", {}).values() for cid in chans}
    mine |= {fid for fid, info in rec.get("matrices", {}).items() if info.get("public")}
    return bool(ids & mine)


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
    kick_source, kick_agree, kick_flags = kick_info(song)
    flags += kick_flags

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
    kept: list[str] = []
    for name in runner.order:
        st = runner.states[name]
        if st.status in OK and st.record:
            rec, current = st.record, True
        elif st.status in OK:
            continue
        else:
            # W4VP-1 (D34): a stage this run left stale, pending or failed keeps its last committed outputs
            # in the folder (publish is never undone for it; pack_curves keeps its curves): they stay listed
            lg = _last_good(runner, name)
            if lg is None:
                continue
            rec, current = lg[1], False
        outs = rec.get("outputs", {})
        n_kept = 0
        for rel in pub.get(name, []):
            if not current:
                if not (song / rel).is_file():
                    continue
                n_kept += 1
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
        if not current and (n_kept or _kept_curves(index, rec)):
            kept.append(name)
    if kept:
        runner.warnings.append(
            "outputs and curves of stages not current in this run kept from their previous run: "
            + ", ".join(kept)
        )
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
            "kick_source": kick_source,
            "kick_agreement": kick_agree,
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
