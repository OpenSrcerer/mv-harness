# ruff: noqa: E501  (long docstrings)
"""Fixtures for the R-ML review tests of M3a (separate_fast, separate_hq, stem_activity, drums).

``synth_e2e`` is the synthetic song run end to end through the REAL separation chain (``mvh analyze ... --only
ingest,separate_fast,separate_hq,stem_activity,drums``): BS-RoFormer-SW, Mel-RoFormer, karaoke and DrumSep run on
the mixed song in the sep worker (ROCm about 2.5 min, CPU much longer; the runner takes the heavy slots and
gpu.lock itself). The drum stage is then scored against the generator truth, which the builder's unit tests only
do on the generator's own (oracle) sub-stems.

Set ``MVH_REVIEW_M3A_SYNTH=<song folder>`` to reuse a folder that already holds such a run (the runner's cache
makes a re-run cheap: only stages whose code changed run again).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from m3a_rml_util import MONO_SPAN  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
STAGES = "ingest,separate_fast,separate_hq,stem_activity,drums"


def pytest_configure(config):
    config.addinivalue_line("markers", "real: uses real models (the runner takes the heavy slots)")
    config.addinivalue_line("markers", "slow: takes minutes")


@pytest.fixture(scope="session")
def synth_e2e(tmp_path_factory) -> Path:
    env_dir = os.environ.get("MVH_REVIEW_M3A_SYNTH")
    out = Path(env_dir) if env_dir else tmp_path_factory.mktemp("m3a-rml") / "synth"
    song = REPO / "tests" / "contract" / "synth" / "_truth" / "synth-song.flac"
    cmd = [sys.executable, "-X", "utf8", "-m", "mvh.cli", "analyze", str(song), "--out", str(out),
           "--no-network", "--only", STAGES]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=3600)
    if r.returncode != 0:
        pytest.fail(f"mvh analyze failed ({r.returncode}):\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    if not (out / "events" / "drum_hits.json").is_file():
        pytest.fail(f"no events/drum_hits.json in {out}")
    return out


@pytest.fixture(scope="session")
def synth_mono_e2e(tmp_path_factory) -> Path:
    """A MONO 12 s excerpt (17-29 s: chorus duet with V2's harmony on backing_vocals, then the build) of the synthetic
    song through ingest + the real separate_hq (about 45 s on ROCm). ``MVH_REVIEW_M3A_MONO=<song folder>`` reuses a
    folder made the same way (its input must be ``synth_mono.flac`` cut as below)."""
    import numpy as np

    from mvh.io import audio as aio

    env_dir = os.environ.get("MVH_REVIEW_M3A_MONO")
    if env_dir:
        return Path(env_dir)
    base = tmp_path_factory.mktemp("m3a-rml-mono")
    x = aio.decode(REPO / "tests" / "contract" / "synth" / "_truth" / "synth-song.flac").samples
    mono = x[:, MONO_SPAN[0] * 44100:MONO_SPAN[1] * 44100].mean(axis=0, dtype=np.float64)[None, :]
    song = base / "synth_mono.flac"
    aio.encode_flac(mono.astype(np.float32), 44100, song)
    out = base / "out"
    cmd = [sys.executable, "-X", "utf8", "-m", "mvh.cli", "analyze", str(song), "--out", str(out),
           "--no-network", "--only", "ingest,separate_hq"]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=3600)
    if r.returncode != 0:
        pytest.fail(f"mvh analyze failed ({r.returncode}):\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return out


def _analyze(song: Path, out: Path, only: str) -> Path:
    cmd = [sys.executable, "-X", "utf8", "-m", "mvh.cli", "analyze", str(song), "--out", str(out),
           "--no-network", "--only", only]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=3600)
    if r.returncode != 0:
        pytest.fail(f"mvh analyze failed ({r.returncode}):\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return out


@pytest.fixture(scope="session")
def synth48_e2e(tmp_path_factory) -> Path:
    """Round 2: the synthetic song resampled to 48 kHz (ffmpeg/soxr via mvh.io.audio) through the real separation chain
    and the drum stage (``MVH_REVIEW_M3A_SYNTH48=<song folder>`` reuses such a run)."""
    import numpy as np

    from mvh.io import audio as aio

    env_dir = os.environ.get("MVH_REVIEW_M3A_SYNTH48")
    if env_dir:
        return Path(env_dir)
    base = tmp_path_factory.mktemp("m3a-rml-48k")
    d = aio.decode(REPO / "tests" / "contract" / "synth" / "_truth" / "synth-song.flac", sr=48000)
    song = base / "synth48.flac"
    aio.encode_flac(np.asarray(d.samples, np.float32), 48000, song)
    return _analyze(song, base / "out", STAGES)


@pytest.fixture(scope="session")
def synth_narrow_e2e(tmp_path_factory) -> Path:
    """Round 2: the 17-29 s stereo excerpt with its side (L-R) scaled so side energy is 24 dB under mid (L/R correlation
    0.992: a near-mono master, not caught by ``fit.is_mono``'s -30 dB) through ingest + the real separate_hq.
    ``MVH_REVIEW_M3A_NARROW=<song folder>`` reuses such a run."""
    import numpy as np

    from mvh.io import audio as aio

    env_dir = os.environ.get("MVH_REVIEW_M3A_NARROW")
    if env_dir:
        return Path(env_dir)
    base = tmp_path_factory.mktemp("m3a-rml-narrow")
    x = aio.decode(REPO / "tests" / "contract" / "synth" / "_truth" / "synth-song.flac").samples.astype(np.float64)
    x = x[:, MONO_SPAN[0] * 44100:MONO_SPAN[1] * 44100]
    mid, side = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2
    g = 10 ** ((-24.0 - 10 * np.log10(np.sum(side ** 2) / np.sum(mid ** 2))) / 20)
    song = base / "synth_narrow24.flac"
    aio.encode_flac(np.stack([mid + g * side, mid - g * side]).astype(np.float32), 44100, song)
    return _analyze(song, base / "out", "ingest,separate_hq")
