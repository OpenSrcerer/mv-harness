"""Test helpers (PLAN §12 "Heavy work").

* ``heavy(owner, gpu=False)``: hold one of the two machine-wide heavy slots (plus gpu.lock) around real
  inference;
  same files and JSON as scripts/heavy_lock.py. Inside a slot use at most 6 threads.
* ``apply_threads(n=None)``: export MVH_THREADS (default 3) and the OMP/BLAS/numba thread variables.
* ``tone(path, seconds, sr, channels, freq)``: a synthetic test file written through ffmpeg (any extension
  ffmpeg
  can mux: .flac, .wav, .mp3, .opus).
* ``make_skeleton_fixture(dir, n_samples, sr)``: a minimal, schema-valid walking-skeleton fixture (every
  stub's
  declared outputs, empty event lists, zero curves of the right length) for runner tests while the real
  tests/contract/synth/ is absent. Point MVH_FIXTURE_DIR at it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterator

import numpy as np

__all__ = ["heavy", "apply_threads", "tone", "make_skeleton_fixture", "instance_of", "DEFAULT_TEST_THREADS"]

DEFAULT_TEST_THREADS = 3


@contextlib.contextmanager
def heavy(
    owner: str = "pytest", gpu: bool = False, timeout: float | None = None, threads: int = 6
) -> Iterator[Any]:
    from mvh.runner import locks

    with locks.heavy(owner, gpu=gpu, timeout=timeout, threads=threads) as slot:
        yield slot


def apply_threads(n: int | None = None) -> int:
    from mvh.runner.threads import thread_env

    if n is None:
        try:
            n = int(os.environ.get("MVH_THREADS") or DEFAULT_TEST_THREADS)
        except ValueError:
            n = DEFAULT_TEST_THREADS
    os.environ.update(thread_env(n))
    return n


def tone(
    path: Path | str,
    seconds: float = 3.0,
    sr: int = 44100,
    channels: int = 2,
    freq: float = 440.0,
    amp: float = 0.5,
) -> Path:
    """Write a sine tone (with a short silence at both ends) through ffmpeg; returns the path."""
    from mvh.io import audio as aio
    from mvh.io import proc
    from mvh.io.ffmpeg import resolve_ffmpeg

    n = int(round(seconds * sr))
    t = np.arange(n) / sr
    env = np.clip(np.minimum(t / 0.05, (seconds - t) / 0.05), 0, 1)
    x = (amp * env * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    a = np.stack([x * (1.0 - 0.1 * c) for c in range(channels)])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".flac":
        return aio.encode_flac(a, sr, path)
    if path.suffix.lower() == ".wav":
        return aio.encode_wav(a, sr, path)
    data = np.ascontiguousarray(a.T).astype("<f4").tobytes()
    r = proc.run(
        [
            resolve_ffmpeg(),
            "-hide_banner",
            "-v",
            "error",
            "-y",
            "-f",
            "f32le",
            "-ar",
            str(sr),
            "-ac",
            str(channels),
            "-i",
            "pipe:0",
            path,
        ],
        input=data,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or b"").decode("utf-8", "replace")[:300])
    return path


# ============================================================================== schema instances
_PATTERNS = {
    r"^[0-9a-f]{64}$": "0" * 64,
    r"^#[0-9a-fA-F]{6}$": "#000000",
    r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$": "1.0.0-rc.1",
    r"^L\d{3,}\.\d{2,}$": "L001.01",
    r"^[A-Z]{1,2}$": "A",
    r"^\d+/\d+$": "4/4",
    r"^[a-z][a-z-]*#\d+$": "intro#1",
    r"^https://": "https://example.invalid/",
}


def _from_pattern(p: str) -> str:
    if p in _PATTERNS:
        return _PATTERNS[p]
    m = re.match(r"^\^([A-Z]+)\\d\{(\d+),\}\$$", p)
    if m:
        return m.group(1) + "1".zfill(int(m.group(2)))
    m = re.match(r"^\^([A-Z]+)\[1-9\]\\d\*\$$", p)
    if m:
        return m.group(1) + "1"
    if p.startswith("^mvh/"):
        return p[1:] + "x"
    return "x"


def _resolve(schema: dict, root: dict) -> dict:
    from mvh.contract import schemas

    ref = schema.get("$ref")
    if not ref:
        return schema
    sid = ref.replace(schemas.catalog.SCHEMA_BASE, "").replace(".schema.json", "")
    return schemas.load(sid)


def instance_of(schema: dict, root: dict | None = None, prefer_null: bool = True) -> Any:
    """A minimal instance that satisfies ``schema`` (required properties only; nullable -> null)."""
    root = root or schema
    schema = _resolve(schema, root)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "allOf" in schema:
        out: dict = {}
        for s in schema["allOf"]:
            v = instance_of(s, root, prefer_null)
            if isinstance(v, dict):
                out.update(v)
        base = {k: v for k, v in schema.items() if k != "allOf"}
        if base.get("properties"):
            v = instance_of(base, root, prefer_null)
            if isinstance(v, dict):
                out.update(v)
        return out
    if "anyOf" in schema or "oneOf" in schema:
        return instance_of((schema.get("anyOf") or schema.get("oneOf"))[0], root, prefer_null)
    t = schema.get("type")
    types = t if isinstance(t, list) else [t] if t else []
    if prefer_null and "null" in types:
        return None
    t = next((x for x in types if x != "null"), None)
    if t is None and "properties" in schema:
        t = "object"
    if t == "object":
        props = schema.get("properties", {})
        return {k: instance_of(props.get(k, {}), root, prefer_null) for k in schema.get("required", [])}
    if t == "array":
        n = int(schema.get("minItems", 0))
        return [instance_of(schema.get("items", {}), root, prefer_null) for _ in range(n)]
    if t == "string":
        return _from_pattern(schema["pattern"]) if "pattern" in schema else "x"
    if t in ("number", "integer"):
        lo = schema.get("minimum", schema.get("exclusiveMinimum"))
        v = lo if lo is not None else 0
        if "exclusiveMinimum" in schema:
            v = v + 1
        hi = schema.get("maximum")
        if hi is not None and v > hi:
            v = hi
        return int(v) if t == "integer" else float(v)
    if t == "boolean":
        return False
    return None


# ============================================================================== skeleton fixture
_MIDI_EMPTY = bytes.fromhex("4d546864000000060000000101e04d54726b0000000400ff2f00")


def make_skeleton_fixture(
    root: Path | str, n_samples: int, sr: int, *, stages: list[str] | None = None
) -> Path:
    """Write a minimal schema-valid fixture for every stub stage (all stages except ingest by default)."""
    from mvh.contract import catalog, curvefile, registry, schemas
    from mvh.contract.events import dumps_events, dumps_json
    from mvh.io import audio as aio
    from mvh.io.wav import write_wav
    from mvh.runner.spec import load_stage_specs

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    specs = load_stage_specs()
    names = stages or [n for n in specs if n != "ingest"]
    prov = instance_of(schemas.load("mvh/envelope/provenance"))
    n100 = -(-n_samples * 100 // sr)
    n1 = -(-n_samples * 1 // sr)
    entries: list[curvefile.ChannelData] = []
    silence = np.zeros((2, n_samples), np.float32)
    for name in names:
        spec = specs[name]
        for o in spec.outputs:
            base = root if o.public else root / "_intermediate" / name
            if o.kind == "curve":
                if not o.public:
                    continue
                for ch in o.channels:
                    if "{" in ch:
                        continue
                    c = registry.channel(ch)
                    n = n1 if registry.CURVE_FILES[c.file].rate_hz == 1 else n100
                    entries.append(curvefile.ChannelData(ch, np.zeros(n, np.float32)))
                continue
            if o.kind == "matrix":
                if o.public:
                    entries.append(curvefile.ChannelData("spectrum128", np.zeros((n100, 128), np.uint8)))
                elif o.required:
                    p = base / o.path
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(np.zeros((n100, 4), "<f4").tobytes())
                continue
            if not o.required:
                continue
            rel = o.path
            if o.is_pattern:
                rel = re.sub(r"\{stem\}", "vocals", rel)
                rel = re.sub(r"\{src\}", "bass", rel)
                rel = re.sub(r"\{[a-z]+\}", "x", rel)
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if o.kind == "events":
                ev = o.events or ""
                ev = ev.replace("{src}", "bass")
                ed = catalog.event_def(ev)
                env = {
                    "schema": "mvh/" + ed.schema_id,
                    "schema_version": catalog.CONTRACT_VERSION,
                    "name": ev,
                    "kind": ed.kind,
                    "fields": {f.name: {"unit": f.unit, "type": f.type} for f in ed.fields},
                    "provenance": prov,
                    "items": [],
                }
                p.write_text(dumps_events(env), encoding="utf-8", newline="\n")
            elif o.kind == "json":
                obj = instance_of(schemas.load(o.schema)) if o.schema else {}
                p.write_text(dumps_json(obj), encoding="utf-8", newline="\n")
            elif o.kind == "table":
                t = catalog.TABLES_BY_PATH.get(o.path)
                cols = [c.name for c in t.columns] if t else ["t"]
                p.write_text((t.sep if t else ",").join(cols) + "\n", encoding="utf-8", newline="\n")
            elif o.kind == "midi":
                p.write_bytes(_MIDI_EMPTY)
            elif o.kind == "audio":
                if p.suffix == ".wav":
                    write_wav(p, silence, sr)
                elif p.suffix == ".flac":
                    aio.encode_flac(silence, sr, p)
                else:
                    p.write_bytes(b"")
            else:
                p.write_text("stub\n", encoding="utf-8", newline="\n")
    if entries:
        curvefile.assemble(root, entries)
    (root / ".done.json").write_text(
        json.dumps({"generator": "mvh.testing.make_skeleton_fixture", "n_samples": n_samples, "sr": sr})
        + "\n",
        encoding="utf-8",
    )
    return root
