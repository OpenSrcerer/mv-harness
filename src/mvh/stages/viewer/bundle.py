"""Data bundle for the file:// read-only viewer (PLAN §9, M6a).

The viewer is one HTML file that also works when opened straight from the disk. Browsers refuse ``fetch`` of
local files, so the *preview data* is inlined: every events file, the ``meta/`` documents, lyrics, meaning, a
reduced ``curves/index.json`` with only the channels the lanes draw, the spectrogram (when it fits), a 1 kHz
min/max waveform pyramid base and, when small enough, ``audio/preview.opus``.  Each file is zlib-compressed and
base64-encoded; ``lib/mvh.js`` reads them through a ``fetch`` shim, so the page uses the same loader as every
video agent (no re-implemented helpers).

Nothing here touches the network or the output folder: inputs come from the stage's declared upstream caches.
"""
from __future__ import annotations

import base64
import fnmatch
import json
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

#: curve channels the lanes and the values panel read (fnmatch patterns); everything else stays out of the page
DEFAULT_CHANNELS: tuple[str, ...] = (
    "bands.bass", "bands.mid", "bands.high", "bands.level", "bands.kick",
    "bands.bass_db", "bands.mid_db", "bands.high_db",
    "loud.momentary_lufs", "loud.short_term_lufs", "loud.short_term", "loud.momentary", "loud.rms_db",
    "dyn.intensity", "dyn.novelty", "tempo.bpm", "rhythm.in_pulse", "rhythm.beat_act", "rhythm.downbeat_act",
    "hits.kick", "hits.mid", "hits.high", "choreo.movement", "choreo.accent",
    "stem.*.level", "stem.*.active", "vocal.*", "inst.*", "mood.*",
)
STEMS_MIX: tuple[str, ...] = ("lead_vocals", "backing_vocals", "drums", "bass", "guitar", "piano", "other")


@dataclass
class Bundle:
    """rel path -> (kind, raw bytes); kind is 'json' | 'text' | 'bin'."""

    files: dict[str, tuple[str, bytes]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # what was left out, machine tags
    sizes: dict[str, int] = field(default_factory=dict)  # rel -> encoded (b64) size

    def add(self, rel: str, kind: str, raw: bytes) -> None:
        self.files[rel] = (kind, raw)

    def encode(self) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for rel in sorted(self.files):
            kind, raw = self.files[rel]
            z = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
            self.sizes[rel] = len(z)
            out[rel] = [kind, len(raw), z]
        return out

    def encoded_size(self, rel: str, kind: str, raw: bytes) -> int:
        return len(base64.b64encode(zlib.compress(raw, 9)))


def _channel_wanted(cid: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(cid, p) for p in patterns)


def upstream_outputs(up: Any) -> dict[str, dict[str, Any]]:
    """rel -> info for the public outputs of one upstream cache (runner record); {} when unavailable."""
    rec = getattr(up, "record", None)
    if not rec:
        return {}
    return {rel: info for rel, info in (rec.get("outputs") or {}).items() if info.get("public", True)}


def waveform_base(samples: np.ndarray, sr: int, hz: int = 1000) -> dict[str, Any]:
    """Per-bin min/max (int8, scaled to the song peak) at ``hz`` bins per second. Deterministic."""
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim == 2:
        x = x.mean(axis=0, dtype=np.float64).astype(np.float32)
    n = int(x.shape[0])
    if n == 0:
        return {"hz": hz, "n": 0, "peak": 0.0, "data": ""}
    nb = int(np.ceil(n * hz / sr))
    idx = np.floor(np.arange(nb, dtype=np.float64) * sr / hz).astype(np.int64)
    idx = np.minimum(idx, n - 1)
    lo = np.minimum.reduceat(x, idx)
    hi = np.maximum.reduceat(x, idx)
    peak = float(max(np.abs(lo).max(), np.abs(hi).max(), 1e-9))
    q = np.empty(nb * 2, dtype=np.int8)
    q[0::2] = np.clip(np.round(lo / peak * 127.0), -127, 127).astype(np.int8)
    q[1::2] = np.clip(np.round(hi / peak * 127.0), -127, 127).astype(np.int8)
    return {"hz": hz, "n": nb, "peak": round(peak, 6), "data": base64.b64encode(q.tobytes()).decode("ascii")}


def pack_curves(
    channels: Mapping[str, tuple[np.ndarray, Mapping[str, Any]]],
    files_meta: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Reduced ``curves/index.json`` + the packed float32 files (column-major, one file per curve-file id)."""
    by_file: dict[str, list[str]] = {}
    for cid, (_arr, meta) in channels.items():
        by_file.setdefault(str(meta.get("file")), []).append(cid)
    files: dict[str, Any] = {}
    chans: list[dict[str, Any]] = []
    blobs: dict[str, bytes] = {}
    for fid in sorted(by_file):
        fm = files_meta.get(fid, {})
        ids = sorted(by_file[fid], key=lambda c: (channels[c][1].get("order", 0), c))
        n = int(channels[ids[0]][0].shape[0])
        buf = bytearray()
        for j, cid in enumerate(ids):
            arr = np.ascontiguousarray(channels[cid][0], dtype="<f4")
            if arr.shape[0] != n:
                continue
            ent = dict(channels[cid][1])
            ent.update({"file": fid, "offset_bytes": len(buf), "n": n})
            chans.append(ent)
            buf += arr.tobytes()
        path = str(fm.get("path") or f"curves/{fid}.f32")
        files[fid] = {
            "path": path, "dtype": "f32le", "layout": "column-major", "rate_hz": fm.get("rate_hz", 100),
            "n_frames": n, "n_channels": len([c for c in chans if c["file"] == fid]),
        }
        blobs[path] = bytes(buf)
    return {"schema": "mvh/envelope/curves_index", "files": files, "channels": chans}, blobs


def collect_curves(ctx: Any, patterns: Iterable[str]) -> tuple[dict[str, tuple[np.ndarray, dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Read the wanted channels from the upstream caches. Returns ({id: (values, index entry)}, {file id: meta})."""
    chans: dict[str, tuple[np.ndarray, dict[str, Any]]] = {}
    files_meta: dict[str, dict[str, Any]] = {}
    from mvh.contract import registry

    for dep in ctx.spec.deps:
        try:
            up = ctx.upstream(dep)
        except Exception:  # noqa: BLE001
            continue
        rec = getattr(up, "record", None) or {}
        for fid, cmap in (rec.get("curves") or {}).items():
            cf = registry.CURVE_FILES.get(fid)
            if cf is not None:
                files_meta[fid] = {"path": cf.path, "rate_hz": cf.rate_hz}
            for cid in sorted(cmap):
                if cid in chans or not _channel_wanted(cid, patterns):
                    continue
                try:
                    c = up.curve(cid)
                except Exception:  # noqa: BLE001
                    continue
                meta = dict(c.meta)
                meta.setdefault("id", cid)
                meta["file"] = fid
                meta.setdefault("rate_hz", c.rate_hz)
                chans[cid] = (np.asarray(c.values, dtype=np.float32), meta)
    return chans, files_meta


def collect_spectrogram(ctx: Any) -> tuple[np.ndarray, dict[str, Any]] | None:
    for dep in ctx.spec.deps:
        try:
            up = ctx.upstream(dep)
        except Exception:  # noqa: BLE001
            continue
        rec = getattr(up, "record", None) or {}
        if "spectrum128" in (rec.get("matrices") or {}):
            try:
                arr, info = up.matrix("spectrum128")
                return np.asarray(arr, dtype=np.uint8), dict(info)
            except Exception:  # noqa: BLE001
                return None
    return None


def dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_text(p: Path) -> bytes:
    return Path(p).read_bytes()
