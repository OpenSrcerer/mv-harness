# ruff: noqa: E501
"""brief tests: synthetic fixture by default; real-song runs are marked ``real`` (-m real or MVH_REAL_TESTS=1)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SYNTH = ROOT / "tests" / "contract" / "synth"


def pytest_configure(config):
    config.addinivalue_line("markers", "real: reads the real-song contract fixtures (opt-in: -m real or MVH_REAL_TESTS=1)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MVH_REAL_TESTS") == "1" or "real" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="real-song test: run with -m real or MVH_REAL_TESTS=1")
    for it in items:
        if "real" in it.keywords:
            it.add_marker(skip)


def run_m6b(work: Path, fixture: Path, intent: bool = True, authored: bool = True):
    """meaning + brief on a fixture through the runner child entry point; -> (DevRun, published song folder)."""
    from mvh.stages.meaning.devrun import DevRun

    dr = DevRun(fixture, work)
    (dr.song_dir / "meaning").mkdir(parents=True, exist_ok=True)
    for f, on in (("intent.md", intent), ("authored.json", authored)):
        if on and (fixture / "meaning" / f).is_file():
            shutil.copyfile(fixture / "meaning" / f, dr.song_dir / "meaning" / f)
    dr.run("meaning")
    dr.run("brief")
    song = dr.publish(work / "published")
    return dr, song


@pytest.fixture(scope="module")
def synth_run(tmp_path_factory):
    if not (SYNTH / ".done.json").is_file():
        pytest.skip("tests/contract/synth is not built")
    return run_m6b(tmp_path_factory.mktemp("brief"), SYNTH)


@pytest.fixture
def m6b_runner():
    return run_m6b
