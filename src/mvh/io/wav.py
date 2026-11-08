"""Minimal WAV reader/writer for files mv-harness writes itself (stdlib + numpy; the sep worker uses it).

* write_wav(path, samples[ch, n] float32, sr): IEEE float32 WAV (WAVE_FORMAT_EXTENSIBLE above 2 channels),
  atomic.
* read_wav(path) -> (samples[ch, n] float32, sr): float32/float64 and 16/24/32-bit PCM, plain or extensible.

Never use this on a user's original file: originals are decoded by ffmpeg only (NF3).
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from .atomic import write_bytes

__all__ = ["write_wav", "read_wav", "wav_info", "wav_bytes"]

_FLOAT = 3
_PCM = 1
_EXT = 0xFFFE
_GUID_TAIL = b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"


def _as_ch_n(samples) -> np.ndarray:
    a = np.asarray(samples, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    if a.ndim != 2:
        raise ValueError("samples must be [channels, n] (or 1-D mono)")
    return a


def wav_bytes(samples, sr: int) -> bytes:
    a = _as_ch_n(samples)
    ch, n = a.shape
    data = np.ascontiguousarray(a.T).astype("<f4", copy=False).tobytes()
    block = 4 * ch
    if ch <= 2:
        fmt = struct.pack("<HHIIHH", _FLOAT, ch, int(sr), int(sr) * block, block, 32)
    else:
        mask = (1 << ch) - 1 if ch < 32 else 0
        fmt = struct.pack("<HHIIHHHHI", _EXT, ch, int(sr), int(sr) * block, block, 32, 22, 32, mask)
        fmt += struct.pack("<H", _FLOAT) + _GUID_TAIL
    fact = struct.pack("<I", n)
    body = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"fact"
        + struct.pack("<I", 4)
        + fact
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def write_wav(path: Path | str, samples, sr: int) -> Path:
    return write_bytes(path, wav_bytes(samples, sr))


def _parse(path: Path | str):
    with open(path, "rb") as fh:
        head = fh.read(12)
        if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
            raise ValueError(f"not a WAV file: {path}")
        fmt = None
        while True:
            ck = fh.read(8)
            if len(ck) < 8:
                raise ValueError(f"WAV without data chunk: {path}")
            cid, size = ck[:4], struct.unpack("<I", ck[4:])[0]
            if cid == b"fmt ":
                raw = fh.read(size)
                tag, ch, sr, _br, _ba, bits = struct.unpack("<HHIIHH", raw[:16])
                if tag == _EXT and len(raw) >= 26:
                    tag = struct.unpack("<H", raw[24:26])[0]
                fmt = (tag, ch, sr, bits)
                if size % 2:
                    fh.read(1)
            elif cid == b"data":
                if fmt is None:
                    raise ValueError(f"WAV data before fmt: {path}")
                return fmt, fh.tell(), size
            else:
                fh.seek(size + (size % 2), 1)


def wav_info(path: Path | str) -> dict:
    (tag, ch, sr, bits), _off, size = _parse(path)
    frames = size // max(1, ch * bits // 8)
    return {
        "format": "float" if tag == _FLOAT else "pcm",
        "channels": ch,
        "sample_rate": sr,
        "bits": bits,
        "frames": frames,
    }


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    (tag, ch, sr, bits), off, size = _parse(path)
    file_size = Path(path).stat().st_size
    size = min(size, file_size - off)  # streamed WAVs carry a bogus size
    bps = bits // 8
    n = size // (bps * ch)
    if tag == _FLOAT and bits in (32, 64):
        a = np.fromfile(path, dtype="<f4" if bits == 32 else "<f8", count=n * ch, offset=off).astype(
            np.float32, copy=False
        )
    elif tag == _PCM and bits == 16:
        a = np.fromfile(path, dtype="<i2", count=n * ch, offset=off).astype(np.float32) / 32768.0
    elif tag == _PCM and bits == 32:
        a = np.fromfile(path, dtype="<i4", count=n * ch, offset=off).astype(np.float64) / 2147483648.0
    elif tag == _PCM and bits == 24:
        b = np.fromfile(path, dtype=np.uint8, count=n * ch * 3, offset=off).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        a = v.astype(np.float64) / 8388608.0
    else:
        raise ValueError(f"unsupported WAV format tag={tag} bits={bits}: {path}")
    return np.ascontiguousarray(a.astype(np.float32, copy=False).reshape(n, ch).T), int(sr)
