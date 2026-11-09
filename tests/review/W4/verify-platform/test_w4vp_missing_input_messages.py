"""W4 verify-platform r1: W4P-1 (RUNTIME, runner/run.py) after the w4fix-platform fix. Finding W4VP-4 (minor).

With the recorded song file gone, `mvh analyze <folder> --force ingest` correctly fails ingest with the relink command.
But Runner.resolve() has already appended the content-equivalent warning ("... the cached canonical audio is used"),
and it stays in manifest.warnings and the stdout JSON next to the failure: the folder tells agents and the user that
the cache was used while ingest in fact failed and every downstream stage went pending. The warning should be added
only when the cached entry is actually used (no forced re-run). Fast: real ingest + loudness on a 3 s tone.
"""

from __future__ import annotations

import json
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


def test_forced_ingest_without_input_does_not_claim_the_cache_was_used(tmp_path):
    from mvh import testing

    src = testing.tone(tmp_path / "in" / "gone.flac", seconds=3.0, sr=44100)
    folder = tmp_path / "out" / "gone"
    r = _mvh("analyze", str(src), "--out", str(folder), "--only", "ingest,loudness")
    assert r.returncode == 0, r.stderr[-600:]
    src.unlink()
    r = _mvh("analyze", str(folder), "--only", "ingest,loudness", "--force", "ingest")
    with open(folder / "run.json", encoding="utf-8") as fh:
        st = json.load(fh)["stages"]
    assert st["ingest"]["status"] == "failed", "precondition: a forced ingest without its input fails"
    assert "Relink it" in r.stderr
    with open(folder / "manifest.json", encoding="utf-8") as fh:
        warnings = json.load(fh).get("warnings", [])
    wrong = [w for w in warnings if "cached canonical audio is used" in w]
    assert not wrong, f"ingest failed, but the manifest says the cache was used: {wrong[0][:160]}"
