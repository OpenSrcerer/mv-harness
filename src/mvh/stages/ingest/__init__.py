"""ingest stage (PLAN §5 ingest, CONTRACT §1/D23; owner W1b-runtime).

Decodes the input with ffmpeg only (``-map 0:a:0``, float32, native sample rate and channel count; decoder
warnings
captured), and writes:
* ``canonical.wav`` (cache only): the float32 decode every stage reads through ``ctx.audio('mix')``; its
  interleaved-PCM sha256 is ``pcm_sha256``;
* ``audio/mix.flac`` (24-bit, the soundtrack and timebase) and ``audio/mix.wav`` (float) when |x| > 1 (D23);
* ``audio/preview.opus`` for the viewer;
* ``artwork/cover.jpg`` (when the file has embedded art) and a deterministic k-means palette;
* ``meta/source.json``: decode facts and tags (keys lower-cased; lyric tags are NOT copied there, NF5: their
  text
  goes to the cache-only ``embedded_lyrics.json``).
A truncated corrupt frame (Versatile.flac loses its last 2291 samples) is a warning, not an error. 48 kHz
input
stays 48 kHz. Lossy input: the decode is the lossless reference that becomes the timebase.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mvh.runner.spec import ExternalInput, Output, StageError, StageResult, StageSpec, catalog_outputs

STAGE = StageSpec(
    "ingest",
    (),
    "main",
    "1.0.0",
    override_keys=(),
    outputs=catalog_outputs("ingest")
    + (
        Output(
            "embedded_lyrics.json",
            "json",
            None,
            required=False,
            public=False,
            description="lyric tags found in the file (cache only; never published, NF5)",
        ),
    ),
    params={"palette_k": 6, "preview_bitrate_kbps": 96},
    external_inputs=(ExternalInput("input", "param:input", True, "the song file given to mvh analyze"),),
    uses_ffmpeg=True,
    module="W1b-runtime",
    description="Decode with ffmpeg (-map 0:a:0, float32, native rate), hash the canonical WAV, "
    "export mix.flac/preview.opus, cover and palette.",
)

#: tag keys whose values are lyric text (never copied into meta/source.json)
LYRIC_TAG_PREFIXES = ("lyrics", "unsyncedlyrics", "unsynced lyrics", "uslt", "sylt", "syncedlyrics", "lyric")


def _is_lyric_tag(k: str) -> bool:
    k = k.lower()
    return any(
        k == p or k.startswith(p + "-") or k.startswith(p + ":") or k.startswith(p + "_")
        for p in LYRIC_TAG_PREFIXES
    )


def _tags(pr: dict) -> tuple[dict[str, str], dict[str, str]]:
    """(tags, lyric_tags): format tags overlaid by the audio stream's tags; keys lower-cased."""
    raw: dict[str, str] = {}
    for src in [pr.get("format", {}).get("tags", {})] + [
        s.get("tags", {}) for s in pr.get("streams", []) if s.get("codec_type") == "audio"
    ][:1]:
        for k, v in (src or {}).items():
            raw.setdefault(str(k).lower(), str(v))
    tags = {k: v for k, v in sorted(raw.items()) if not _is_lyric_tag(k)}
    lyr = {k: v for k, v in sorted(raw.items()) if _is_lyric_tag(k)}
    return tags, lyr


def palette(img_path: Path, k: int = 6) -> list[str]:
    """Deterministic k-means palette of an image (most common colour first)."""
    from PIL import Image

    with Image.open(img_path) as im:
        im = im.convert("RGB")
        im.thumbnail((96, 96), Image.Resampling.BILINEAR)
        px = np.asarray(im, dtype=np.float64).reshape(-1, 3)
    if px.size == 0:
        return []
    q = np.unique(np.round(px / 4.0) * 4.0, axis=0)
    k = int(max(1, min(k, len(q))))
    # farthest-point initialisation from the mean colour (deterministic)
    cent = [px.mean(axis=0)]
    for _ in range(1, k):
        d = np.min(((q[:, None, :] - np.array(cent)[None, :, :]) ** 2).sum(-1), axis=1)
        cent.append(q[int(np.argmax(d))])
    c = np.array(cent)
    for _ in range(25):
        lab = np.argmin(((px[:, None, :] - c[None, :, :]) ** 2).sum(-1), axis=1)
        new = np.array([px[lab == j].mean(axis=0) if np.any(lab == j) else c[j] for j in range(k)])
        if np.allclose(new, c, atol=0.25):
            c = new
            break
        c = new
    lab = np.argmin(((px[:, None, :] - c[None, :, :]) ** 2).sum(-1), axis=1)
    counts = np.bincount(lab, minlength=k)
    order = sorted(range(k), key=lambda j: (-int(counts[j]), tuple(np.round(c[j]).astype(int))))
    out = []
    for j in order:
        if counts[j] == 0:
            continue
        r, g, b = (int(np.clip(round(float(x)), 0, 255)) for x in c[j])
        h = f"#{r:02x}{g:02x}{b:02x}"
        if h not in out:
            out.append(h)
    return out[:12]


def run(ctx) -> StageResult:
    from mvh.io import audio as aio

    src = ctx.external("input")
    if src is None:
        raise StageError("ingest needs an input file (mvh analyze <song>)")
    src = Path(src)
    pr = aio.probe(src)
    st = aio.first_audio_stream(pr)
    d = aio.decode(src)
    x, sr = d.samples, d.sr
    if not np.isfinite(x).all():
        raise StageError("the decode contains NaN/inf samples")
    n = int(x.shape[1])
    ch = int(x.shape[0])
    peak = float(np.abs(x).max(initial=0.0))
    warnings: list[str] = []

    # samples the container promised but the decoder could not deliver (e.g. a truncated corrupt last frame)
    expected = None
    dur = st.get("duration") or pr.get("format", {}).get("duration")
    try:
        expected = int(round(float(dur) * sr)) if dur is not None else None
    except (TypeError, ValueError):
        expected = None
    missing = max(0, expected - n) if expected is not None else 0
    if d.warnings:
        warnings.append(
            f"decoder reported {len(d.warnings)} warning(s); the decodable audio was kept"
            + (
                f" ({missing} samples = {missing / sr * 1000:.0f} ms short of the container duration)"
                if missing > 0
                else ""
            )
        )
    elif missing > int(0.05 * sr):
        warnings.append(f"decoded audio is {missing} samples shorter than the container duration")

    ctx.writer.audio("canonical.wav", x, sr)
    ctx.writer.audio("audio/mix.flac", x, sr)  # + audio/mix.wav (float) when peak > 1 (D23)
    ctx.writer.audio("audio/preview.opus", x, sr)

    has_cover = False
    pal: list[str] = []
    cover_tmp = Path(ctx.scratch) / "cover.jpg"
    try:
        has_cover = aio.extract_cover(src, cover_tmp)
    except Exception as e:  # noqa: BLE001  (cover art is optional)
        warnings.append(f"cover art could not be extracted: {type(e).__name__}")
    if has_cover:
        ctx.writer.copy("artwork/cover.jpg", cover_tmp)
        try:
            pal = palette(cover_tmp, int(ctx.params.get("palette_k", 6)))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"palette failed: {type(e).__name__}")

    tags, lyric_tags = _tags(pr)
    if lyric_tags:
        ctx.writer.json("embedded_lyrics.json", {"tags": lyric_tags})
    codec = str(st.get("codec_name") or d.codec or "")
    source = {
        "file_name": src.name,
        "codec": codec,
        "sample_rate": int(sr),
        "channels": ch,
        "n_samples": n,
        "duration_s": round(n / float(sr), 6),
        "pcm_sha256": aio.pcm_sha256(x),
        "lossless": codec in aio.LOSSLESS_CODECS,
        "peak_abs": round(peak, 9),
        "decode_warnings": len(d.warnings),
        "tags": tags,
        "has_cover": bool(has_cover),
        "palette": pal,
        "soundtrack": "audio/mix.wav" if peak > 1.0 else "audio/mix.flac",
        "missing_samples": int(missing),
        "embedded_lyrics_tags": sorted(lyric_tags),
    }
    ctx.writer.json("meta/source.json", source)
    return StageResult(
        status="ok",
        summary={
            "sample_rate": int(sr),
            "channels": ch,
            "duration_s": source["duration_s"],
            "lossless": source["lossless"],
            "peak_abs": source["peak_abs"],
            "decode_warnings": len(d.warnings),
            "has_cover": bool(has_cover),
        },
        warnings=warnings,
        provenance={"notes": [f"decoded with ffmpeg -map 0:a:0 at the native rate ({sr} Hz, {ch} ch)"]},
    )
