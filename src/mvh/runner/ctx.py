# ruff: noqa: E501  (long catalogue tables / docstrings)
"""The runner's implementation of the frozen stage interface (``spec.Ctx``, ``spec.Upstream``,
``spec.Writer``).

Runs inside the stage's child process (``mvh.runner.child``). The writer writes into the stage's staging dir
(``.cache/<stage>/.tmp-*``), which the parent renames to ``.cache/<stage>/<key>/`` and publishes.

Rules enforced here (CONTRACT §10):
* reads only through declared deps (``UndeclaredDependency``); ``ctx.audio('mix')`` is allowed everywhere
  (D8);
* writes only declared outputs (``UndeclaredOutput``); a ``<x>.wav`` float twin is allowed next to a declared
  ``<x>.flac`` (D23); JSON is validated against the declared schema; every write is atomic;
* curves go to ``_mvh/curves/<file>/<channel>.f32`` (+ meta) and are packed by the runner's finalize step
  (D20).
"""

from __future__ import annotations

import csv
import io as _io
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from mvh.contract import catalog, registry
from mvh.contract.events import EventFile, dumps_events, dumps_json, make_envelope, read_events
from mvh.contract.ids import DRUM_SUBSTEMS, STEM_NAMES
from mvh.io import atomic
from mvh.io.wav import read_wav

from .cache import DONE, MVH_DIR
from .spec import (
    Audio,
    Curve,
    Output,
    StageError,
    StageSpec,
    UndeclaredDependency,
    UndeclaredOutput,  # noqa: F401
)

__all__ = ["StageWriter", "CacheUpstream", "StageCtx", "output_regex", "match_output", "provenance_block"]

_PH = re.compile(r"\{(src|stem|sub|voice|fps|name)\}")
_PH_VALUE = r"[A-Za-z0-9_.-]+"


def output_regex(path: str, restrict: Sequence[tuple[str, Sequence[str]]] = ()) -> re.Pattern[str]:
    allowed = {k: v for k, v in restrict}
    parts = _PH.split(path)
    rx = ""
    for i, part in enumerate(parts):
        if i % 2 == 0:
            rx += re.escape(part)
        else:
            val = "|".join(re.escape(v) for v in allowed[part]) if part in allowed else _PH_VALUE
            rx += f"(?P<{part}_{i}>{val})"
    return re.compile("^" + rx + "$")


def match_output(spec: StageSpec, rel: str, kinds: Sequence[str] | None = None) -> Output | None:
    """The declared output a path belongs to (exact, pattern, or the .wav twin of a declared .flac)."""
    for o in spec.outputs:
        if kinds and o.kind not in kinds:
            continue
        if o.kind in ("curve",) or (o.kind == "matrix" and o.public):
            continue
        if o.path == rel or (o.is_pattern and output_regex(o.path, o.restrict).match(rel)):
            return o
    if rel.endswith(".wav"):
        flac = rel[:-4] + ".flac"
        for o in spec.outputs:
            if o.kind == "audio" and (o.path == flac or (o.is_pattern and output_regex(o.path, o.restrict).match(flac))):
                return o
    return None


def provenance_block(
    job: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
    fallbacks: Sequence[str] = (),
    confidence: float | None = None,
) -> dict[str, Any]:
    """Deterministic provenance (envelope/provenance): no timestamps or hosts."""
    extra = dict(extra or {})
    p: dict[str, Any] = {
        "stage": job["stage"],
        "stage_version": job["stage_version"],
        "contract_version": job["contract_version"],
        "key": job["key"],
        "params": dict(job["params"]),
        "models": list(job.get("models_prov", [])),
        "tools": list(job.get("tools", [])),
        "device": job.get("device", "cpu"),
        "upstream": {k: v["key"] for k, v in sorted(job.get("upstream", {}).items())},
        "overrides_applied": [{"key": k, "value": v} for k, v in sorted(job.get("overrides", {}).items())],
        "fallbacks": list(fallbacks),
    }
    for k in ("tools", "models"):
        if k in extra:
            seen = {json.dumps(x, sort_keys=True) for x in p[k]}
            p[k] = p[k] + [x for x in extra.pop(k) if json.dumps(x, sort_keys=True) not in seen]
    if "overrides_applied" in extra:
        p["overrides_applied"] = list(extra.pop("overrides_applied"))
    notes = list(extra.pop("notes", []))
    if notes:
        p["notes"] = [str(n) for n in notes]
    if confidence is not None:
        p["confidence"] = float(confidence)
    for k, v in extra.items():
        p.setdefault(k, v)
    return p


def _validate(obj: Any, schema: str | None, what: str) -> None:
    if not schema:
        return
    from mvh.contract import schemas

    errs = schemas.validate(obj, schema)
    if errs:
        raise StageError(f"{what} does not match {schema}: " + "; ".join(errs[:5]))


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        if not math.isfinite(v):
            return ""
        return repr(round(v, 6))
    return str(v)


# ============================================================================================ Writer
@dataclass
class StageWriter:
    spec: StageSpec
    out: Path  # staging dir
    job: Mapping[str, Any]
    written: dict[str, dict[str, Any]] = field(default_factory=dict)  # rel -> {kind, public, schema, events}
    curves_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    matrices: dict[str, dict[str, Any]] = field(default_factory=dict)
    envelopes: list[str] = field(default_factory=list)  # rels whose provenance is re-stamped after run

    # ---------------------------------------------------------------- helpers
    def _out(self, rel: str, kinds: Sequence[str] | None = None) -> Output:
        if rel.startswith(MVH_DIR + "/") or rel in (
            "overrides.json",
            "meaning/intent.md",
            "meaning/authored.json",
        ):
            raise UndeclaredOutput(f"{self.spec.name}: {rel} is reserved (runner or user input)")
        o = match_output(self.spec, rel, kinds)
        if o is None:
            raise UndeclaredOutput(f"{self.spec.name} did not declare output {rel!r}")
        return o

    def _path(self, rel: str) -> Path:
        p = self.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _note(self, rel: str, o: Output, kind: str | None = None) -> None:
        self.written[rel] = {
            "kind": kind or o.kind,
            "public": o.public,
            "schema": o.schema,
            "events": o.events,
            "declared": o.path,
        }

    def _prov(self) -> dict[str, Any]:
        return provenance_block(self.job)

    # ---------------------------------------------------------------- Writer protocol
    def events(
        self,
        name: str,
        items: Sequence[Mapping[str, Any]],
        *,
        kind: str | None = None,
        fields: Mapping[str, Mapping[str, Any]] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Path:
        o = None
        rel = None
        for cand in self.spec.outputs:
            if cand.kind != "events" or not cand.events:
                continue
            if cand.events == name or (("{" in cand.events) and output_regex(cand.events, cand.restrict).match(name)):
                o = cand
                if cand.is_pattern:
                    m = output_regex(cand.events, cand.restrict).match(name)
                    vals = {k.rsplit("_", 1)[0]: v for k, v in (m.groupdict() if m else {}).items()}
                    rel = _PH.sub(lambda mm: vals.get(mm.group(1), mm.group(0)), cand.path)
                else:
                    rel = cand.path
                break
        if o is None or rel is None:
            raise UndeclaredOutput(f"{self.spec.name} did not declare events {name!r}")
        try:
            env = make_envelope(name, items, self._prov(), kind=kind, fields=fields)
        except KeyError:
            # an additive events name not in the catalogue yet (folded in by the integrator in W3)
            env = {
                "schema": o.schema or f"mvh/events/{name}",
                "schema_version": self.job["contract_version"],
                "name": name,
                "kind": kind or "event",
                "fields": dict(fields or {}),
                "provenance": self._prov(),
                "items": sorted(
                    ({**it, "t": round(float(it["t"]), 6)} for it in items), key=lambda d: d["t"]
                ),
            }
        if extra:
            for k, v in extra.items():
                if k in ("items", "provenance", "schema", "name"):
                    raise StageError(f"events extra may not override {k!r}")
                env[k] = v
        _validate(
            env, o.schema if o.schema and o.schema.startswith("mvh/events/") else "mvh/envelope/events", rel
        )
        p = self._path(rel)
        atomic.write_text(p, dumps_events(env))
        self._note(rel, o, "events")
        self.envelopes.append(rel)
        return p

    def json(self, rel: str, obj: Any) -> Path:
        o = self._out(rel, ("json",))
        if isinstance(obj, dict) and o.schema:
            from mvh.contract import schemas

            try:
                props = schemas.load(o.schema).get("properties", {})
            except OSError:
                props = {}
            if "provenance" in props and "provenance" not in obj:
                obj = {**obj, "provenance": self._prov()}
                self.envelopes.append(rel)
        _validate(obj, o.schema, rel)
        p = self._path(rel)
        atomic.write_text(p, dumps_json(obj))
        self._note(rel, o)
        return p

    def text(self, rel: str, text: str) -> Path:
        o = self._out(rel, ("text", "table", "json"))
        p = self._path(rel)
        atomic.write_text(p, text.replace("\r\n", "\n"))
        self._note(rel, o)
        return p

    def table(self, rel: str, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> Path:
        o = self._out(rel, ("table",))
        tdef = catalog.TABLES_BY_PATH.get(o.path)
        sep = tdef.sep if tdef else ("\t" if rel.endswith(".tsv") else ",")
        if sep == "\t":
            lines = ["\t".join(columns)]
            for r in rows:
                lines.append(
                    "\t".join(
                        _cell(r.get(c)).replace("\t", " ").replace("\r", " ").replace("\n", " ")
                        for c in columns
                    )
                )
            text = "\n".join(lines) + "\n"
        else:
            buf = _io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(list(columns))
            for r in rows:
                w.writerow([_cell(r.get(c)) for c in columns])
            text = buf.getvalue()
        p = self._path(rel)
        atomic.write_text(p, text)
        self._note(rel, o)
        return p

    def bytes(self, rel: str, data: bytes) -> Path:
        o = self._out(rel)
        p = self._path(rel)
        atomic.write_bytes(p, bytes(data))
        self._note(rel, o)
        return p

    def midi(self, rel: str, data: bytes) -> Path:
        o = self._out(rel, ("midi",))
        p = self._path(rel)
        atomic.write_bytes(p, bytes(data))
        self._note(rel, o)
        return p

    def copy(self, rel: str, src: Path) -> Path:
        o = self._out(rel)
        src = Path(src)
        if not src.is_file():
            raise StageError(f"copy source missing: {src}")
        if rel.endswith(".json") and o.schema:
            with open(src, encoding="utf-8") as fh:
                obj = json.load(fh)
            _validate(obj, o.schema, rel)
        p = self._path(rel)
        atomic.copy_file(src, p)
        self._note(rel, o)
        return p

    def audio(self, rel: str, samples: Any, sr: int) -> Path:
        o = self._out(rel, ("audio",))
        a = np.asarray(samples, dtype=np.float32)
        if a.ndim == 1:
            a = a[None, :]
        if not np.isfinite(a).all():
            raise StageError(f"{rel}: audio contains NaN/inf")
        from mvh.io import audio as aio

        p = self._path(rel)
        if rel.endswith(".flac"):
            aio.encode_flac(a, sr, p)
            self._note(rel, o)
            twin = rel[:-5] + ".wav"
            if float(np.abs(a).max(initial=0.0)) > 1.0:
                aio.encode_wav(a, sr, self._path(twin))
                self._note(twin, o)
            elif (self.out / twin).exists():
                atomic.unlink_retry(self.out / twin)
                self.written.pop(twin, None)
        elif rel.endswith(".wav"):
            aio.encode_wav(a, sr, p)
            self._note(rel, o)
        elif rel.endswith(".opus"):
            aio.encode_opus(a, sr, p, int(self.job["params"].get("preview_bitrate_kbps", 96)))
            self._note(rel, o)
        else:
            raise StageError(f"{rel}: audio outputs are .flac, .wav or .opus")
        return p

    def curves(
        self,
        file_id: str,
        channels: Mapping[str, Any],
        *,
        meta: Mapping[str, Mapping[str, Any]] | None = None,
        rate_hz: float | None = None,
    ) -> None:
        if file_id not in registry.CURVE_FILES:
            raise UndeclaredOutput(f"unknown curve file {file_id!r}")
        cf = registry.CURVE_FILES[file_id]
        decl = [o for o in self.spec.outputs if o.kind == "curve" and o.path == cf.path]
        if not decl:
            raise UndeclaredOutput(f"{self.spec.name} did not declare curve file {cf.path}")
        pats = [p for o in decl for p in o.channels]
        if rate_hz is not None and float(rate_hz) != float(cf.rate_hz):
            raise StageError(f"{file_id} is a {cf.rate_hz} Hz file, got rate_hz={rate_hz}")
        expect = self._expected_frames(cf.rate_hz)
        meta = dict(meta or {})
        for cid, values in channels.items():
            c = registry.match_channel(cid)
            if c is None or c.file != file_id:
                raise UndeclaredOutput(f"channel {cid!r} is not a {file_id} channel in the registry")
            if not any(cid == p or ("{" in p and registry.match_channel(p) is c) for p in pats):
                raise UndeclaredOutput(f"{self.spec.name} did not declare channel {cid!r}")
            v = np.asarray(values, dtype="<f4").reshape(-1)
            if expect is not None and v.size != expect:
                raise StageError(
                    f"channel {cid}: {v.size} frames, expected {expect} "
                    f"(ceil(n_samples * {cf.rate_hz:g} / sample_rate))"
                )
            if not c.nan_aware and np.isnan(v).any():
                raise StageError(f"{cid}: NaN is only allowed in NaN-aware pitch channels")
            if np.isinf(v).any():
                raise StageError(f"{cid}: inf is not allowed (floor dB channels)")
            p = self._path(f"{MVH_DIR}/curves/{file_id}/{cid}.f32")
            atomic.write_bytes(p, v.tobytes())
            m = dict(meta.get(cid, {}))
            for k in ("id", "file", "offset_bytes", "n", "rate_hz"):
                m.pop(k, None)
            # keep only per-song fields that differ from the registry defaults (norm lo/hi, description, ...)
            base = registry.index_entry(c, cid)
            keep = {}
            for k, val in m.items():
                if k == "norm" and isinstance(val, Mapping):
                    for nk in ("lo", "hi"):
                        if nk in val and val[nk] is not None:
                            keep[nk] = float(val[nk])
                elif k in ("lo", "hi"):
                    keep[k] = float(val)
                elif base.get(k) != val:
                    keep[k] = val
            self.curves_meta.setdefault(file_id, {})[cid] = {"n": int(v.size), "meta": keep}

    def matrix(self, file_id: str, array: Any, *, meta: Mapping[str, Any] | None = None) -> None:
        a = np.asarray(array)
        if a.ndim != 2:
            raise StageError(f"matrix {file_id} must be 2-D [frames x k]")
        if file_id in registry.CURVE_FILES:
            cf = registry.CURVE_FILES[file_id]
            if not any(o.kind == "matrix" and o.path == cf.path for o in self.spec.outputs):
                raise UndeclaredOutput(f"{self.spec.name} did not declare matrix {cf.path}")
            expect = self._expected_frames(cf.rate_hz)
            if expect is not None and a.shape[0] != expect:
                raise StageError(f"matrix {file_id}: {a.shape[0]} frames, expected {expect}")
            arr = np.ascontiguousarray(a, dtype=np.uint8 if cf.dtype == "u8" else "<f4")
            atomic.write_bytes(self._path(f"{MVH_DIR}/matrices/{file_id}.bin"), arr.tobytes())
            m = {k: (list(map(float, v)) if k == "band_edges_hz" else v) for k, v in dict(meta or {}).items()}
            self.matrices[file_id] = {"shape": list(arr.shape), "dtype": cf.dtype, "public": True, "meta": m}
            return
        # cache-only matrix (allin1 activations / embeddings): row-major float32 at the declared path
        cand = [
            o
            for o in self.spec.outputs
            if o.kind == "matrix" and not o.public and Path(o.path).stem == file_id
        ]
        if not cand:
            raise UndeclaredOutput(f"{self.spec.name} did not declare matrix {file_id!r}")
        o = cand[0]
        arr = np.ascontiguousarray(a, dtype="<f4")
        atomic.write_bytes(self._path(o.path), arr.tobytes())
        self.matrices[file_id] = {
            "shape": list(arr.shape),
            "dtype": "f32le",
            "public": False,
            "path": o.path,
            "meta": dict(meta or {}),
        }
        self._note(o.path, o, "matrix")

    def _expected_frames(self, rate_hz: float) -> int | None:
        tb = self.job.get("timebase")
        if not tb:
            return None
        n, sr = int(tb["n_samples"]), int(tb["sample_rate"])
        r = float(rate_hz)
        if r.is_integer():
            return -(-n * int(r) // sr)
        return int(math.ceil(n * r / sr))

    # ---------------------------------------------------------------- post-run
    def restamp(self, prov: Mapping[str, Any]) -> None:
        """Merge the final provenance (StageResult extras, fallbacks) into every envelope this stage wrote."""
        for rel in dict.fromkeys(self.envelopes):
            p = self.out / rel
            with open(p, encoding="utf-8") as fh:
                obj = json.load(fh)
            obj["provenance"] = dict(prov)
            info = self.written.get(rel, {})
            if info.get("kind") == "events":
                sch = info.get("schema")
                _validate(obj, sch if sch and sch.startswith("mvh/events/") else "mvh/envelope/events", rel)
                atomic.write_text(p, dumps_events(obj))
            else:
                _validate(obj, info.get("schema"), rel)
                atomic.write_text(p, dumps_json(obj))


# ============================================================================================ Upstream
class CacheUpstream:
    """Read-only view of one upstream stage's cache dir."""

    def __init__(self, stage: str, root: Path, record: Mapping[str, Any] | None = None):
        self.stage = stage
        self.root = Path(root)
        self._record = record
        self._audio: dict[tuple[str, int | None, bool], Audio] = {}

    @property
    def record(self) -> Mapping[str, Any]:
        if self._record is None:
            with open(self.root / DONE, encoding="utf-8") as fh:
                self._record = json.load(fh)
        return self._record

    def path(self, rel: str) -> Path:
        p = self.root / rel
        if not p.is_file():
            raise StageError(f"upstream {self.stage} has no {rel}")
        return p

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def json(self, rel: str) -> Any:
        with open(self.path(rel), encoding="utf-8") as fh:
            return json.load(fh)

    def text(self, rel: str) -> str:
        with open(self.path(rel), encoding="utf-8") as fh:
            return fh.read()

    def table(self, rel: str) -> list[dict[str, str]]:
        sep = "\t" if rel.endswith(".tsv") else ","
        with open(self.path(rel), encoding="utf-8", newline="") as fh:
            if sep == "\t":
                lines = fh.read().split("\n")
                head = lines[0].split("\t") if lines else []
                return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln]
            return list(csv.DictReader(fh))

    def events(self, name: str) -> EventFile:
        for rel, info in self.record.get("outputs", {}).items():
            if info.get("events") and (info["events"] == name or output_regex(info["events"]).match(name)):
                if info["events"] == name or rel.endswith(f"/{name}.json") or rel.endswith(f"{name}.json"):
                    return read_events(self.root / rel)
        try:
            ed = catalog.event_def(name)
            rel = ed.file.replace("{src}", name.split(".", 1)[1]) if "{src}" in ed.file else ed.file
            if (self.root / rel).is_file():
                return read_events(self.root / rel)
        except KeyError:
            pass
        raise StageError(f"upstream {self.stage} has no events {name!r}")

    def curve(self, channel_id: str) -> Curve:
        c = registry.match_channel(channel_id)
        if c is None:
            raise StageError(f"unknown curve channel {channel_id!r}")
        p = self.root / MVH_DIR / "curves" / c.file / f"{channel_id}.f32"
        if not p.is_file():
            raise StageError(f"upstream {self.stage} has no curve {channel_id!r}")
        v = np.fromfile(p, dtype="<f4")
        meta = registry.index_entry(c, channel_id)
        extra = self.record.get("curves", {}).get(c.file, {}).get(channel_id, {}).get("meta", {})
        if meta.get("norm") is not None:
            meta["norm"].update({k: extra[k] for k in ("lo", "hi") if k in extra})
        meta.update({k: v2 for k, v2 in extra.items() if k not in ("lo", "hi")})
        rate = registry.CURVE_FILES[c.file].rate_hz
        return Curve(channel_id, v, float(rate), meta)

    def matrix(self, file_id: str) -> tuple[Any, Mapping[str, Any]]:
        info = self.record.get("matrices", {}).get(file_id)
        if info is None:
            raise StageError(f"upstream {self.stage} has no matrix {file_id!r}")
        if info.get("public"):
            p = self.root / MVH_DIR / "matrices" / f"{file_id}.bin"
            dt = np.uint8 if info["dtype"] == "u8" else "<f4"
        else:
            p = self.root / info["path"]
            dt = "<f4"
        a = np.fromfile(p, dtype=dt).reshape(info["shape"])
        return a, {**info.get("meta", {}), "shape": info["shape"], "dtype": info["dtype"]}

    def audio(self, rel: str, *, sr: int | None = None, mono: bool = False) -> Audio:
        k = (rel, sr, mono)
        if k in self._audio:
            return self._audio[k]
        p = self.path(rel)
        if p.suffix.lower() == ".wav":
            try:
                x, native = read_wav(p)
            except ValueError:
                x, native = None, 0
            if x is not None and (sr is None or sr == native):
                if mono and x.shape[0] > 1:
                    x = x.mean(axis=0, dtype=np.float64).astype(np.float32)[None, :]
                a = Audio(x, native, p)
                self._audio[k] = a
                return a
        from mvh.io import audio as aio

        d = aio.decode(p, sr=sr, mono=mono)
        a = Audio(d.samples, d.sr, p)
        self._audio[k] = a
        return a


# ============================================================================================ Ctx
class StageCtx:
    """spec.Ctx for one stage run (child process)."""

    def __init__(self, spec: StageSpec, job: Mapping[str, Any], writer: StageWriter, log: logging.Logger):
        self.spec = spec
        self.job = job
        self.slug = job["slug"]
        self.params = dict(job["params"])
        self.profile = job["profile"]
        self.threads = int(job["threads"])
        self.device = job.get("device", "cpu")
        self.offline = bool(job.get("offline"))
        self.scratch = Path(job["scratch"])
        self.log = log
        self.overrides = dict(job.get("overrides", {}))
        self.writer = writer
        self.song_dir = Path(job["song_dir"])
        self._ups: dict[str, CacheUpstream] = {}
        self._http = None
        self.worker_runs: list[dict[str, Any]] = []

    # ---------------------------------------------------------------- reads
    def upstream(self, stage: str) -> CacheUpstream:
        if stage not in self.spec.deps:
            raise UndeclaredDependency(f"{self.spec.name} reads {stage!r} but does not declare it in deps")
        return self._upstream(stage)

    def _upstream(self, stage: str) -> CacheUpstream:
        if stage not in self._ups:
            info = self.job.get("upstream", {}).get(stage)
            if info is None:
                raise StageError(f"upstream {stage} has no cache entry (run it first)")
            self._ups[stage] = CacheUpstream(stage, Path(info["dir"]))
        return self._ups[stage]

    def _producer_events(self, name: str) -> str:
        try:
            return catalog.producer_of_events(name)
        except KeyError:
            for d in self.spec.deps:
                rec = self._upstream(d).record if d in self.job.get("upstream", {}) else {}
                if any(i.get("events") == name for i in rec.get("outputs", {}).values()):
                    return d
        raise StageError(f"no stage produces events {name!r}")

    def events(self, name: str) -> EventFile:
        return self.upstream(self._producer_events(name)).events(name)

    def curve(self, channel_id: str) -> Curve:
        c = registry.match_channel(channel_id)
        if c is None:
            raise StageError(f"unknown curve channel {channel_id!r}")
        return self.upstream(c.stage).curve(channel_id)

    def audio(self, name: str = "mix", *, sr: int | None = None, mono: bool = False) -> Audio:
        if name == "mix":
            ing = self.job.get("ingest_dir")
            if not ing:
                raise StageError("the canonical mix is not available (ingest has not run)")
            up = self._ups.get("ingest") or CacheUpstream("ingest", Path(ing))
            self._ups.setdefault("ingest", up)
            return up.audio("canonical.wav", sr=sr, mono=mono)
        if name == "preview":
            return self.upstream("ingest").audio("audio/preview.opus", sr=sr, mono=mono)
        if name.startswith("fast:"):
            return self.upstream("separate_fast").audio(f"fast/{name[5:]}.wav", sr=sr, mono=mono)
        if name in STEM_NAMES or (name.startswith("drums_") and name[6:] in DRUM_SUBSTEMS):
            up = self.upstream("separate_hq")
            base = f"stems/{name}" if name in STEM_NAMES else f"stems/drums/{name[6:]}"
            rel = base + ".wav" if up.exists(base + ".wav") else base + ".flac"
            return up.audio(rel, sr=sr, mono=mono)
        raise StageError(f"unknown audio name {name!r} (mix, preview, fast:<stem>, <stem>, drums_<sub>)")

    def model(self, model_id: str):
        if model_id not in self.spec.models:
            raise UndeclaredDependency(
                f"{self.spec.name} uses model {model_id!r} but does not list it in STAGE.models"
            )
        from . import models

        try:
            return models.handle(model_id)
        except models.ModelError as e:
            raise StageError(str(e)) from e

    def external(self, name: str) -> Path | None:
        for e in self.spec.external_inputs:
            if e.name == name:
                return _resolve_external(e.path, self.job)
        raise UndeclaredDependency(f"{self.spec.name} has no external input {name!r}")

    def http(self):
        if not self.spec.network:
            raise StageError(f"{self.spec.name} is not a network stage (STAGE.network=False)")
        if self._http is None:
            from .http import CachedHttp

            self._http = CachedHttp(Path(self.job["http_dir"]), offline=self.offline)
        return self._http

    def ffmpeg(self) -> Path:
        from mvh.io.ffmpeg import resolve_ffmpeg

        return resolve_ffmpeg()

    # ---------------------------------------------------------------- sep worker (D29)
    def worker(
        self,
        inputs: Mapping[str, Any],
        *,
        params: Mapping[str, Any] | None = None,
        models: Sequence[str] | None = None,
        variants: Sequence[str] | None = None,
        timeout: float | None = None,
        hold_slot: bool | None = None,
        stage: str | None = None,
    ):
        """Run this stage's inference in the sep worker env (env='sep' stages). ``inputs`` maps names to
        Audio,
        (samples, sr) or float32 WAV paths; returns a sepworker.WorkerResult (``.outputs``, ``.read(rel)``,
        ``.variant``, ``.fallbacks``). Model ids must be in STAGE.models; their local paths go into
        job.json."""
        from .sepworker import run_worker

        if self.spec.env != "sep" and stage is None:
            raise StageError(f"{self.spec.name} is not an env='sep' stage")
        mpaths = {}
        for mid in models or ():
            h = self.model(mid)
            mpaths[mid] = {k: str(v) for k, v in h.files.items()}
        hold = self.job.get("heavy_locks", True) if hold_slot is None else hold_slot
        res = run_worker(
            stage or self.spec.name,
            stage_version=self.spec.version,
            params=dict(params or self.params),
            inputs=inputs,
            scratch=self.scratch / f"sep-{len(self.worker_runs)}",
            threads=self.threads,
            models=mpaths,
            variants=variants,
            offline=True,
            timeout=timeout,
            hold_slot=bool(hold),
            log=self.log.info,
        )
        self.worker_runs.append(
            {
                "variant": res.variant,
                "device": res.device,
                "fallbacks": res.fallbacks,
                "attempts": [{k: v for k, v in a.items() if k != "log_tail"} for a in res.attempts],
                "seconds": round(res.seconds, 3),
            }
        )
        self.device = res.device
        return res


def _resolve_external(path: str, job: Mapping[str, Any]) -> Path | None:
    if path.startswith("param:"):
        v = job.get("params_ext", {}).get(path[6:])
        return Path(v) if v and Path(v).is_file() else None
    if path.startswith("http:"):
        d = Path(job["http_dir"])
        return d if d.is_dir() else None
    p = Path(job["song_dir"]) / path.split("#", 1)[0]
    return p if p.is_file() else None
