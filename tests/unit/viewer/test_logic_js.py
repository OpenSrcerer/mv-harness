# ruff: noqa: E501  (long lines)
"""Runs the node unit tests of the DOM-free viewer logic (logic.test.mjs) under pytest so the gate covers them."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_logic_node_tests():
    r = subprocess.run(["node", "--test", str(HERE / "logic.test.mjs")], capture_output=True, text=True, timeout=120, encoding="utf-8")
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]
