"""W4 verify-platform r2: W4VP-8 (minor, RUNTIME finalize.build_manifest), introduced by the W4VP-1 fix.

The amended D34 says the kept outputs of a stale / pending / failed stage stay listed and "`status.stages` gives their
status". For the on-demand stage `frames` it does not: build_manifest skips non-analyze stages that are not current
when it builds status.stages, but the new kept-files loop lists their files. After `mvh frames --fps 24` and a later
`mvh analyze` that changes an upstream (here a meaning param), the manifest lists frames/24fps.csv (computed from the
previous analysis) with no status.stages entry for frames; only the generic "kept" warning names it. Before the fix
the stale CSV was not listed at all.

Real (read-only): out/_wip/w4verify-platform-r2/synth, an rc.3 synth max copy after `mvh frames --fps 24` and then
`mvh analyze <folder> --param meaning.foo=2` (`mvh status`: frames stale, upstream changed: meaning).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SYNTH = ROOT / "out" / "_wip" / "w4verify-platform-r2" / "synth"


def _json(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.real
@pytest.mark.skipif(not (SYNTH / "frames" / "24fps.csv").is_file(), reason="needs the r2 synth copy with frames")
def test_every_listed_stage_has_a_status():
    man = _json(SYNTH / "manifest.json")
    stages = {f["stage"] for f in man["files"] if not f["stage"].startswith("_")}
    missing = sorted(s for s in stages if s not in man["status"]["stages"])
    assert not missing, (
        f"files of {missing} are listed (kept from a previous run) but status.stages has no entry for them, so an "
        "agent cannot tell that frames/24fps.csv is stale (D34: status.stages gives their status)"
    )
