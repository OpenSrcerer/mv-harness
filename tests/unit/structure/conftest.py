"""M2 tests: synthetic and fast by default; ``slow`` (real models on synthetic audio) and ``real`` (real-song
fixtures) are opt-in: -m slow / -m real, or MVH_SLOW_TESTS=1 / MVH_REAL_TESTS=1."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for _p in (REPO / "src", REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from tests.synth.m2.testing import configure, skip_optin  # noqa: E402


def pytest_configure(config):
    configure(config)


def pytest_collection_modifyitems(config, items):
    skip_optin(config, items)
