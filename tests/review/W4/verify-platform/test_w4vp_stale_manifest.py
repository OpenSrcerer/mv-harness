"""W4 verify-platform r1: W4D-1 (RUNTIME, finalize) after the w4fix-platform fix. Finding W4VP-1 (major).

The fix keeps the curve files of stages a scoped run left stale / pending / failed ("matching the events and meta
files it keeps in the folder", finalize.pack_curves). But build_manifest still lists only the outputs of stages that
are current in this run, so after the W4D-1 flow (a version bump, then `mvh meaning <folder>`) the manifest lists the
kept curves and NONE of the events / meta / audio files that stay on disk next to them:

* real MEGAFAUNA (copy of out/_wip/integrator/megafauna, rc.2 -> rc.3, `mvh meaning`): manifest.files 124 -> 12
  entries, events 42 -> 0, `mvh validate` checks 20 files instead of ~124 (the kept files are never validated);
* lib/mvh.js on that folder: `song.eventNames` 42 -> 0, so `kickSource` falls back to 'mix' (`song.kicks()` 647 ->
  188 kicks: an agent cuts on a different kick timeline, UD2) and `events:*` selectors return nothing.

The folder is again inconsistent after a run that did not run; only the direction changed (curves listed, their
events and meta not). Fast test: real ingest + loudness on a 3 s tone, no models.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
# r2: the r1 copy was finalized by the pre-fix code and is never re-run; the r2 copy (integrator rc.2 MEGAFAUNA after
# `mvh meaning` with the W4VP-1 fix) is read when present
STALE_MEGAFAUNA = next(
    (p for p in (ROOT / "out" / "_wip" / f"w4verify-platform-{r}" / "stale-megafauna" for r in ("r2", "r1"))
     if (p / "manifest.json").is_file()),
    ROOT / "out" / "_wip" / "w4verify-platform-r1" / "stale-megafauna",
)


def _mvh(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["MVH_OFFLINE"] = "1"
    env.pop("MVH_FIXTURE_DIR", None)
    env.pop("MVH_STAGE_STUBS", None)
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "mvh.cli", *args], env=env, cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


def _json(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def test_scoped_run_on_a_stale_folder_keeps_listing_the_kept_outputs(tmp_path):
    from mvh import testing

    src = testing.tone(tmp_path / "in" / "s.flac", seconds=3.0, sr=44100)
    folder = tmp_path / "out" / "s"
    r = _mvh("analyze", str(src), "--out", str(folder), "--only", "ingest,loudness")
    assert r.returncode == 0, r.stderr[-600:]
    listed0 = {f["path"] for f in _json(folder / "manifest.json")["files"]}
    assert "meta/loudness.json" in listed0
    # loudness goes stale (a changed param stands in for a version bump); the user asks only for meaning/brief
    _mvh("analyze", str(folder), "--only", "meaning,brief", "--param", "loudness.foo=2")
    man = _json(folder / "manifest.json")
    listed = {f["path"] for f in man["files"]}
    idx = _json(folder / "curves" / "index.json")
    loud_curves = [c["id"] for c in idx["channels"] if c["id"].startswith("loud")]
    assert (folder / "meta" / "loudness.json").is_file()
    assert loud_curves, "precondition: the stale stage's curves were kept (the W4D-1 fix)"
    assert "meta/loudness.json" in listed, (
        f"the manifest lists the kept loudness curves {loud_curves[:3]} but not meta/loudness.json, which the same "
        f"stale stage keeps on disk; listed: {sorted(listed)}"
    )


@pytest.mark.real
@pytest.mark.skipif(not (STALE_MEGAFAUNA / "manifest.json").is_file(), reason="needs the verifier's stale MEGAFAUNA copy")
def test_real_megafauna_meaning_on_stale_folder_lists_its_events():
    """Read-only on out/_wip/w4verify-platform-r1/stale-megafauna (integrator rc.2 copy after `mvh meaning`)."""
    man = _json(STALE_MEGAFAUNA / "manifest.json")
    on_disk = sorted(p.name for p in (STALE_MEGAFAUNA / "events").glob("*.json"))
    listed = [f["path"] for f in man["files"] if f.get("kind") == "events"]
    assert len(listed) >= len(on_disk) * 0.9, (
        f"{len(on_disk)} events files stay in the folder, the manifest lists {len(listed)}: lib eventNames is empty "
        "and kickSource falls back to 'mix'"
    )
