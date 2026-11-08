# ruff: noqa: E501
"""M5 unit tests: markers models (default on) and real (opt-in); see tests/synth/m5/pytest_markers.py."""
from tests.synth.m5 import pytest_markers as _m


def pytest_configure(config):
    _m.configure(config)


def pytest_collection_modifyitems(config, items):
    _m.modify(config, items)
