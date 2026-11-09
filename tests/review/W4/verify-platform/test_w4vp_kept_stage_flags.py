"""W4 verify-platform r2: W4VP-7 (minor, RUNTIME finalize.build_manifest), left open by the W4VP-1 fix.

build_manifest now lists the outputs a stale / pending / failed stage keeps in the folder (W4-P6), but it still reads
the stage's flags, warnings and summary only from a record of THIS run (st.record). For a kept stage the manifest
therefore lists its files and drops `degraded:<stage>`, its `fallback:*` flags, its warnings and its summary.stages
entry, although the files listed are exactly the degraded / fallback outputs those flags describe. The last-good cache
entry (the same one used to list the files) carries them.

Real (integrator rc.2 copies after a scoped run, out/_wip/w4verify-platform-r2/stale-*): MEGAFAUNA flags 17 -> 8
(degraded:vocals, degraded:voices and the vocals_stem / asr_no_vad fallbacks gone), warnings 7 -> 1, summary.stages
3 -> 0; Versatile flags 8 -> 5 (degraded:vocals gone), warnings 6 -> 1, summary.stages 7 -> 0.

Fast test: identity on a tone warns and summarises; identity goes stale, the run touches loudness.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
STALE_MEGAFAUNA = ROOT / "out" / "_wip" / "w4verify-platform-r2" / "stale-megafauna"
INTEGRATOR_MEGAFAUNA = ROOT / "out" / "_wip" / "integrator" / "megafauna"


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


def test_kept_stage_keeps_its_warnings_and_summary(tmp_path):
    from mvh import testing

    src = testing.tone(tmp_path / "in" / "s.flac", seconds=3.0, sr=44100)
    folder = tmp_path / "out" / "s"
    r = _mvh("analyze", str(src), "--out", str(folder), "--only", "ingest,identity,loudness")
    assert r.returncode == 0, r.stderr[-600:]
    man0 = _json(folder / "manifest.json")
    w0 = [w for w in man0["warnings"] if w.startswith("identity:")]
    assert w0 and "identity" in man0["summary"]["stages"], "precondition: identity warns and summarises on a tone"
    _mvh("analyze", str(folder), "--only", "loudness", "--param", "identity.foo=2")
    man = _json(folder / "manifest.json")
    assert man["status"]["stages"].get("identity") == "stale", "precondition: identity is stale"
    assert "meta/identity.json" in {f["path"] for f in man["files"]}, "precondition: its output is kept and listed"
    lost = [w for w in w0 if w not in man["warnings"]]
    assert not lost and "identity" in man["summary"]["stages"], (
        f"the manifest lists identity's kept meta/identity.json but drops its warnings {lost} and its summary.stages "
        "entry (both are in the stage's last-good cache entry, which build_manifest already reads for the file list)"
    )


@pytest.mark.real
@pytest.mark.skipif(not (STALE_MEGAFAUNA / "manifest.json").is_file(), reason="needs the r2 stale MEGAFAUNA copy")
def test_real_megafauna_scoped_run_keeps_degraded_flags():
    before = set(_json(INTEGRATOR_MEGAFAUNA / "manifest.json")["status"]["flags"])
    man = _json(STALE_MEGAFAUNA / "manifest.json")
    listed = {f["stage"] for f in man["files"]}
    lost = sorted(f for f in before if f.startswith("degraded:") and f.split(":", 1)[1] in listed
                  and f not in man["status"]["flags"])
    assert not lost, f"kept outputs of {[f.split(':', 1)[1] for f in lost]} are listed but {lost} is gone"
