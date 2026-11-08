"""Audio decode/encode through ffmpeg ONLY (NF3, PLAN §3.1): never torchaudio.load, never soundfile on
originals.

decode(path, sr=None, mono=False) -> Decoded(samples[ch, n] float32, sr, warnings, ...)
    ``ffmpeg -i <path> -map 0:a:0 -vn -f f32le`` (the cover-art stream is skipped), native rate unless
    ``sr`` is
    given (then ``aresample`` with soxr when the build has it). Mono = the mean of the channels (numpy).
    Decoder warnings are captured (a truncated corrupt frame is a warning, not an error).
encode_flac / encode_opus / encode_wav: from float32 arrays (piped as f32le), bit-exact flags, no metadata.
probe(path): ffprobe JSON (streams, format, tags).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import atomic, proc
from .ffmpeg import child_env, info, resolve_ffmpeg, resolve_ffprobe
from .wav import write_wav

__all__ = [
    "Decoded",
    "AudioError",
    "probe",
    "first_audio_stream",
    "decode",
    "encode_flac",
    "encode_opus",
    "encode_wav",
    "extract_cover",
    "pcm_sha256",
    "LOSSLESS_CODECS",
]

LOSSLESS_CODECS = {
    "flac",
    "alac",
    "wavpack",
    "ape",
    "tta",
    "mlp",
    "truehd",
    "shorten",
    "tak",
    "pcm_s16le",
    "pcm_s24le",
    "pcm_s32le",
    "pcm_f32le",
    "pcm_f64le",
    "pcm_s16be",
    "pcm_s24be",
    "pcm_s32be",
    "pcm_f32be",
    "pcm_u8",
    "pcm_s8",
}


class AudioError(RuntimeError):
    pass


@dataclass
class Decoded:
    samples: np.ndarray  # float32 [channels, n]
    sr: int
    warnings: list[str] = field(default_factory=list)
    returncode: int = 0
    source_channels: int = 0
    codec: str = ""

    @property
    def n(self) -> int:
        return int(self.samples.shape[1])

    @property
    def duration_s(self) -> float:
        return self.n / float(self.sr)


def probe(path: Path | str) -> dict[str, Any]:
    r = proc.run(
        [
            resolve_ffprobe(),
            "-v",
            "error",
            "-hide_banner",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            os.fspath(path),
        ],
        text=True,
        timeout=120,
        env=child_env(),
    )
    if r.returncode != 0:
        raise AudioError(f"ffprobe failed on {Path(path).name}: {(r.stderr or '').strip()[:500]}")
    return json.loads(r.stdout or "{}")


def first_audio_stream(pr: dict[str, Any]) -> dict[str, Any]:
    for s in pr.get("streams", []):
        if s.get("codec_type") == "audio":
            return s
    raise AudioError("no audio stream")


def _resample_filter(sr: int) -> list[str]:
    try:
        soxr = info()["has"].get("libsoxr", False)
    except Exception:  # noqa: BLE001
        soxr = False
    return ["-af", f"aresample={sr}:resampler=soxr:precision=28" if soxr else f"aresample={sr}"]


def decode(
    path: Path | str, sr: int | None = None, mono: bool = False, *, timeout: float | None = None
) -> Decoded:
    path = Path(path)
    if not path.is_file():
        raise AudioError(f"no such file: {path}")
    pr = probe(path)
    st = first_audio_stream(pr)
    ch = int(st.get("channels") or 0)
    native = int(st.get("sample_rate") or 0)
    if ch <= 0 or native <= 0:
        raise AudioError(f"cannot read channels/sample rate of {path.name}")
    out_sr = int(sr or native)
    args: list[Any] = [
        resolve_ffmpeg(),
        "-nostdin",
        "-hide_banner",
        "-v",
        "warning",
        "-i",
        path,
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
    ]
    if out_sr != native:
        args += _resample_filter(out_sr)
    args += ["-ac", str(ch), "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
    r = proc.run(args, timeout=timeout, env=child_env())
    raw = r.stdout or b""
    warnings = [
        ln.strip() for ln in (r.stderr or b"").decode("utf-8", errors="replace").splitlines() if ln.strip()
    ]
    usable = len(raw) - (len(raw) % (4 * ch))
    if usable == 0:
        raise AudioError(
            f"ffmpeg decoded no audio from {path.name} (exit {r.returncode}): "
            f"{' | '.join(warnings[:5])[:500]}"
        )
    if r.returncode != 0:
        warnings.append(
            f"ffmpeg exited with {r.returncode}; "
            f"{usable // (4 * ch)} frames decoded before the error were kept"
        )
    a = np.frombuffer(raw[:usable], dtype="<f4").reshape(-1, ch).T.astype(np.float32, copy=True)
    if mono and a.shape[0] > 1:
        a = a.mean(axis=0, dtype=np.float64).astype(np.float32)[None, :]
    return Decoded(a, out_sr, warnings, r.returncode, ch, str(st.get("codec_name") or ""))


def pcm_sha256(samples: np.ndarray) -> str:
    """sha256 of the interleaved float32 little-endian PCM (the canonical decode's content hash)."""
    a = np.ascontiguousarray(np.asarray(samples, dtype=np.float32).T).astype("<f4", copy=False)
    return hashlib.sha256(a.tobytes()).hexdigest()


def _encode(samples: np.ndarray, sr: int, dst: Path | str, codec_args: list[str], fmt: str) -> Path:
    a = np.asarray(samples, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    ch = a.shape[0]
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.enc.tmp")
    data = np.ascontiguousarray(a.T).astype("<f4", copy=False).tobytes()
    args = [
        resolve_ffmpeg(),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-f",
        "f32le",
        "-ar",
        str(int(sr)),
        "-ac",
        str(ch),
        "-i",
        "pipe:0",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        *codec_args,
        "-f",
        fmt,
        tmp,
    ]
    try:
        r = proc.run(args, input=data, env=child_env())
        if r.returncode != 0 or not tmp.exists():
            err = (r.stderr or b"").decode("utf-8", "replace").strip()[:500]
            raise AudioError(f"ffmpeg {fmt} encode failed: {err}")
        atomic.replace_retry(tmp, dst)
    finally:
        if tmp.exists():
            atomic.unlink_retry(tmp)
    return dst


def encode_flac(samples: np.ndarray, sr: int, dst: Path | str, bits: int = 24) -> Path:
    """24-bit FLAC (values beyond full scale clip: write a float WAV twin as well, D23)."""
    fmt_args = ["-c:a", "flac", "-compression_level", "8"]
    fmt_args += ["-sample_fmt", "s32", "-bits_per_raw_sample", "24"] if bits == 24 else ["-sample_fmt", "s16"]
    return _encode(samples, sr, dst, fmt_args, "flac")


def encode_opus(samples: np.ndarray, sr: int, dst: Path | str, kbps: int = 96) -> Path:
    return _encode(
        samples,
        sr,
        dst,
        [
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            f"{int(kbps)}k",
            "-vbr",
            "on",
            "-compression_level",
            "10",
        ],
        "ogg",
    )


def encode_wav(samples: np.ndarray, sr: int, dst: Path | str) -> Path:
    """float32 WAV, written by our own writer (bit-exact, no ffmpeg needed)."""
    return write_wav(dst, samples, sr)


def extract_cover(path: Path | str, dst: Path | str) -> bool:
    """Write the embedded cover (attached picture) as JPEG. False when the file has none."""
    pr = probe(path)
    vids = [s for s in pr.get("streams", []) if s.get("codec_type") == "video"]
    if not vids:
        return False
    pics = [s for s in vids if (s.get("disposition") or {}).get("attached_pic")] or vids
    st = pics[0]
    idx = vids.index(st)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.tmp.jpg")
    if st.get("codec_name") == "mjpeg":
        codec = ["-c:v", "copy"]
    else:
        codec = ["-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj444p"]
    args = [
        resolve_ffmpeg(),
        "-nostdin",
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-i",
        os.fspath(path),
        "-map",
        f"0:v:{idx}",
        "-frames:v",
        "1",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        *codec,
        "-f",
        "image2",
        tmp,
    ]
    try:
        r = proc.run(args, env=child_env())
        if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            return False
        atomic.replace_retry(tmp, dst)
        return True
    finally:
        if tmp.exists():
            atomic.unlink_retry(tmp)
