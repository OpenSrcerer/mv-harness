# ruff: noqa: E501  (long numeric tables / docstrings)
"""M3b unit-test setup (owner builder-m3b): markers, and the shared synthetic run of instruments -> notes -> vocals."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "real: needs the real songs and models (run with MVH_REAL=1)")
    config.addinivalue_line("markers", "slow: real model inference (seconds to minutes)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MVH_REAL") == "1":
        return
    skip = pytest.mark.skip(reason="real-song test: set MVH_REAL=1")
    for it in items:
        if "real" in it.keywords:
            it.add_marker(skip)


@pytest.fixture(scope="session")
def synth_out():
    from tests.synth.m3b.synthrun import synth_outputs

    return synth_outputs()


@pytest.fixture(scope="session")
def truth():
    from tests.synth.m3b.synthrun import truth

    return truth()
