# ruff: noqa: E501  (long data tables / docstrings in generated-fixture code)
"""Thin adapters: raw W0 outputs in tests/.cache/real/<slug>/ -> contract-layout folders tests/contract/real-<slug>/.

These folders give module builders REAL upstream inputs (stems, beats, sections, notes, lyrics, ...) for the stages
the W0 spike covered. They are NOT ground truth: each file's provenance says which raw tool output it came from and
that no fusion/post-processing of the production stage was applied. Stages without W0 data are simply absent;
``coverage.json`` (and tests/contract/README.md) list which stages are full / partial / absent, by checking every
catalogue output.

Privacy (NF5): lyric text is written only into lyrics/*.json|lrc|vtt|srt|ass of these gitignored folders. Nothing here
prints or logs lyric text; errors are reported by type only.

Big audio: canonical.wav and fast/*.wav are hard links to the W0 cache (same volume; no copy); stems are encoded to
24-bit FLAC (contract format) once and skipped when already present.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Any

import numpy as np

from mvh.contract import catalog, curvefile, schemas
from mvh.contract.catalog import CONTRACT_VERSION
from mvh.contract.events import dumps_events, dumps_json, make_envelope

from .audio_io import ffmpeg_exe
from .midi import write_smf

__all__ = ["build_real", "build_all_real", "SLUGS"]

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "tests" / ".cache" / "real"
OUT = REPO / "tests" / "contract"
SLUGS = ("megafauna", "versatile", "jeremy", "newton-vs-nye")
ADAPTER_VERSION = "1.0.0"
HARMONIX = ["start", "end", "intro", "outro", "break", "bridge", "inst", "solo", "verse", "chorus"]
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DEGREE = {
    "1": 0,
    "b2": 1,
    "2": 2,
    "b3": 3,
    "3": 4,
    "4": 5,
    "#4": 6,
    "b5": 6,
    "5": 7,
    "#5": 8,
    "b6": 8,
    "6": 9,
    "b7": 10,
    "7": 11,
    "9": 2,
    "b9": 1,
}
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _j(p: Path) -> Any:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _key(slug: str, stage: str) -> str:
    return hashlib.sha256(f"mvh-real-adapter/{slug}/{stage}/{ADAPTER_VERSION}".encode()).hexdigest()


def _prov(slug: str, stage: str, source: str, notes: list[str] | None = None) -> dict:
    return {
        "stage": stage,
        "stage_version": ADAPTER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "key": _key(slug, stage),
        "params": {"adapter": "tests.synth.real", "w0_source": source},
        "models": [],
        "tools": [{"name": "tests.synth.real", "version": ADAPTER_VERSION}],
        "device": "cpu",
        "upstream": {},
        "overrides_applied": [],
        "fallbacks": [],
        "notes": [
            "REAL-SONG ADAPTER: raw W0 tool output converted to the contract layout; not ground truth and not the "
            "production stage (no fusion, no QA)",
            *(notes or []),
        ],
    }


def _pc(name: str) -> int:
    n = name.strip()
    pc = PC[n[0].upper()]
    for ch in n[1:]:
        pc += 1 if ch == "#" else -1 if ch == "b" else 0
    return pc % 12


def _name(m: int) -> str:
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


class Folder:
    def __init__(self, slug: str):
        self.slug = slug
        self.src = CACHE / slug
        self.root = OUT / f"real-{slug}"
        self.errors: list[str] = []
        self.invalid: list[str] = []
        self.channels: dict[str, np.ndarray] = {}
        self.cmeta: dict[str, dict] = {}
        self.matrix: tuple[np.ndarray, dict] | None = None
        self.n = 0

    def p(self, rel: str) -> Path:
        q = self.root / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        return q

    def write_json(self, rel: str, obj: Any, schema: str | None) -> None:
        if schema:
            errs = schemas.validate(obj, schema)
            self.invalid += [f"{rel}: {e[:160]}" for e in errs[:3]]
        self.p(rel).write_text(dumps_json(obj), encoding="utf-8", newline="\n")

    def events(
        self,
        name: str,
        items: list[dict],
        stage: str,
        source: str,
        notes=None,
        rel: str | None = None,
        fields=None,
    ) -> None:
        env = make_envelope(name, items, _prov(self.slug, stage, source, notes), fields=fields)
        errs = schemas.validate(env, env["schema"])
        self.invalid += [f"{name}: {e[:160]}" for e in errs[:3]]
        path = rel or catalog.event_def(name).file.replace("{src}", name.split(".", 1)[-1])
        self.p(path).write_text(dumps_events(env), encoding="utf-8", newline="\n")

    def link(self, rel: str, src: Path) -> None:
        dst = self.p(rel)
        if dst.exists():
            if dst.stat().st_size == src.stat().st_size:
                return
            dst.unlink()
        try:
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst)

    def flac(self, rel: str, src: Path) -> None:
        dst = self.p(rel)
        if dst.exists() and dst.stat().st_size > 0:
            return
        tmp = dst.with_name(dst.stem + ".tmp.flac")
        cmd = [
            ffmpeg_exe(),
            "-y",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(src),
            "-map",
            "0:a:0",
            "-c:a",
            "flac",
            "-sample_fmt",
            "s32",
            "-bits_per_raw_sample",
            "24",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            "-map_metadata",
            "-1",
            str(tmp),
        ]
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg flac failed for {src.name}")
        os.replace(tmp, dst)

    def curve(self, cid: str, v: np.ndarray, meta: dict | None = None) -> None:
        v = np.asarray(v, dtype=np.float64)
        if v.size < self.n:
            v = np.concatenate([v, np.full(self.n - v.size, v[-1] if v.size else 0.0)])
        self.channels[cid] = v[: self.n]
        if meta:
            self.cmeta[cid] = meta


def _pnorm(v: np.ndarray) -> tuple[np.ndarray, dict]:
    lo, hi = float(np.percentile(v, 2)), float(np.percentile(v, 99.5))
    return (np.clip((v - lo) / (hi - lo), 0, 1) if hi > lo else np.zeros_like(v)), {"lo": lo, "hi": hi}


def _f32_memmap(path: Path) -> np.ndarray:
    """[n, ch] float32 view of a float WAV's data chunk (read-only memmap)."""
    with path.open("rb") as b:
        b.read(12)
        ch = 2
        while True:
            h = b.read(8)
            cid, size = h[:4], int.from_bytes(h[4:], "little")
            if cid == b"fmt ":
                body = b.read(size + (size % 2))
                ch = int.from_bytes(body[2:4], "little")
            elif cid == b"data":
                off = b.tell()
                break
            else:
                b.seek(size + (size % 2), 1)
    return np.memmap(path, dtype="<f4", mode="r", offset=off, shape=(size // 4 // ch, ch))


def _wav_peak_and_sha(path: Path) -> tuple[float, str, int, int, int]:
    """(peak, sha256 of the interleaved float32 PCM, sr, channels, n) of a float32 WAV (memory-mapped)."""
    b = path.open("rb")
    head = b.read(12)
    assert head[:4] == b"RIFF"
    sr = ch = None
    while True:
        h = b.read(8)
        if len(h) < 8:
            raise ValueError("no data chunk")
        cid, size = h[:4], int.from_bytes(h[4:], "little")
        if cid == b"fmt ":
            body = b.read(size)
            ch, sr = int.from_bytes(body[2:4], "little"), int.from_bytes(body[4:8], "little")
            if size % 2:
                b.read(1)
        elif cid == b"data":
            off = b.tell()
            break
        else:
            b.seek(size + (size % 2), 1)
    b.close()
    mm = np.memmap(path, dtype="<f4", mode="r", offset=off, shape=(size // 4,))
    peak = float(np.max(np.abs(mm)))
    sha = hashlib.sha256(mm.tobytes()).hexdigest()
    n = size // 4 // ch
    del mm
    return peak, sha, sr, ch, n


# ================================================================================================ stages
def _ingest(f: Folder) -> dict:
    d = _j(f.src / "decode/decode.json")
    mix = f.src / "decode/mix.wav"
    peak, sha, sr, ch, n = _wav_peak_and_sha(mix)
    f.n = int(np.ceil(n * 100 / sr))
    f.link("_intermediate/ingest/canonical.wav", mix)
    f.flac("audio/mix.flac", mix)
    if peak > 1.0:
        f.link("audio/mix.wav", mix)
    op = f.p("audio/preview.opus")
    if not op.exists():
        r = subprocess.run(
            [
                ffmpeg_exe(),
                "-y",
                "-v",
                "error",
                "-nostdin",
                "-i",
                str(mix),
                "-c:a",
                "libopus",
                "-b:a",
                "96k",
                "-ar",
                "48000",
                "-fflags",
                "+bitexact",
                "-flags:a",
                "+bitexact",
                "-map_metadata",
                "-1",
                str(op),
            ],
            capture_output=True,
        )
        if r.returncode != 0:
            raise RuntimeError("opus encode failed")
    streams = d["ffprobe"]["streams"]
    tags = {
        k.lower(): str(v)
        for k, v in d["ffprobe"]["format"].get("tags", {}).items()
        if k.lower() not in ("lyrics", "unsyncedlyrics")
    }
    src = {
        "file_name": d["source_file"],
        "codec": streams[0]["codec_name"],
        "sample_rate": sr,
        "channels": ch,
        "n_samples": n,
        "duration_s": round(n / sr, 6),
        "pcm_sha256": sha,
        "lossless": streams[0]["codec_name"] in ("flac", "pcm_s16le", "alac", "wavpack"),
        "peak_abs": round(peak, 6),
        "decode_warnings": int(d.get("decoder_warning_count", 0)),
        "tags": tags,
        "has_cover": any(s.get("codec_type") == "video" for s in streams),
        "palette": [],
        "soundtrack": "audio/mix.wav" if peak > 1.0 else "audio/mix.flac",
    }
    f.write_json("meta/source.json", src, "mvh/files/source")
    f.duration = n / sr
    f.sr = sr
    return src


def _identity(f: Folder, src: dict) -> None:
    t = src["tags"]
    f.write_json(
        "meta/identity.json",
        {
            "title": t.get("title"),
            "artist": t.get("artist"),
            "album": t.get("album"),
            "duration_s": src["duration_s"],
            "source": "tags",
            "conf": 0.9,
            "credits": [],
        },
        "mvh/files/identity",
    )


def _separation(f: Folder) -> None:
    for k in ("vocals", "drums", "bass", "other"):
        f.link(f"_intermediate/separate_fast/fast/{k}.wav", f.src / f"demucs/htdemucs/{k}.wav")
    f.write_json(
        "_intermediate/separate_fast/fast/separation.json",
        {
            "variant": "fast",
            "degraded": False,
            "lead_backing_split": False,
            "stems": {
                k: {"model": "demucs_onnx_htdemucs", "file": f"fast/{k}.wav"}
                for k in ("vocals", "drums", "bass", "other")
            },
            "models": [
                {
                    "id": "demucs_onnx_htdemucs",
                    "licence": "MIT (package); weight licence unclear (Demucs weights)",
                }
            ],
        },
        "mvh/files/separation",
    )
    sep = f.src / "sep"
    idx = _j(sep / "index.json")
    stems = {}
    for s in (
        "vocals",
        "lead_vocals",
        "backing_vocals",
        "drums",
        "bass",
        "guitar",
        "piano",
        "other",
        "instrumental",
    ):
        if (sep / f"{s}.wav").exists():
            f.flac(f"stems/{s}.flac", sep / f"{s}.wav")
            stems[s] = {"model": "sep", "file": f"stems/{s}.flac"}
    for sub in ("kick", "snare", "toms", "hihat", "ride", "crash"):
        if (sep / f"drums/{sub}.wav").exists():
            f.flac(f"stems/drums/{sub}.flac", sep / f"drums/{sub}.wav")
            stems[f"drums_{sub}"] = {"model": "sep.mdx23c-drumsep", "file": f"stems/drums/{sub}.flac"}
    models = []
    for m in idx.get("models", []) if isinstance(idx.get("models"), list) else []:
        if isinstance(m, dict) and "id" in m:
            models.append({"id": str(m["id"]), "licence": str(m.get("licence", "see models.lock.json"))})
    if not models:
        models = [
            {"id": k, "licence": "see models.lock.json"}
            for k in (
                "sep.bs-roformer-sw-6stem",
                "sep.mel-roformer-vocals-kimberley",
                "sep.mel-roformer-karaoke-aufr33-viperx",
                "sep.mdx23c-drumsep",
            )
        ]
    f.write_json(
        "meta/separation.json",
        {
            "variant": idx.get("variant", "rocm"),
            "degraded": False,
            "lead_backing_split": True,
            "stems": stems,
            "models": models,
        },
        "mvh/files/separation",
    )


def _allin1(f: Folder) -> dict:
    a = _j(f.src / "allin1/allin1.json")
    act = np.load(f.src / "allin1/activations.npz")
    T = act["beat"].shape[0]
    mat = np.column_stack([act["beat"], act["downbeat"], act["segment"], act["label"].T]).astype("<f4")
    f.p("_intermediate/allin1/activations.f32").write_bytes(np.ascontiguousarray(mat).tobytes())
    emb = np.load(f.src / "allin1/embeddings.npy", mmap_mode="r")
    e2 = np.asarray(emb, dtype=np.float32).mean(axis=0).reshape(emb.shape[1], -1)
    f.p("_intermediate/allin1/embeddings.f32").write_bytes(np.ascontiguousarray(e2.astype("<f4")).tobytes())
    doc = {
        "bpm": float(a["bpm"]) if a.get("bpm") is not None else None,
        "beats": a["beats"],
        "downbeats": a["downbeats"],
        "beat_positions": a["beat_positions"],
        "segments": a["segments"],
        "labels": HARMONIX,
        "activations": {
            "file": "activations.f32",
            "rate_hz": 100,
            "columns": ["beat", "downbeat", "boundary", *HARMONIX],
            "frames": T,
        },
        "embeddings": {
            "file": "embeddings.f32",
            "rate_hz": 100,
            "dim": int(e2.shape[1]),
            "frames": int(e2.shape[0]),
        },
    }
    f.write_json("_intermediate/allin1/allin1.json", doc, "mvh/intermediate/allin1")
    return a


def _rhythm(f: Folder, a1: dict) -> list[dict]:
    bt = _j(f.src / "beat_this/beat_this.json")
    lb = np.load(f.src / "beat_this/logits_beat.npy")
    ld = np.load(f.src / "beat_this/logits_downbeat.npy")
    pb, pd = 1 / (1 + np.exp(-lb)), 1 / (1 + np.exp(-ld))
    times, nums = bt["beats"], bt["beat_numbers"]
    bar = 0 if nums and nums[0] != 1 else 1
    beats, bars = [], []
    for i, (t, k) in enumerate(zip(times, nums)):
        if k == 1 and i > 0:
            bar += 1
        beats.append(
            {
                "beat_index": i,
                "t": t,
                "bar": bar,
                "beat_in_bar": int(k),
                "in_pulse": True,
                "strength": round(float(pb[min(len(pb) - 1, int(round(t * 50)))]), 4),
                "conf": 0.8,
            }
        )
    by_bar: dict[int, list[dict]] = {}
    for b in beats:
        by_bar.setdefault(b["bar"], []).append(b)
    for k in sorted(by_bar):
        bs = by_bar[k]
        nominal = max(b["beat_in_bar"] for b in bs)
        if k == 0 and (k + 1) in by_bar:
            nominal = max(nominal, max(b["beat_in_bar"] for b in by_bar[1]))
        for b in bs:
            b["beats_in_bar"] = max(nominal, b["beat_in_bar"])
        end = (
            by_bar[k + 1][0]["t"]
            if (k + 1) in by_bar
            else bs[-1]["t"] + (bs[-1]["t"] - bs[-2]["t"] if len(bs) > 1 else 0.5)
        )
        bars.append(
            {
                "bar": k,
                "t": bs[0]["t"],
                "d": round(end - bs[0]["t"], 6),
                "beats_in_bar": bs[0]["beats_in_bar"],
                "n_beats": len(bs),
                "first_beat": bs[0]["beat_index"],
                "pickup": k == 0,
                "in_pulse": True,
                "conf": 0.8,
            }
        )
    src_note = "beat_this final0 minimal postprocessor (beats, beat_numbers); no tempo arbitration or 2-of-3 downbeat vote"
    f.events("beats", beats, "rhythm", "beat_this", [src_note])
    f.events("bars", bars, "rhythm", "beat_this", [src_note])
    med = float(bt.get("median_bpm") or 60.0 / np.median(np.diff(times)))
    f.events(
        "tempo_segments",
        [{"t": 0.0, "d": round(f.duration, 6), "bpm": round(med, 3), "stable": True}],
        "rhythm",
        "beat_this",
    )
    regions = []
    if times[0] > 0:
        regions.append({"t": 0.0, "d": round(times[0], 6), "in_pulse": False})
    regions.append({"t": times[0], "d": round(times[-1] - times[0], 6), "in_pulse": True})
    if f.duration - times[-1] > 1e-3:
        regions.append({"t": times[-1], "d": round(f.duration - times[-1], 6), "in_pulse": False})
    f.events(
        "pulse_regions",
        regions,
        "rhythm",
        "beat_this",
        ["pulse = [first beat, last beat] (no pulse detection in W0)"],
    )
    lib = _j(f.src / "librosa/librosa.json")

    def fmeas(a, b, tol=0.07):
        a, b = np.asarray(a), np.asarray(b)
        if not len(a) or not len(b):
            return None
        hit = sum(1 for x in a if np.min(np.abs(b - x)) <= tol)
        p, r = hit / len(a), hit / len(b)
        return round(2 * p * r / (p + r), 4) if p + r else 0.0

    meter = max(
        set(b["beats_in_bar"] for b in bars), key=lambda m: sum(1 for b in bars if b["beats_in_bar"] == m)
    )
    est = {"beat_this": round(med, 3), "allin1": float(a1["bpm"]) if a1.get("bpm") else None}
    if isinstance(lib.get("beat_track_tempo"), (int, float)):
        est["librosa"] = round(float(lib["beat_track_tempo"]), 3)
    f.write_json(
        "meta/tempo.json",
        {
            "bpm": round(med, 3),
            "confidence": 0.5,
            "feel": "normal",
            "is_variable": False,
            "candidates": [
                {"bpm": round(med * r, 3), "score": s, "relation": rel}
                for r, s, rel in (
                    (1, 1.0, "x1"),
                    (2, 0.3, "x2"),
                    (0.5, 0.3, "x0.5"),
                    (1.5, 0.1, "x1.5"),
                    (2 / 3, 0.1, "x0.667"),
                )
            ],
            "meter": {
                "time_signature": f"{meter}/4",
                "beats_per_bar": int(meter),
                "confidence": 0.5,
                "changes": [],
            },
            "qa": {
                "beat_agreement_f": fmeas(times, a1["beats"]),
                "downbeat_agreement_f": fmeas(bt["downbeats"], a1["downbeats"]),
                "flags": ["real_adapter_no_fusion"],
            },
            "estimates": est,
        },
        "mvh/files/tempo",
    )
    t100 = np.arange(f.n) / 100.0
    ibi = np.diff(times)
    mids = (np.asarray(times[:-1]) + np.asarray(times[1:])) / 2
    f.curve("tempo.bpm", np.clip(np.interp(t100, mids, 60.0 / ibi), 30, 300))
    f.curve("rhythm.beat_act", np.interp(t100, np.arange(len(pb)) / 50.0, pb))
    f.curve("rhythm.downbeat_act", np.interp(t100, np.arange(len(pd)) / 50.0, pd))
    f.curve("rhythm.in_pulse", ((t100 >= times[0]) & (t100 < times[-1])).astype(np.float64))
    return beats


_SPEC_MAP = {
    "viz_bass": "bands.bass_viz",
    "viz_mid": "bands.mid_viz",
    "viz_high": "bands.high_viz",
    "db_sub": "fine.sub_db",
    "db_bass": "fine.bass_db",
    "db_lowmid": "fine.lowmid_db",
    "db_mid": "fine.mid_db",
    "db_highmid": "fine.highmid_db",
    "db_presence": "fine.presence_db",
    "db_air": "fine.air_db",
    "db_viz_bass": "bands.bass_db",
    "db_viz_mid": "bands.mid_db",
    "db_viz_high": "bands.high_db",
    "db_kick": "bands.kick_db",
    "kick": "hits.kick",
    "kick_raw": "hits.kick_raw",
    "mid_hit": "hits.mid",
    "high_hit": "hits.high",
    "flux_low": "flux.bass",
    "flux_mid": "flux.mid",
    "flux_high": "flux.high",
    "rms_db": "loud.rms_db",
    "lufs_m": "loud.momentary_lufs",
    "lufs_s": "loud.short_term_lufs",
    "centroid_hz": "timbre.centroid_hz",
    "rolloff_hz": "timbre.rolloff_hz",
    "flatness": "timbre.flatness",
    "width": "stereo.width",
    "corr": "stereo.correlation",
}


def _spectral_loudness(f: Folder) -> None:
    sp = f.src / "spectral_proto"
    cols = _j(sp / "curve_columns.json")
    mat = np.load(sp / "curves.npz")[
        "curves"
    ]  # [T, len(cols)] row-major, columns in curve_columns.json order
    T = mat.shape[0]
    for j, c in enumerate(cols):
        cid = _SPEC_MAP.get(c)
        if cid is None:
            continue
        v = mat[:, j].astype(np.float64)
        if cid.endswith("_db"):
            v = np.maximum(v, -120.0)
        if cid.endswith("_lufs"):
            v = np.maximum(v, -70.0)
        if cid.startswith("flux."):
            v, m = _pnorm(v)
            f.curve(cid, v, m)
            continue
        f.curve(cid, v)
    for twin in (
        "bands.bass",
        "bands.mid",
        "bands.high",
        "bands.kick",
        "fine.sub",
        "fine.bass",
        "fine.lowmid",
        "fine.mid",
        "fine.highmid",
        "fine.presence",
        "fine.air",
        "loud.rms",
    ):
        if f"{twin}_db" in f.channels:
            v, m = _pnorm(f.channels[f"{twin}_db"])
            f.curve(twin, v, m)
    for twin, phys in (
        ("loud.momentary", "loud.momentary_lufs"),
        ("loud.short_term", "loud.short_term_lufs"),
        ("timbre.centroid", "timbre.centroid_hz"),
        ("timbre.rolloff", "timbre.rolloff_hz"),
    ):
        if phys in f.channels:
            v, m = _pnorm(f.channels[phys])
            f.curve(twin, v, m)
    if all(f"bands.{b}_viz" in f.channels for b in ("bass", "mid", "high")):
        f.curve(
            "bands.level",
            (f.channels["bands.bass_viz"] + f.channels["bands.mid_viz"] + f.channels["bands.high_viz"]) / 3.0,
        )
    u8 = np.fromfile(sp / "spectrum128.u8", dtype=np.uint8)
    if u8.size == T * 128:
        f.matrix = (
            u8.reshape(T, 128)[: f.n]
            if T >= f.n
            else np.vstack([u8.reshape(T, 128), np.zeros((f.n - T, 128), np.uint8)]),
            {"band_edges_hz": [float(x) for x in np.geomspace(32.0, 16000.0, 129)]},
        )
    # loudness scalars from ffmpeg ebur128 (true peak)
    r = subprocess.run(
        [
            ffmpeg_exe(),
            "-nostdin",
            "-hide_banner",
            "-i",
            str(f.src / "decode/mix.wav"),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = r.stderr[r.stderr.rfind("Summary:") :]

    def grab(label):
        m = re.search(label + r":\s+(-?[\d.]+)", tail)
        return float(m.group(1)) if m else None

    integ, lra, lo, hi, tp = grab("I"), grab("LRA"), grab("LRA low"), grab("LRA high"), grab("Peak")
    peak = _j(f.root / "meta/source.json")["peak_abs"]
    # loud.peak_db / loud.crest_db (46 ms centred windows) from the decode, like the fixture's reference measurement
    from scipy.ndimage import maximum_filter1d

    mm = _f32_memmap(f.src / "decode/mix.wav")
    a8 = np.abs(mm).max(axis=1)
    nb = a8.size // 8
    blk = a8[: nb * 8].reshape(nb, 8).max(axis=1)
    win = maximum_filter1d(blk, size=256, mode="constant")
    centres = np.minimum((np.arange(f.n) * f.sr / 100 / 8).astype(int), nb - 1)
    with np.errstate(divide="ignore"):
        pk = np.maximum(np.nan_to_num(20 * np.log10(win[centres].astype(np.float64)), neginf=-120.0), -120.0)
    f.curve("loud.peak_db", pk)
    if "loud.rms_db" in f.channels:
        rms = f.channels["loud.rms_db"]
        f.curve("loud.crest_db", np.where(rms > -120.0, np.clip(pk - rms, 0, 60), 0.0))
    del mm
    sp_db = 20 * np.log10(max(peak, 1e-9))
    f.write_json(
        "meta/loudness.json",
        {
            "integrated_lufs": integ,
            "lra_lu": lra,
            "lra_low_lufs": lo,
            "lra_high_lufs": hi,
            "true_peak_dbtp": tp,
            "sample_peak_db": round(sp_db, 3),
            "plr_db": round(tp - integ, 3) if tp is not None and integ is not None else None,
            "ebur128": {"integrated_lufs": integ, "lra_lu": lra, "true_peak_dbtp": tp},
        },
        "mvh/files/loudness",
    )


def _harmony(f: Folder, beats: list[dict]) -> None:
    k = _j(f.src / "key/key.json")
    top = k["skey_global_top3"][0]
    ks = k["profile_global_ks_top3"][0]

    def parse(lbl):
        tonic, mode = lbl.split()
        return _pc(tonic), mode.lower()

    tpc, mode = parse(top[0])
    kpc, kmode = parse(ks[0])
    agree = (tpc, mode) == (kpc, kmode)
    rel = (
        "agree"
        if agree
        else "relative"
        if (mode != kmode and (tpc - kpc) % 12 in (3, 9))
        else "parallel"
        if tpc == kpc
        else "disagree"
    )
    key_name = f"{NOTE_NAMES[tpc]} {mode}"
    f.write_json(
        "meta/key.json",
        {
            "global": {"key": key_name, "tonic_pc": tpc, "mode": mode, "conf": 0.5},
            "agreement": rel,
            "flags": [] if agree else ["skey_vs_ks_disagree"],
            "methods": {"skey": {"key": top[0]}, "ks": {"key": ks[0]}},
        },
        "mvh/files/key",
    )
    f.events(
        "key",
        [
            {
                "t": 0.0,
                "d": round(f.duration, 6),
                "key": key_name,
                "tonic_pc": tpc,
                "mode": mode,
                "conf": 0.5,
                "agree": agree,
            }
        ],
        "harmony",
        "key",
        ["global S-KEY top-1; KS profile used only for the agree flag"],
    )
    ch = _j(f.src / "chords/chords.json")
    bt = np.array([b["t"] for b in beats])
    items = []
    for s in ch["segments"]:
        lab = s["chord"]
        if lab in ("N", "X"):
            root = bass = None
            qual = "N"
        else:
            base, _, bs = lab.partition("/")
            r, _, q = base.partition(":")
            root = _pc(r)
            qual = q or "maj"
            bass = (root + DEGREE.get(bs, 0)) % 12 if bs else root
        d = round(s["end_time"] - s["start_time"], 6)
        if d <= 0:
            continue
        j = int(np.argmin(np.abs(bt - s["start_time"]))) if bt.size else None
        items.append(
            {
                "t": s["start_time"],
                "d": d,
                "label": lab,
                "root_pc": root,
                "quality": qual,
                "bass_pc": bass,
                "conf": 0.5,
                "beat_index": j if j is not None and abs(bt[j] - s["start_time"]) <= 0.07 else None,
            }
        )
    f.events("chords", items, "harmony", "chords", ["lv-chordia raw segments; not snapped to beats"])


def _structure(f: Folder, a1: dict, beats: list[dict]) -> list[dict]:
    bars = _j(f.root / "events/bars.json")["items"]
    bt = np.array([b["t"] for b in bars])
    secs = []
    for s in a1["segments"]:
        if s["label"] in ("start", "end") or s["end"] - s["start"] < 1.0:
            continue
        i0 = int(np.argmin(np.abs(bt - s["start"])))
        i1 = int(np.argmin(np.abs(bt - s["end"])))
        if i1 <= i0:
            continue
        if secs and secs[-1]["_i1"] > i0:
            i0 = secs[-1]["_i1"]
            if i1 <= i0:
                continue
        secs.append({"_i0": i0, "_i1": i1, "label": s["label"]})
    groups: dict[str, str] = {}
    occ: dict[str, int] = {}
    out = []
    for n, s in enumerate(secs, start=1):
        lab = s["label"]
        occ[lab] = occ.get(lab, 0) + 1
        if lab not in groups:
            groups[lab] = chr(65 + len(groups))
        b0, b1 = bars[s["_i0"]], bars[s["_i1"] - 1]
        out.append(
            {
                "id": f"S{n:02d}",
                "t": b0["t"],
                "d": round(b1["t"] + b1["d"] - b0["t"], 6),
                "label": lab,
                "occurrence": occ[lab],
                "occurrence_label": f"{lab}#{occ[lab]}",
                "repeat_group": groups[lab],
                "start_bar": b0["bar"],
                "n_bars": s["_i1"] - s["_i0"],
                "label_probs": {lab: 1.0},
                "conf": 0.5,
                "boundary_conf": 0.5,
            }
        )
    f.events(
        "sections",
        out,
        "structure",
        "allin1",
        ["allin1 harmonix segments snapped to beat_this downbeats; repeat group = label"],
    )
    phrases = []
    for s in out:
        b = s["start_bar"]
        end = s["start_bar"] + s["n_bars"]
        while b < end:
            nb = min(4, end - b)
            t0 = next(x for x in bars if x["bar"] == b)
            t1 = next(x for x in bars if x["bar"] == b + nb - 1)
            phrases.append(
                {
                    "id": "",
                    "t": t0["t"],
                    "d": round(t1["t"] + t1["d"] - t0["t"], 6),
                    "start_bar": b,
                    "n_bars": nb,
                    "section_id": s["id"],
                }
            )
            b += nb
    for i, p in enumerate(phrases, start=1):
        p["id"] = f"P{i:02d}"
    f.events("phrases", phrases, "structure", "allin1", ["naive 4-bar phrases from each section start"])
    f.events("edm_roles", [], "structure", "none", ["no EDM-role detection in W0"])
    rg: dict[str, dict] = {}
    for s in out:
        g = rg.setdefault(s["repeat_group"], {"label": s["label"], "section_ids": [], "similarity": 0.5})
        g["section_ids"].append(s["id"])
    f.write_json(
        "meta/structure.json",
        {"repeat_groups": rg, "phrase_bars": 4, "n_sections": len(out)},
        "mvh/files/structure",
    )
    return out


def _notes(f: Folder, bpm: float) -> None:
    files = {
        "bass": "notes/htdemucs_bass.json",
        "other": "notes/htdemucs_other.json",
        "guitar": "notes/htdemucs_6s_guitar.json",
    }
    idx = {}
    tracks = []
    for src in ("bass", "piano", "guitar", "other"):
        items = []
        p = f.src / files.get(src, "__none__")
        if p.exists():
            raw = _j(p)
            fields = raw["notes_fields"]
            amp = [n[fields.index("amplitude")] for n in raw["notes"]] or [1.0]
            amax = max(amp) or 1.0
            for n in raw["notes"]:
                t0, t1, m, a = (n[fields.index(k)] for k in ("start_s", "end_s", "midi", "amplitude"))
                if t1 - t0 <= 0:
                    continue
                items.append(
                    {
                        "t": round(t0, 6),
                        "d": round(t1 - t0, 6),
                        "midi": int(m),
                        "name": _name(int(m)),
                        "vel": round(min(1.0, a / amax), 4),
                        "conf": round(min(1.0, a / amax), 4),
                    }
                )
        f.events(
            f"notes.{src}",
            items,
            "notes",
            f"basic-pitch on {p.parent.name}/{p.name}" if p.exists() else "none",
            [
                "basic-pitch raw notes on htdemucs stems (not masked by stem activity)"
                if items
                else "no W0 notes for this source"
            ],
            rel=f"events/notes.{src}.json",
        )
        ms = [x["midi"] for x in items]
        hist = [0.0] * 12
        for m in ms:
            hist[m % 12] += 1
        tot = sum(hist) or 1.0
        idx[src] = {
            "events": f"events/notes.{src}.json",
            "midi": None,
            "count": len(ms),
            "lowest": min(ms) if ms else None,
            "highest": max(ms) if ms else None,
            "pc_histogram": [round(h / tot, 4) for h in hist],
            "density_per_s": round(len(ms) / f.duration, 4),
        }
        tracks.append((src, [(x["t"], x["d"], x["midi"], x["vel"]) for x in items]))
    f.p("notes/notes.mid").write_bytes(write_smf(tracks, [(0.0, bpm)]))
    f.write_json(
        "notes/notes.json",
        {"sources": idx, "tempo_map": f"constant {bpm:.3f} BPM (beat_this median; adapter)"},
        "mvh/files/notes_index",
    )


def _vocals(f: Folder) -> None:
    p = np.load(f.src / "pitch/rmvpe.npz")
    hz, conf = p["hz"].astype(np.float64), p["conf"].astype(np.float64)
    voiced = (hz > 0) & (conf >= 0.3)
    midi = np.where(voiced, 69 + 12 * np.log2(np.where(voiced, hz, 440.0) / 440.0), np.nan)
    f.curve("vocal.f0_hz", np.where(voiced, hz, np.nan))
    f.curve("vocal.midi", midi)
    f.curve("vocal.voiced", voiced.astype(np.float64))
    f.curve("vocal.conf", np.clip(conf, 0, 1))
    vm = midi[np.isfinite(midi)]
    if vm.size:
        p2, p98 = float(np.percentile(vm, 2)), float(np.percentile(vm, 98))
        pitch = np.zeros(midi.size)
        last = (vm[0] - p2) / (p98 - p2) if p98 > p2 else 0.0
        for i, v in enumerate(midi):
            if np.isfinite(v):
                last = (v - p2) / (p98 - p2) if p98 > p2 else 0.0
            pitch[i] = last
        f.curve("vocal.pitch01", np.clip(pitch, 0, 1), {"lo": p2, "hi": p98})
    else:
        f.curve("vocal.pitch01", np.zeros(f.n))
    present = vm.size / 100.0 >= 8.0
    # vocal notes: voiced runs split where the pitch moves > 0.7 semitone from the running median; >= 80 ms
    notes, cur = [], []
    for i in range(midi.size + 1):
        v = midi[i] if i < midi.size else np.nan
        if np.isfinite(v) and (not cur or abs(v - np.median([midi[j] for j in cur[-10:]])) <= 0.7):
            cur.append(i)
            continue
        if len(cur) >= 8:
            m = float(np.median(midi[cur]))
            notes.append(
                {
                    "t": round(cur[0] / 100.0, 6),
                    "d": round(len(cur) / 100.0, 6),
                    "midi": int(round(m)),
                    "name": _name(int(round(m))),
                    "vel": 0.8,
                    "conf": round(float(np.mean(conf[cur])), 4),
                }
            )
        cur = [i] if (i < midi.size and np.isfinite(v)) else []
    f.events(
        "notes.vocals",
        notes,
        "vocals",
        "rmvpe",
        ["RMVPE f0 (conf >= 0.3) segmented into notes by the adapter"],
        rel="events/notes.vocals.json",
    )
    f.p("notes/vocals.mid").write_bytes(
        write_smf([("vocals", [(x["t"], x["d"], x["midi"], x["vel"]) for x in notes])], [(0.0, 120.0)])
    )
    lv = _f32_memmap(f.src / "sep/lead_vocals.wav") if (f.src / "sep/lead_vocals.wav").exists() else None
    phr = []
    vv = np.isfinite(midi)
    i = 0
    while i < vv.size:
        if vv[i]:
            j = i
            while j < vv.size and (vv[j] or (j + 30 < vv.size and vv[j : j + 30].any())):
                j += 1
            if j - i >= 50:
                seg = midi[i:j][np.isfinite(midi[i:j])]
                db = -120.0
                if lv is not None:
                    x = np.asarray(lv[int(i * f.sr / 100) : int(j * f.sr / 100)], dtype=np.float64)
                    db = float(10 * np.log10(np.mean(x * x) + 1e-12))
                phr.append(
                    {
                        "id": f"VP{len(phr) + 1:03d}",
                        "t": round(i / 100.0, 6),
                        "d": round((j - i) / 100.0, 6),
                        "median_midi": round(float(np.median(seg)), 3),
                        "min_midi": round(float(seg.min()), 3),
                        "max_midi": round(float(seg.max()), 3),
                        "mean_db": round(max(db, -120.0), 2),
                    }
                )
            i = j
        else:
            i += 1
    f.events("vocal_phrases", phr, "vocals", "rmvpe", ["voiced runs (gaps < 0.3 s bridged), >= 0.5 s"])

    def stat(fn):
        i = int(fn(midi))
        m = int(round(midi[i]))
        return {"midi": m, "name": _name(m), "hz": round(float(hz[i]), 2), "t": round(i / 100.0, 6)}

    f.write_json(
        "meta/vocal_range.json",
        {
            "present": bool(present),
            "voiced_s": round(vm.size / 100.0, 2),
            "lowest": stat(np.nanargmin) if present else None,
            "highest": stat(np.nanargmax) if present else None,
            **{
                k: (round(float(np.percentile(vm, q)), 3) if present else None)
                for k, q in (("p2", 2), ("p98", 98), ("p10", 10), ("p90", 90))
            },
            "median_midi": round(float(np.median(vm)), 3) if present else None,
            "span_semitones": round(float(np.percentile(vm, 98) - np.percentile(vm, 2)), 3)
            if present
            else None,
            "register": None,
            "conf": 0.3,
        },
        "mvh/files/vocal_range",
    )


def _lrclib_record(f: Folder) -> dict | None:
    wid = _j(CACHE / "index.words.json").get("lrclib_chosen", {}).get(f.slug)
    if wid is None:
        return None
    m = re.match(r"\d+", str(wid))
    want = int(m.group(0)) if m else None
    cands = []
    for p in sorted((f.src / "http").glob("*.json")) + [f.src / "lyrics_src/chosen_lrclib.json"]:
        if not p.exists():
            continue
        d = _j(p)
        for x in d if isinstance(d, list) else [d]:
            if isinstance(x, dict) and x.get("id") == want and x.get("syncedLyrics"):
                cands.append(x)
    return cands[0] if cands else None


def _lyrics(f: Folder, sections: list[dict]) -> list[dict] | None:
    wp = f.src / f"align_mms/{f.slug}_lead_vocals_mms_words.json"
    rec = _lrclib_record(f)
    if not wp.exists() or rec is None:
        return None
    words_raw = _j(wp)
    lrc = [ln for ln in rec["syncedLyrics"].splitlines() if re.match(r"^\[\d+:\d+(\.\d+)?\]", ln)]
    texts = [re.sub(r"^(\[[^\]]+\])+\s*", "", ln).strip() for ln in lrc]
    texts = [t for t in texts if t]
    by_line: dict[int, list[dict]] = {}
    for w in words_raw:
        by_line.setdefault(int(w["line"]), []).append(w)
    use_lrc = len(texts) == (max(by_line) + 1 if by_line else 0)
    lines, words = [], []
    norm_groups: dict[str, str] = {}
    counts: dict[str, int] = {}
    for li in sorted(by_line):
        ws = sorted(by_line[li], key=lambda w: w["start"])
        lid = f"L{li + 1:03d}"
        text = texts[li] if use_lrc else " ".join(w["w"] for w in ws)
        key = re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
        counts[key] = counts.get(key, 0) + 1
        if key not in norm_groups:
            norm_groups[key] = f"T{len(norm_groups) + 1:02d}"
        t0, t1 = ws[0]["start"], max(w["end"] for w in ws)
        sec = next((s["id"] for s in sections if s["t"] <= t0 < s["t"] + s["d"]), None)
        sc = float(np.mean([w["score"] for w in ws]))
        lines.append(
            {
                "id": lid,
                "t": round(t0, 6),
                "d": round(max(1e-3, t1 - t0), 6),
                "text": text,
                "section_id": sec,
                "text_group": norm_groups[key],
                "repeat_group": None,
                "conf": round(min(1.0, max(0.0, sc)), 4),
                "grade": "B",
                "first_word": f"{lid}.01",
                "n_words": len(ws),
                "backing": False,
                "speaker_hint": None,
                "timing_source": "ctc",
                "_key": key,
            }
        )
        for k, w in enumerate(ws, start=1):
            words.append(
                {
                    "id": f"{lid}.{k:02d}",
                    "line_id": lid,
                    "t": round(w["start"], 6),
                    "d": round(max(1e-3, w["end"] - w["start"]), 6),
                    "text": w["w"],
                    "conf": round(min(1.0, max(0.0, float(w["score"]))), 4),
                }
            )
    lg: dict[str, str] = {}
    for ln in lines:
        if counts[ln["_key"]] > 1:
            lg.setdefault(ln["_key"], f"LG{len(lg) + 1:02d}")
            ln["repeat_group"] = lg[ln["_key"]]
        del ln["_key"]
    lines.sort(key=lambda x: x["t"])
    doc = {
        "schema": "mvh/files/lyrics",
        "schema_version": CONTRACT_VERSION,
        "provenance": _prov(
            f.slug, "lyrics", "lrclib + align_mms", ["MMS_FA words (W0) on lead_vocals; LRCLIB line text"]
        ),
        "source": {
            "kind": "lrclib",
            "lrclib_id": int(rec["id"]),
            "duration_diff_s": round(float(rec.get("duration", 0)) - f.duration, 3),
            "has_word_sync": bool(rec.get("hasWordSync", False)),
        },
        "instrumental": False,
        "language": "en",
        "grade": "B",
        "lyrics_match_score": None,
        "coverage": round(sum(1 for w in words if w["conf"] >= 0.1) / max(1, len(words)), 4),
        "lines": lines,
        "words": words,
    }
    f.write_json("lyrics/lyrics.json", doc, "mvh/files/lyrics")
    from .song.folder import _ass_ts, _lrc_ts, _vtt_ts

    wl: dict[str, list[dict]] = {}
    for w in words:
        wl.setdefault(w["line_id"], []).append(w)
    lrcs = [
        f"[{_lrc_ts(ln['t'])}] " + " ".join(f"<{_lrc_ts(w['t'])}> {w['text']}" for w in wl[ln["id"]])
        for ln in lines
    ]
    f.p("lyrics/lyrics.lrc").write_text("\n".join(lrcs) + "\n", encoding="utf-8", newline="\n")
    vtt = ["WEBVTT", ""]
    srt = []
    ass = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for i, ln in enumerate(lines, start=1):
        end = ln["t"] + ln["d"]
        vtt += [
            ln["id"],
            f"{_vtt_ts(ln['t'])} --> {_vtt_ts(end)}",
            " ".join(f"<{_vtt_ts(w['t'])}>{w['text']}" for w in wl[ln["id"]]),
            "",
        ]
        srt += [str(i), f"{_vtt_ts(ln['t'], True)} --> {_vtt_ts(end, True)}", ln["text"], ""]
        ass.append(
            f"Dialogue: 0,{_ass_ts(ln['t'])},{_ass_ts(end)},Default,,0,0,0,,"
            + "".join(f"{{\\k{int(round(w['d'] * 100))}}}{w['text']} " for w in wl[ln["id"]]).rstrip()
        )
    f.p("lyrics/lyrics.vtt").write_text("\n".join(vtt), encoding="utf-8", newline="\n")
    f.p("lyrics/lyrics.srt").write_text("\n".join(srt), encoding="utf-8", newline="\n")
    f.p("lyrics/lyrics.ass").write_text("\n".join(ass) + "\n", encoding="utf-8", newline="\n")
    return words


def _voices(f: Folder, words: list[dict] | None) -> None:
    sp = f.src / "voices/voices_lead_vocals_summary.json"
    ip = f.src / "voices/items.json"
    if not sp.exists() or not ip.exists() or not words:
        return
    s = _j(sp)
    items = _j(ip)
    k = "3" if "3" in s["ecapa"]["clusterings"] else sorted(s["ecapa"]["clusterings"])[0]
    seq = dict(tok.split(":") for tok in s["ecapa"]["clusterings"][k]["seq"].split())
    letter_to_v: dict[str, str] = {}
    by_line: dict[str, list[dict]] = {}
    for w in words:
        by_line.setdefault(w["line_id"], []).append(w)
    spans = []
    for iid in sorted(items["spans"], key=lambda x: items["spans"][x][0]):
        lab = seq.get(str(iid))
        lid = f"L{int(iid) + 1:03d}"
        if lab is None or lid not in by_line:
            continue
        if lab not in letter_to_v:
            letter_to_v[lab] = f"V{len(letter_to_v) + 1}"
        t0, t1 = items["spans"][iid]
        ws = by_line[lid]
        spans.append(
            {
                "t": round(t0, 6),
                "d": round(max(1e-3, t1 - t0), 6),
                "line_id": lid,
                "first_word": ws[0]["id"],
                "last_word": ws[-1]["id"],
                "voice_id": letter_to_v[lab],
                "conf": 0.6,
                "review": True,
            }
        )
    f.events(
        "voice_spans",
        spans,
        "voices",
        "voices (ECAPA)",
        [
            f"ECAPA agglomerative clusters at k={k}; UNLABELLED: the user's "
            "voice->character mapping is the truth"
        ],
    )
    va = []
    for v in sorted(set(letter_to_v.values())):
        segs = sorted((x["t"], x["t"] + x["d"]) for x in spans if x["voice_id"] == v)
        merged: list[list[float]] = []
        for a, b in segs:
            if merged and a - merged[-1][1] < 0.3:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        va += [{"t": round(a, 6), "d": round(b - a, 6), "voice_id": v} for a, b in merged]
    va.sort(key=lambda x: (x["t"], x["voice_id"]))
    f.events("voice_activity", va, "voices", "voices (ECAPA)")
    f.write_json(
        "meta/voices.json",
        {
            "n_voices": len(letter_to_v),
            "method": f"ecapa agglomerative k={k} (W0 spike)",
            "n_source": "estimate",
            "voices": [
                {
                    "id": v,
                    "seconds": round(sum(x["d"] for x in va if x["voice_id"] == v), 3),
                    "n_lines": len({x["line_id"] for x in spans if x["voice_id"] == v}),
                    "proposed_character_id": None,
                    "hint": None,
                }
                for v in sorted(set(letter_to_v.values()), key=lambda s_: int(s_[1:]))
            ],
        },
        "mvh/files/voices",
    )


def _mouth(f: Folder) -> bool:
    p = f.src / f"mouth_open/{f.slug}_mouth_open_sustain_100hz.npy"
    if not p.exists():
        return False
    v = np.load(p).astype(np.float64)
    f.curve("vocal.mouth_open", np.clip(v, 0, 1))
    return True


# ================================================================================================ driver
def coverage(root: Path) -> dict[str, Any]:
    """Per stage: full (every required output present), partial, or absent; plus the channels present."""
    from mvh.runner.spec import catalog_outputs

    ids = set()
    if (root / "curves/index.json").exists():
        ids = {c["id"] for c in curvefile.read_index(root)["channels"]}
    out = {}
    for stage in catalog.all_stages():
        have, miss = [], []
        for o in catalog_outputs(stage):
            if o.kind in ("curve", "matrix") and o.public:
                for c in o.channels:
                    if "{" in c:
                        continue
                    (have if c in ids else miss).append(f"curve:{c}")
                continue
            base = root if o.public else root / "_intermediate" / stage
            pat = re.sub(r"\{[a-z]+\}", "*", o.path)
            ok = any(base.glob(pat)) if "*" in pat else (base / o.path).exists()
            if o.required:
                (have if ok else miss).append(o.path)
            elif ok:
                have.append(o.path)
        out[stage] = {
            "status": "full" if have and not miss else "partial" if have else "absent",
            "present": have,
            "missing": miss,
        }
    return out


def build_real(slug: str, log=print) -> dict[str, Any]:
    f = Folder(slug)
    if not f.src.exists():
        return {"slug": slug, "status": "no W0 cache"}
    f.root.mkdir(parents=True, exist_ok=True)
    steps = []

    def step(name, fn, *a):
        try:
            r = fn(*a)
            steps.append(name)
            return r
        except Exception as e:  # noqa: BLE001 - adapters are best-effort; errors are reported without content
            f.errors.append(
                f"{name}: {type(e).__name__} at {traceback.extract_tb(e.__traceback__)[-1].lineno}"
            )
            return None

    src = step("ingest", _ingest, f)
    if src is None:
        return {"slug": slug, "errors": f.errors}
    step("identity", _identity, f, src)
    step("separation", _separation, f)
    a1 = step("allin1", _allin1, f)
    beats = step("rhythm", _rhythm, f, a1) if a1 else None
    step("spectral+loudness", _spectral_loudness, f)
    if beats:
        step("harmony", _harmony, f, beats)
    secs = step("structure", _structure, f, a1, beats) if a1 and beats else None
    bpm = _j(f.root / "meta/tempo.json")["bpm"] if (f.root / "meta/tempo.json").exists() else 120.0
    step("notes", _notes, f, bpm)
    step("vocals", _vocals, f)
    words = step("lyrics", _lyrics, f, secs or [])
    step("voices", _voices, f, words)
    step("lipsync", _mouth, f)
    entries = [
        curvefile.ChannelData(cid, v.astype(np.float32), f.cmeta.get(cid)) for cid, v in f.channels.items()
    ]
    if f.matrix is not None:
        entries.append(curvefile.ChannelData("spectrum128", f.matrix[0], f.matrix[1]))
    if entries:
        idx = curvefile.assemble(f.root, entries)
        f.invalid += [
            f"curves/index.json: {e[:160]}" for e in schemas.validate(idx, "mvh/envelope/curves_index")[:3]
        ]
    cov = coverage(f.root)
    files = {
        p.relative_to(f.root).as_posix(): p.stat().st_size
        for p in sorted(f.root.rglob("*"))
        if p.is_file() and p.name not in ("coverage.json", ".done.json")
    }
    doc = {
        "slug": slug,
        "adapter_version": ADAPTER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "steps_ok": steps,
        "errors": f.errors,
        "validation_errors": f.invalid,
        "stages": {k: v["status"] for k, v in cov.items()},
        "detail": cov,
    }
    (f.root / "coverage.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    (f.root / ".done.json").write_text(
        json.dumps(
            {"slug": slug, "adapter_version": ADAPTER_VERSION, "files": files}, ensure_ascii=False, indent=1
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    log(
        f"real-{slug}: {sum(1 for v in cov.values() if v['status'] == 'full')} full / "
        f"{sum(1 for v in cov.values() if v['status'] == 'partial')} partial stages; errors={f.errors}; invalid={len(f.invalid)}"
    )
    return doc


def build_all_real(log=print) -> int:
    rc = 0
    for slug in SLUGS:
        d = build_real(slug, log)
        if d.get("errors") or d.get("validation_errors"):
            rc = 1
    return rc
