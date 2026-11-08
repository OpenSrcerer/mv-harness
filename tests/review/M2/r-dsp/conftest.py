"""r-dsp-m2 reviewer tests (PLAN §11): evidence for the blocker/major findings on module M2
(rhythm, structure, choreo, cues). Fast and synthetic by default; ``real`` tests (W0 real-song cache,
no model inference) are opt-in: -m real or MVH_REAL_TESTS=1."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
for _p in (REPO / "src", REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from tests.synth.m2.testing import configure, skip_optin  # noqa: E402


def pytest_configure(config):
    configure(config)


def pytest_collection_modifyitems(config, items):
    skip_optin(config, items)
