import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
for p in (REPO / "src", REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

SYNTH = REPO / "tests" / "contract" / "synth"


@pytest.fixture(scope="session")
def synth() -> Path:
    """The generated synthetic fixture folder (built once when .done.json is missing)."""
    if not (SYNTH / ".done.json").exists():
        from tests.synth.build import build_synth

        build_synth(SYNTH, log=lambda *a: None)
    return SYNTH


@pytest.fixture(scope="session")
def truth(synth) -> dict:
    with open(synth / "_truth" / "truth.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_json(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def ev(synth):
    """events name -> items (by the catalogue path)."""
    from mvh.contract.events import read_events

    out = {}
    for p in sorted((synth / "events").glob("*.json")):
        e = read_events(p)
        out[e.name] = e.items
    for p in sorted((synth / "lipsync").glob("*.json")):
        e = read_events(p)
        out[e.name] = e.items
    return out
