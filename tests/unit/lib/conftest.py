"""Fixtures for the helper-library tests: the standalone lib/mvh_load.py module and the golden vectors."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ASSETS = REPO / "src" / "mvh" / "assets"
GOLDEN = REPO / "docs" / "contract" / "golden-vectors.json"


def _load_module():
    """Import mvh_load.py from its file, as a song folder's lib/ would (it must not need mvh)."""
    name = "mvh_load_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ASSETS / "mvh_load.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def ml():
    return _load_module()


@pytest.fixture(scope="session")
def golden():
    with open(GOLDEN, encoding="utf-8") as fh:
        return json.load(fh)
