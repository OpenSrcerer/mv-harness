"""Shared pytest hook for the M3a unit-test folders: tests marked ``real`` (real models or real songs) are skipped
unless selected explicitly with ``-m real`` or ``MVH_RUN_REAL=1`` (PLAN §12: unit tests default to synthetic inputs)."""

from __future__ import annotations

import os

import pytest


def skip_real_unless_selected(config, items) -> None:
    sel = config.getoption("-m") or ""
    if "real" in sel or os.environ.get("MVH_RUN_REAL") == "1":
        return
    skip = pytest.mark.skip(reason="real model / real song test: run with -m real or MVH_RUN_REAL=1")
    for it in items:
        if "real" in it.keywords:
            it.add_marker(skip)


def register_real_marker(config) -> None:
    config.addinivalue_line("markers", "real: needs real models or real songs (run with -m real or MVH_RUN_REAL=1)")
