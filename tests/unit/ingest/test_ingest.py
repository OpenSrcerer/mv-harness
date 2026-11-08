"""The real ingest stage (PLAN §5 ingest, CONTRACT D23), run through the runner with --only ingest."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mvh import testing
from mvh.contract import schemas
from mvh.io import audio as aio
from mvh.io.ffmpeg import run_ffmpeg
from mvh.io.wav import read_wav, write_wav
from mvh.runner import run as rr

VERSATILE = Path(__file__).resolve().parents[4] / "viz" / "Versatile.flac"


def _ingest(song: Path, song_dir: Path) -> tuple[rr.StageState, dict]:
    s = rr.Settings(
        song=song,
        song_dir=song_dir,
        slug="ingest-test",
        only=("ingest",),
        heavy_locks=False,
        progress=lambda m: None,
    )
    r = rr.Runner(s)
    r.run()
    st = r.states["ingest"]
    src = (
        json.loads((song_dir / "meta/source.json").read_text(encoding="utf-8")) if st.status == "done" else {}
    )
    return st, src


def test_48k_stays_48k(tmp_path, tone48):
    st, src = _ingest(tone48, tmp_path / "s")
    assert st.status == "done" and st.record["result"]["warnings"] == []
    assert schemas.validate(src, "mvh/files/source") == []
    assert (
        src["sample_rate"] == 48000
        and src["n_samples"] == 144000
        and src["lossless"]
        and src["codec"] == "flac"
    )
    assert src["soundtrack"] == "audio/mix.flac" and not (tmp_path / "s/audio/mix.wav").exists()
    mix = aio.decode(tmp_path / "s/audio/mix.flac")
    assert mix.sr == 48000 and mix.n == 144000
    assert (tmp_path / "s/audio/preview.opus").stat().st_size > 1000
    # the canonical float decode is cache-only and hashes to pcm_sha256
    can = Path(st.record and (tmp_path / "s/.cache/ingest" / st.pre_key / "canonical.wav"))
    x, sr = read_wav(can)
    assert sr == 48000 and aio.pcm_sha256(x) == src["pcm_sha256"]
    assert not (tmp_path / "s/canonical.wav").exists()
    assert np.abs(mix.samples - x).max() < 2e-7


def test_over_full_scale_gets_a_float_twin(tmp_path):
    x = (1.5 * np.sin(np.arange(22050) / 5)).astype(np.float32)[None].repeat(2, 0)
    song = write_wav(tmp_path / "loud float.wav", x, 22050)
    st, src = _ingest(song, tmp_path / "s")
    assert st.status == "done" and src["soundtrack"] == "audio/mix.wav" and src["peak_abs"] > 1.4
    y, sr = read_wav(tmp_path / "s/audio/mix.wav")
    assert sr == 22050 and np.array_equal(y, x)
    assert (tmp_path / "s/audio/mix.flac").is_file()


def test_mono_mp3_and_lyric_tags(tmp_path):
    t = testing.tone(tmp_path / "t.wav", seconds=1.5, sr=22050, channels=1)
    mp3 = tmp_path / "song.mp3"
    r = run_ffmpeg(
        [
            "-y",
            "-i",
            t,
            "-metadata",
            "title=Synthetic Title",
            "-metadata",
            "lyrics=la la synthetic words",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            mp3,
        ]
    )
    assert r.returncode == 0
    st, src = _ingest(mp3, tmp_path / "s")
    assert st.status == "done" and src["channels"] == 1 and not src["lossless"] and src["codec"] == "mp3"
    assert src["tags"]["title"] == "Synthetic Title"
    assert not any("lyric" in k for k in src["tags"]) and src["embedded_lyrics_tags"]
    assert "la la" not in (tmp_path / "s/meta/source.json").read_text(encoding="utf-8")
    assert not (tmp_path / "s/embedded_lyrics.json").exists()  # cache only, never published
    cached = tmp_path / "s/.cache/ingest" / st.pre_key / "embedded_lyrics.json"
    assert "la la" in cached.read_text(encoding="utf-8")


def test_cover_and_palette(tmp_path):
    t = testing.tone(tmp_path / "t.flac", seconds=1.0)
    img = tmp_path / "img.png"
    assert (
        run_ffmpeg(["-y", "-f", "lavfi", "-i", "color=c=0x3366cc:s=32x32", "-frames:v", "1", img]).returncode
        == 0
    )
    song = tmp_path / "with cover.flac"
    assert (
        run_ffmpeg(
            [
                "-y",
                "-i",
                t,
                "-i",
                img,
                "-map",
                "0:a",
                "-map",
                "1:v",
                "-c:a",
                "copy",
                "-c:v",
                "png",
                "-disposition:v",
                "attached_pic",
                song,
            ]
        ).returncode
        == 0
    )
    st, src = _ingest(song, tmp_path / "s")
    assert src["has_cover"] and (tmp_path / "s/artwork/cover.jpg").is_file()
    r, g, b = (int(src["palette"][0][i : i + 2], 16) for i in (1, 3, 5))
    assert abs(r - 0x33) < 12 and abs(g - 0x66) < 12 and abs(b - 0xCC) < 12


def test_truncated_frame_is_a_warning(tmp_path):
    t = testing.tone(tmp_path / "t.flac", seconds=2.0, sr=44100)
    data = t.read_bytes()
    bad = tmp_path / "cut.flac"
    bad.write_bytes(data[: len(data) - 1500])
    st, src = _ingest(bad, tmp_path / "s")
    assert st.status == "done" and src["decode_warnings"] > 0
    assert any("decoder reported" in w for w in st.record["result"]["warnings"])


@pytest.mark.skipif(not VERSATILE.is_file(), reason="viz/Versatile.flac not present")
def test_versatile_corrupt_last_frame(tmp_path):
    st, src = _ingest(VERSATILE, tmp_path / "s")
    assert st.status == "done"
    assert src["n_samples"] == 10043392 and src["missing_samples"] == 2291 and src["decode_warnings"] == 2
    assert src["has_cover"] and src["palette"] and src["sample_rate"] == 44100
    assert any("2291 samples" in w for w in st.record["result"]["warnings"])
