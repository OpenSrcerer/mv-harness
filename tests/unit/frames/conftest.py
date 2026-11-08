# ruff: noqa: E501
"""frames tests: synthetic by default; real-song runs are marked ``real`` (-m real or MVH_REAL_TESTS=1)."""
from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real: reads the real-song contract fixtures (opt-in: -m real or MVH_REAL_TESTS=1)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MVH_REAL_TESTS") == "1" or "real" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="real-song test: run with -m real or MVH_REAL_TESTS=1")
    for it in items:
        if "real" in it.keywords:
            it.add_marker(skip)
