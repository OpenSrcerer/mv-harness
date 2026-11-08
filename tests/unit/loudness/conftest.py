"""M1 unit-test setup (owner builder-m1): markers real (opt-in) and slow; see tests/synth/m1/markers.py."""

from tests.synth.m1 import markers as _m


def pytest_configure(config):
    _m.configure(config)


def pytest_collection_modifyitems(config, items):
    _m.collection_modifyitems(config, items)
