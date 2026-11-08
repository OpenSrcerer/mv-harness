"""Shared pytest setup (PLAN §12): src/ on sys.path, MVH_THREADS (default 3) applied to the thread variables
in code,
UTF-8 stdio, and a few session fixtures for runtime tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mvh.testing import apply_threads  # noqa: E402

THREADS = apply_threads()  # MVH_THREADS (default 3) -> OMP/OPENBLAS/MKL/NUMBA/... before heavy imports


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def tone48(tmp_path_factory) -> Path:
    """A 3 s 48 kHz stereo tone as FLAC in a folder whose name has spaces and non-ASCII characters."""
    from mvh import testing

    d = tmp_path_factory.mktemp("tone") / "in dir ünï"
    return testing.tone(d / "tëst ♪ 曲.flac", seconds=3.0, sr=48000)


@pytest.fixture(scope="session")
def skeleton(tmp_path_factory, tone48) -> Path:
    """A minimal walking-skeleton fixture sized for ``tone48`` (MVH_FIXTURE_DIR target)."""
    from mvh import testing
    from mvh.io import audio as aio

    d = aio.decode(tone48)
    return testing.make_skeleton_fixture(tmp_path_factory.mktemp("skeleton"), d.n, d.sr)


@pytest.fixture
def no_heavy_locks(monkeypatch):
    monkeypatch.setenv("MVH_HEAVY_LOCKS", "0")


def pytest_report_header(config):
    return f"mvh: MVH_THREADS={THREADS} OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')}"
