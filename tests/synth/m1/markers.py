# ruff: noqa: E501  (long formulas, tables and docstrings)
"""Shared pytest setup for the M1 unit tests: ``real`` (real songs; opt-in with MVH_REAL_TESTS=1 or ``-m real``) and
``slow`` markers, and the real-song table (W0 reference numbers from docs/spike/bench-music.md §4)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

#: slug -> (canonical decode, W0 integrated LUFS, W0 LRA, viz-port offline kick reference count)
REAL_SONGS = {
    "megafauna": (-10.81, 17.89, 464),
    "versatile": (-6.08, 14.23, 208),
    "jeremy": (-7.02, 6.49, 617),
    "newton-vs-nye": (-10.08, 3.53, 199),
}


def configure(config) -> None:
    config.addinivalue_line("markers", "real: real songs from tests/contract/real-<slug> (opt-in: MVH_REAL_TESTS=1 or -m real)")
    config.addinivalue_line("markers", "slow: takes more than ~10 s")


def collection_modifyitems(config, items) -> None:
    want_real = os.environ.get("MVH_REAL_TESTS") == "1" or "real" in (config.getoption("-m") or "")
    if want_real:
        return
    skip = pytest.mark.skip(reason="real-song test (set MVH_REAL_TESTS=1 or use -m real)")
    for it in items:
        if "real" in it.keywords:
            it.add_marker(skip)


def real_dir(slug: str) -> Path:
    return REPO / "tests" / "contract" / f"real-{slug}"


def real_available(slug: str) -> bool:
    d = real_dir(slug)
    return (d / "_intermediate" / "ingest" / "canonical.wav").is_file() and (d / "events" / "bars.json").is_file()
