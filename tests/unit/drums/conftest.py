from tests.synth.m3a.conftest_real import register_real_marker, skip_real_unless_selected


def pytest_configure(config):
    register_real_marker(config)


def pytest_collection_modifyitems(config, items):
    skip_real_unless_selected(config, items)
