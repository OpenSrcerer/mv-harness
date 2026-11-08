"""io/: atomic writes, float WAV, the ffmpeg resolver, ffmpeg-only decode/encode, the Job Object."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mvh import testing
from mvh.io import atomic, audio, ffmpeg, proc
from mvh.io.wav import read_wav, wav_info, write_wav


# ------------------------------------------------------------------------------------------- atomic
def test_atomic_write_retries_permission_error(tmp_path, monkeypatch):
    calls = {"n": 0}
    real = os.replace

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked by the indexer")
        return real(a, b)

    monkeypatch.setattr(os, "replace", flaky)
    p = atomic.write_text(tmp_path / "a b" / "x.json", "{}\n")
    assert p.read_text(encoding="utf-8") == "{}\n" and calls["n"] == 3
    assert [q.name for q in p.parent.iterdir()] == ["x.json"]  # no temp files left


def test_atomic_text_is_lf_utf8(tmp_path):
    p = atomic.write_text(tmp_path / "t.txt", "ä\n♪\n")
    assert p.read_bytes() == "ä\n♪\n".encode("utf-8")


# ------------------------------------------------------------------------------------------- wav
@pytest.mark.parametrize("ch", [1, 2, 6])
def test_wav_roundtrip(tmp_path, ch):
    x = np.random.default_rng(0).uniform(-1.5, 1.5, (ch, 1000)).astype(np.float32)
    write_wav(tmp_path / "x.wav", x, 44100)
    y, sr = read_wav(tmp_path / "x.wav")
    assert sr == 44100 and y.shape == x.shape and np.array_equal(x, y)
    assert wav_info(tmp_path / "x.wav")["format"] == "float"


def test_wav_reads_pcm_written_by_ffmpeg(tmp_path):
    x = (0.25 * np.sin(np.arange(4800) / 10)).astype(np.float32)[None].repeat(2, 0)
    write_wav(tmp_path / "f.wav", x, 48000)
    for fmt, tol in (("pcm_s16le", 1e-4), ("pcm_s24le", 1e-6)):
        out = tmp_path / f"{fmt}.wav"
        r = ffmpeg.run_ffmpeg(["-y", "-i", tmp_path / "f.wav", "-c:a", fmt, out])
        assert r.returncode == 0
        y, sr = read_wav(out)
        assert sr == 48000 and np.abs(y - x).max() < tol


# ------------------------------------------------------------------------------------------- resolver
def test_resolver_order(tmp_path, monkeypatch):
    real = ffmpeg.resolve_ffmpeg()
    fake = tmp_path / "bin dir" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.parent.mkdir()
    fake.write_bytes(b"")
    monkeypatch.setenv("MVH_FFMPEG", str(fake))
    assert ffmpeg.resolve_ffmpeg() == fake
    # config.json (with a BOM: PowerShell 5.1 writes one) is next
    monkeypatch.delenv("MVH_FFMPEG")
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.json").write_text(json.dumps({"ffmpeg": str(real)}), encoding="utf-8-sig")
    monkeypatch.setenv("MVH_HOME", str(home))
    assert ffmpeg.resolve_ffmpeg() == real
    # then PATH
    (home / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("PATH", str(real.parent) + os.pathsep + os.environ.get("PATH", ""))
    assert Path(ffmpeg.resolve_ffmpeg()).parent == real.parent
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ffmpeg.FfmpegNotFound):
        ffmpeg.resolve_ffmpeg()


def test_child_env_puts_ffmpeg_first():
    env = ffmpeg.child_env({"PATH": r"C:\x;C:\y"})
    assert env["PATH"].split(os.pathsep)[0] == str(ffmpeg.bin_dir())
    assert env["PYTHONUTF8"] == "1" and Path(env["MVH_FFMPEG"]).is_file()


def test_ffmpeg_info_flags():
    fi = ffmpeg.info()
    assert fi["version"].startswith("9.") and fi["has"]["chromaprint"] and fi["has"]["libopus"]


# ------------------------------------------------------------------------------------------- decode / encode
def test_decode_native_rate_and_unicode_path(tone48):
    d = audio.decode(tone48)
    assert (
        d.sr == 48000 and d.samples.shape == (2, 144000) and d.samples.dtype == np.float32 and not d.warnings
    )
    m = audio.decode(tone48, sr=16000, mono=True)
    assert m.sr == 16000 and m.samples.shape[0] == 1 and abs(m.n - 48000) <= 2


def test_flac_and_opus_are_bit_exact(tmp_path):
    x = (0.5 * np.sin(np.arange(48000) / 7)).astype(np.float32)[None].repeat(2, 0)
    a = audio.encode_flac(x, 48000, tmp_path / "a.flac").read_bytes()
    b = audio.encode_flac(x, 48000, tmp_path / "b.flac").read_bytes()
    assert a == b
    assert (
        audio.encode_opus(x, 48000, tmp_path / "a.opus").read_bytes()
        == audio.encode_opus(x, 48000, tmp_path / "b.opus").read_bytes()
    )
    y = audio.decode(tmp_path / "a.flac").samples
    assert np.abs(y - x).max() < 2e-7  # 24-bit


def test_truncated_flac_is_a_warning(tmp_path):
    src = testing.tone(tmp_path / "t.flac", seconds=2.0, sr=44100)
    data = src.read_bytes()
    bad = tmp_path / "cut.flac"
    bad.write_bytes(data[: len(data) - 1500])  # chop the end of the last frame
    d = audio.decode(bad)
    assert d.n > 44100 and d.warnings  # audio kept, decoder complained


def test_mp3_decodes(tmp_path):
    p = testing.tone(tmp_path / "t.mp3", seconds=2.0, sr=44100)
    d = audio.decode(p)
    assert d.sr == 44100 and abs(d.n - 88200) < 1200 and d.codec == "mp3"


def test_extract_cover(tmp_path):
    t = testing.tone(tmp_path / "t.flac", seconds=1.0)
    out = tmp_path / "with cover.flac"
    img = tmp_path / "img.jpg"
    r = ffmpeg.run_ffmpeg(["-y", "-f", "lavfi", "-i", "color=c=0x3366cc:s=64x64", "-frames:v", "1", img])
    assert r.returncode == 0, r.stderr
    r = ffmpeg.run_ffmpeg(
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
            "-c",
            "copy",
            "-disposition:v",
            "attached_pic",
            out,
        ]
    )
    assert r.returncode == 0, r.stderr
    assert audio.extract_cover(out, tmp_path / "c.jpg") and (tmp_path / "c.jpg").stat().st_size > 100
    assert not audio.extract_cover(t, tmp_path / "none.jpg")
    d = audio.decode(out)  # -map 0:a:0 skips the picture stream
    assert d.samples.shape[0] == 2


def test_children_run_in_the_kill_on_close_job():
    p = proc.popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
    try:
        if os.name == "nt":
            assert proc.in_job(p)
    finally:
        p.wait()
    with pytest.raises(ValueError):
        proc.popen(["x"], shell=True)


def test_job_kills_children_when_parent_dies(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows Job Object")
    marker = tmp_path / "alive.txt"
    code = (
        "import sys, time, subprocess\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from mvh.io import proc\n"
        "body = 'import time,sys; time.sleep(3); open(sys.argv[1], \"w\").write(\"x\")'\n"
        "c = proc.popen([sys.executable, '-c', body, sys.argv[2]])\n"
        "print(c.pid, flush=True)\n"
        "import os; os._exit(0)\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code, str(Path(audio.__file__).parents[2]), str(marker)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    import time

    time.sleep(4)
    assert not marker.exists()  # the grandchild died with its job
