"""Reference reader/packer for curves/*.f32, curves/spectrum128.u8 and curves/index.json (PLAN §4.1).

Layout rules (frozen):
* ``*.f32`` files are float32 little-endian, **column-major**: channel j of a file with n frames occupies
  bytes [offset_j, offset_j + 4n) with offset_j = 4 * n * j; JS reads it as ``new Float32Array(buf, off, n)``.
* Every channel of one file has the same length n = ceil(n_samples * rate / sample_rate) (conventions.n_curve_frames).
* Channel order within a file: registry declaration order of the channel (family), then concrete id (string sort).
* ``spectrum128.u8`` is row-major uint8 [n x 128]; value = offset + scale * u8 with scale = 1/255, offset = 0.
* NaN appears only in channels with special.nan = 'unvoiced'; dB channels are floored (special.floor), never -inf.

Runner use: ``assemble(out_dir, entries)`` packs the channels handed to ``ctx.writer.curves`` by every stage.
Stdlib + numpy.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from . import registry
from .catalog import CONTRACT_VERSION

__all__ = ["ChannelData", "pack", "index_bytes", "assemble", "read_index", "read_channel", "read_matrix", "channel_order_key"]


@dataclass
class ChannelData:
    id: str
    values: np.ndarray                 # 1-D float32 (or 2-D uint8 [n x 128] for spectrum128)
    meta: Mapping[str, Any] | None = None   # per-song registry fields (norm lo/hi, description override, ...)


_ORDER = {c.id: i for i, c in enumerate(registry.CHANNELS.values())}


def channel_order_key(cid: str) -> tuple[int, str]:
    c = registry.match_channel(cid)
    return (_ORDER[c.id] if c else 1 << 30, cid)


def _atomic_write(path: Path, data: bytes) -> None:
    """Unique temp file next to the target, then os.replace retried on PermissionError (W4P-2: a fixed
    ``<name>.tmp`` collided between two writers and was left behind when the replace failed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
        for k in range(12):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if k == 11:
                    raise
                time.sleep(min(0.05 * (2**k), 2.0))
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def index_bytes(index: Mapping[str, Any]) -> bytes:
    """curves/index.json exactly as ``assemble`` writes it."""
    return (json.dumps(index, ensure_ascii=False, indent=1, allow_nan=False) + "\n").encode("utf-8")


def assemble(out_dir: Path | str, entries: Iterable[ChannelData], *, write: bool = True) -> dict[str, Any]:
    """Pack channels into curves/<file> and return (and write) curves/index.json.

    Unknown channel ids raise KeyError (add them to the registry first: that is a contract change).
    Length mismatches within one file raise ValueError."""
    out = Path(out_dir)
    index, blobs = pack(entries)
    if write:
        for rel, data in blobs.items():
            _atomic_write(out / rel, data)
        _atomic_write(out / "curves/index.json", index_bytes(index))
    return index


def pack(entries: Iterable[ChannelData]) -> tuple[dict[str, Any], dict[str, bytes]]:
    """(curves/index.json document, {song-relative path: bytes} of every curve file), writing nothing.

    W4P-2: the runner writes the files itself, so a file held open by a reader keeps its old version."""
    blobs: dict[str, bytes] = {}
    per_file: dict[str, list[ChannelData]] = {}
    for e in entries:
        c = registry.channel(e.id)
        per_file.setdefault(c.file, []).append(e)
    index: dict[str, Any] = {"schema": "mvh/curves_index", "schema_version": CONTRACT_VERSION, "files": {}, "channels": []}
    for fid in [f for f in registry.CURVE_FILES if f in per_file]:
        cf = registry.CURVE_FILES[fid]
        chans = sorted(per_file[fid], key=lambda e: channel_order_key(e.id))
        if cf.layout == "row-major":
            (e,) = chans
            arr = np.ascontiguousarray(e.values, dtype=np.uint8)
            if arr.ndim != 2:
                raise ValueError(f"{fid} must be 2-D [frames x k]")
            n, k = arr.shape
            blobs[cf.path] = arr.tobytes()
            finfo: dict[str, Any] = {"path": cf.path, "dtype": cf.dtype, "layout": cf.layout, "rate_hz": cf.rate_hz,
                                     "n_frames": int(n), "n_channels": int(k), "quant": {"scale": 1 / 255, "offset": 0.0}}
            meta = dict(e.meta or {})
            if "band_edges_hz" in meta:
                finfo["band_edges_hz"] = [float(x) for x in meta.pop("band_edges_hz")]
            index["files"][fid] = finfo
            index["channels"].append(_entry(e.id, fid, 0, int(n), cf.rate_hz, meta))
            continue
        n = None
        blocks = []
        for e in chans:
            v = np.asarray(e.values, dtype="<f4").reshape(-1)
            if n is None:
                n = v.size
            elif v.size != n:
                raise ValueError(f"{fid}: channel {e.id} has {v.size} frames, expected {n}")
            c = registry.channel(e.id)
            if not c.nan_aware and np.isnan(v).any():
                raise ValueError(f"{e.id}: NaN is only allowed in NaN-aware pitch channels")
            if np.isinf(v).any():
                raise ValueError(f"{e.id}: inf values are not allowed (floor dB channels)")
            blocks.append(v)
        blobs[cf.path] = b"".join(b.tobytes() for b in blocks)
        index["files"][fid] = {"path": cf.path, "dtype": cf.dtype, "layout": cf.layout, "rate_hz": cf.rate_hz,
                               "n_frames": int(n or 0), "n_channels": len(chans)}
        for j, e in enumerate(chans):
            index["channels"].append(_entry(e.id, fid, 4 * int(n or 0) * j, int(n or 0), cf.rate_hz, dict(e.meta or {})))
    return index, blobs


def _entry(cid: str, fid: str, off: int, n: int, rate: float, meta: dict[str, Any]) -> dict[str, Any]:
    c = registry.channel(cid)
    e = registry.index_entry(c, cid)
    norm_extra = {k: meta.pop(k) for k in ("lo", "hi") if k in meta}
    if norm_extra and e.get("norm") is not None:
        e["norm"].update({k: float(v) for k, v in norm_extra.items()})
    e.update(meta)
    e.update({"file": fid, "offset_bytes": off, "n": n, "rate_hz": rate})
    order = ["id", "file", "offset_bytes", "n", "rate_hz", "unit", "range", "norm", "resample", "special", "twin", "stage", "description"]
    return {k: e[k] for k in order if k in e} | {k: v for k, v in e.items() if k not in order}


def read_index(song_dir: Path | str) -> dict[str, Any]:
    with open(Path(song_dir) / "curves/index.json", encoding="utf-8") as fh:
        return json.load(fh)


def read_channel(song_dir: Path | str, index: Mapping[str, Any], cid: str) -> tuple[np.ndarray, dict[str, Any]]:
    """(values float32, index entry) of one channel."""
    for e in index["channels"]:
        if e["id"] == cid:
            f = index["files"][e["file"]]
            if f["dtype"] != "f32le":
                raise ValueError(f"{cid} is a matrix; use read_matrix")
            v = np.fromfile(Path(song_dir) / f["path"], dtype="<f4", count=e["n"], offset=e["offset_bytes"])
            return v, dict(e)
    raise KeyError(cid)


def read_matrix(song_dir: Path | str, index: Mapping[str, Any], file_id: str = "spectrum128") -> tuple[np.ndarray, dict[str, Any]]:
    f = index["files"][file_id]
    a = np.fromfile(Path(song_dir) / f["path"], dtype=np.uint8 if f["dtype"] == "u8" else "<f4")
    return a.reshape(f["n_frames"], f["n_channels"]), dict(f)
