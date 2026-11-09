"""W4 verify-platform r2: W4VP-5 (major, RUNTIME finalize.build_manifest), introduced by the W4VP-1 fix.

build_manifest now lists the published outputs of every stage a run left stale / pending / failed (W4-P6). pack_curves,
for the same stages, drops the kept curves when they "do not fit the current audio" (a different audio is in the
folder now). build_manifest applies no such rule: the events and meta of the OLD audio stay listed, next to a warning
that says "outputs and curves ... kept" right after the warning that their curves were dropped.

Flow: a song folder analysed from audio A; then audio B (another master / edit / song, different length) is analysed
into the same folder, and the run stops before the downstream stages (a scoped run here; in a full run any failing
upstream stage leaves every later stage pending the same way). The manifest then lists events/hits.kick.json,
events/onsets.*.json and meta/loudness.json computed from A: lib/mvh.js loads them as this song's events (kicks from
another audio; summary.integrated_lufs from A). Before the W4VP-1 fix these files were not listed.

Fast: real ingest + loudness + spectral on 3 s / 6 s tones, no models.
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


def _json(p: Path):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def test_outputs_kept_from_a_different_audio_are_not_listed(tmp_path):
    from mvh import testing

    a = testing.tone(tmp_path / "in" / "a.flac", seconds=3.0, freq=440.0)
    b = testing.tone(tmp_path / "in" / "b.flac", seconds=6.0, freq=220.0, amp=0.2)
    folder = tmp_path / "out" / "song"
    r = _mvh("analyze", str(a), "--out", str(folder), "--only", "ingest,loudness,spectral")
    assert r.returncode == 0, r.stderr[-600:]
    r = _mvh("analyze", str(b), "--out", str(folder), "--only", "ingest")
    assert r.returncode == 0, r.stderr[-600:]
    man = _json(folder / "manifest.json")
    assert man["source"]["duration_s"] == 6.0, "precondition: audio B is the folder's audio now"
    assert any("do not fit the current audio" in w for w in man["warnings"]), (
        "precondition: pack_curves dropped the kept curves of A as unfit"
    )
    listed = {f["path"] for f in man["files"]}
    from_a = sorted(p for p in listed if p.startswith("events/") or p == "meta/loudness.json")
    assert not from_a, (
        f"the manifest lists {from_a}, computed from the previous (3 s) audio, as outputs of the current 6 s audio; "
        "their curves were dropped as unfit but the events/meta are kept and loaded by the lib"
    )
