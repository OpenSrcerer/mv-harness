"""Audio file helpers for the fixtures (deterministic; numpy + stdlib; ffmpeg only for encoders).

* ``write_wav`` writes float32 (IEEE float, format 3), int16 or int24 PCM WAV with a minimal fixed header, so the
  bytes depend only on the samples.
* ``quantize24`` puts samples on the 24-bit grid (k / 2**23): sums of such tracks stay on the grid, which is how
  the synthetic stems sum *exactly* to the mix.
* ``encode`` pipes float32 into ffmpeg with ``-fflags +bitexact -flags:a +bitexact`` (byte-identical reruns).
"""

from __future__ import annotations

import os
import struct
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

__all__ = [
    "Q24",
    "quantize24",
    "write_wav",
    "read_wav",
    "ffmpeg_exe",
    "ffprobe_exe",
    "encode",
    "decode",
    "atomic_bytes",
]

Q24 = float(1 << 23)


def quantize24(x: np.ndarray) -> np.ndarray:
    """Round to the 24-bit grid (float64 in, float64 out). Values are clipped to [-1, 1 - 2**-23]."""
    q = np.round(np.asarray(x, dtype=np.float64) * Q24)
    q = np.clip(q, -Q24, Q24 - 1)
    return q / Q24


def atomic_bytes(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def _as_2d(x: np.ndarray) -> np.ndarray:
    a = np.asarray(x)
    if a.ndim == 1:
        a = a[None, :]
    return a


def wav_bytes(x: np.ndarray, sr: int, fmt: str = "f32") -> bytes:
    """x: [ch, n] or [n]. fmt: f32 | s16 | s24."""
    a = _as_2d(x)
    ch, n = a.shape
    inter = a.T.reshape(-1)  # interleave
    if fmt == "f32":
        data = inter.astype("<f4").tobytes()
        tag, bits = 3, 32
    elif fmt == "s16":
        data = np.clip(np.round(inter * 32768.0), -32768, 32767).astype("<i2").tobytes()
        tag, bits = 1, 16
    elif fmt == "s24":
        q = np.clip(np.round(inter * Q24), -Q24, Q24 - 1).astype("<i4")
        b = q.view(np.uint8).reshape(-1, 4)[:, :3]
        data = b.tobytes()
        tag, bits = 1, 24
    else:
        raise ValueError(fmt)
    block = ch * bits // 8
    fmt_chunk = struct.pack("<HHIIHH", tag, ch, sr, sr * block, block, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
    if tag == 3:
        body += b"fact" + struct.pack("<II", 4, n)
    body += b"data" + struct.pack("<I", len(data)) + data
    if len(data) % 2:
        body += b"\x00"
    return b"RIFF" + struct.pack("<I", len(body)) + body


def write_wav(path: Path | str, x: np.ndarray, sr: int, fmt: str = "f32") -> Path:
    return atomic_bytes(Path(path), wav_bytes(x, sr, fmt))


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    """Read a PCM/float WAV written by write_wav (or any simple RIFF WAV). Returns ([ch, n] float64, sr)."""
    b = Path(path).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError(f"not a WAV file: {path}")
    pos = 12
    tag = ch = sr = bits = None
    data = None
    while pos + 8 <= len(b):
        cid, size = b[pos : pos + 4], struct.unpack("<I", b[pos + 4 : pos + 8])[0]
        body = b[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, sr, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE:  # WAVE_FORMAT_EXTENSIBLE: sub-format GUID starts with the real tag
                tag = struct.unpack("<H", body[24:26])[0]
        elif cid == b"data":
            data = body
        pos += 8 + size + (size % 2)
    if data is None or tag is None:
        raise ValueError(f"incomplete WAV: {path}")
    if tag == 3 and bits == 32:
        a = np.frombuffer(data, "<f4").astype(np.float64)
    elif tag == 1 and bits == 16:
        a = np.frombuffer(data, "<i2").astype(np.float64) / 32768.0
    elif tag == 1 and bits == 24:
        u = np.frombuffer(data, np.uint8).reshape(-1, 3).astype(np.int32)
        v = u[:, 0] | (u[:, 1] << 8) | (u[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        a = v.astype(np.float64) / Q24
    elif tag == 1 and bits == 32:
        a = np.frombuffer(data, "<i4").astype(np.float64) / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV format tag={tag} bits={bits}")
    return a.reshape(-1, ch).T.copy(), int(sr)


def ffmpeg_exe() -> str:
    """ffmpeg resolution as in PLAN §3.4: MVH_FFMPEG, then %LOCALAPPDATA%/mvh/config.json, then PATH."""
    env = os.environ.get("MVH_FFMPEG")
    if env and Path(env).exists():
        return env
    cfg = Path(os.environ.get("LOCALAPPDATA", "")) / "mvh" / "config.json"
    if cfg.exists():
        import json

        with open(cfg, encoding="utf-8-sig") as fh:
            p = json.load(fh).get("ffmpeg")
        if p and Path(p).exists():
            return p
    return "ffmpeg"


def ffprobe_exe() -> str:
    env = os.environ.get("MVH_FFPROBE")
    if env and Path(env).exists():
        return env
    ff = Path(ffmpeg_exe())
    cand = ff.with_name("ffprobe" + ff.suffix)
    return str(cand) if cand.exists() else "ffprobe"


_BITEXACT = ["-fflags", "+bitexact", "-flags:a", "+bitexact"]


def encode(
    path: Path | str,
    x: np.ndarray,
    sr: int,
    codec: str,
    *,
    tags: Mapping[str, str] | None = None,
    extra: Sequence[str] = (),
    cover: Path | None = None,
    in_sr: int | None = None,
) -> Path:
    """Encode float samples [ch, n] with ffmpeg. codec: flac24 | flac16 | mp3 | opus | wav16.

    The output is written atomically (temp name, then os.replace). Deterministic: bitexact flags, fixed
    encoder settings, no timestamps."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    a = _as_2d(np.asarray(x, dtype=np.float64))
    ch = a.shape[0]
    raw = np.ascontiguousarray(a.T).astype("<f4").tobytes()
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    cmd = [
        ffmpeg_exe(),
        "-y",
        "-v",
        "error",
        "-nostdin",
        *_BITEXACT,
        "-f",
        "f32le",
        "-ar",
        str(in_sr or sr),
        "-ac",
        str(ch),
        "-i",
        "pipe:0",
    ]
    if cover is not None:
        cmd += [
            "-i",
            str(cover),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c:v",
            "copy",
            "-disposition:v",
            "attached_pic",
            "-metadata:s:v",
            "comment=Cover (front)",
        ]
    cmd += ["-map_metadata", "-1"]
    for k, v in (tags or {}).items():
        cmd += ["-metadata", f"{k}={v}"]
    if codec == "flac24":
        cmd += ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24", "-compression_level", "5"]
    elif codec == "flac16":
        cmd += ["-c:a", "flac", "-sample_fmt", "s16", "-compression_level", "5"]
    elif codec == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", "192k"]
    elif codec == "opus":
        cmd += ["-c:a", "libopus", "-b:a", "96k", "-vbr", "off", "-application", "audio"]
    elif codec == "wav16":
        cmd += ["-c:a", "pcm_s16le"]
    else:
        raise ValueError(codec)
    if in_sr and in_sr != sr:
        cmd += ["-ar", str(sr)]
    cmd += [*_BITEXACT, *extra, str(tmp)]
    r = subprocess.run(cmd, input=raw, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed ({codec}): {r.stderr.decode('utf-8', 'replace')[-800:]}")
    os.replace(tmp, path)
    return path


def decode(path: Path | str, sr: int | None = None, mono: bool = False) -> tuple[np.ndarray, int]:
    """Decode with ffmpeg (``-map 0:a:0``) to float32; returns ([ch, n] float64, sr)."""
    probe = subprocess.run(
        [
            ffprobe_exe(),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if probe.returncode != 0:
        raise RuntimeError(probe.stderr[-500:])
    fields = [f for f in probe.stdout.strip().split(",") if f]
    src_sr, src_ch = int(fields[0]), int(fields[1])
    out_sr = sr or src_sr
    out_ch = 1 if mono else src_ch
    cmd = [
        ffmpeg_exe(),
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-f",
        "f32le",
        "-ac",
        str(out_ch),
        "-ar",
        str(out_sr),
        "pipe:1",
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-500:])
    a = np.frombuffer(r.stdout, "<f4").astype(np.float64)
    return a.reshape(-1, out_ch).T.copy(), out_sr
