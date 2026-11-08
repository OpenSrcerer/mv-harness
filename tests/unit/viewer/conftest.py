# ruff: noqa: E501  (long lines)
"""Fixtures for the viewer tests."""
from __future__ import annotations

from pathlib import Path

import pytest
from viewer_support import SYNTH, make_ctx


@pytest.fixture(scope="session")
def synth_dir() -> Path:
    if not (SYNTH / ".done.json").is_file():
        pytest.skip("tests/contract/synth is not built (python -m tests.synth.build --only synth)")
    return SYNTH


@pytest.fixture(scope="session")
def built_html(synth_dir) -> str:
    from mvh.stages.viewer import run

    ctx = make_ctx()
    run(ctx)
    return ctx.writer.files["viewer.html"]
