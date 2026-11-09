"""W4 R-DOGFOOD, finding W4D-1 (RUNTIME, major): a scoped run on a stale folder deletes curves/ and leaves events/.

Real flow: a contract/version bump makes every stage stale; the user edits meaning/intent.md and runs
`mvh meaning <folder>` (RUNS.md section 5). The runner reports "not run - upstream not done" but pack_curves
(runner/finalize.py) unlinks every curve file no stage currently produces: curves/ is emptied, events/ stays, brief.md
and manifest.json still point at the curves. A 'not run' must not destroy outputs. Seconds, no models.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _mvh(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["MVH_OFFLINE"] = "1"
    env.pop("MVH_FIXTURE_DIR", None)
    env.pop("MVH_STAGE_STUBS", None)
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "mvh.cli", *args], env=env, cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


def test_scoped_run_on_a_stale_folder_does_not_delete_curves(tmp_path):
    from mvh import testing

    src = testing.tone(tmp_path / "in" / "s.flac", seconds=3.0, sr=44100)
    folder = tmp_path / "out" / "s"
    r = _mvh("analyze", str(src), "--out", str(folder), "--only", "ingest,loudness")
    assert r.returncode == 0, r.stderr[-600:]
    before = sorted(p.name for p in (folder / "curves").iterdir())
    assert "core.f32" in before and "index.json" in before
    # make loudness stale (a changed param stands in for a version bump), then ask only for the meaning/brief stages
    _mvh("analyze", str(folder), "--only", "meaning,brief", "--param", "loudness.foo=2")
    after = sorted(p.name for p in (folder / "curves").iterdir()) if (folder / "curves").is_dir() else []
    assert after == before, f"curves/ was {before}, now {after}: a run that did not run deleted the curve files"
