"""The runner end to end on the walking skeleton (real ingest + every stub copying from a fixture)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mvh.contract import schemas
from mvh.runner import run as rr
from mvh.runner.validate import validate_folder

SRC = Path(__file__).resolve().parents[3] / "src"


@pytest.fixture
def fx(monkeypatch, skeleton, no_heavy_locks):
    monkeypatch.setenv("MVH_FIXTURE_DIR", str(skeleton))
    # W3: every stage is real now; the runtime tests keep running the walking skeleton through the child's stub seam
    monkeypatch.setenv("MVH_STAGE_STUBS", "all-but-ingest")
    return skeleton


def _settings(song, song_dir, **kw):
    return rr.Settings(
        song=song, song_dir=song_dir, slug="tone", progress=lambda m: None, heavy_locks=False, **kw
    )


def _snap(d: Path) -> dict[str, str]:
    out = {}
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d).as_posix()
        if p.is_file() and not rel.startswith((".cache/", "lib/")) and rel != "run.json":
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_walking_skeleton_cache_and_determinism(tmp_path, tone48, fx):
    song_dir = tmp_path / "out dir" / "tone"
    res = rr.analyze(_settings(tone48, song_dir))
    assert res["failed"] == [] and res["pending"] == [] and res["valid"], res["warnings"]
    man = json.loads((song_dir / "manifest.json").read_text(encoding="utf-8"))
    assert man["source"]["file_name"] == "tëst ♪ 曲.flac" and man["source"]["sample_rate"] == 48000
    assert set(man["status"]["stages"].values()) == {"done"} and "frames" not in man["status"]["stages"]
    paths = [f["path"] for f in man["files"]]
    assert paths == sorted(paths) and not any(p.startswith("schema/") for p in paths)
    assert "audio/mix.flac" in paths and "curves/index.json" in paths and "canonical.wav" not in paths
    assert (song_dir / "schema/envelope/manifest.schema.json").is_file()
    run = json.loads((song_dir / "run.json").read_text(encoding="utf-8"))
    assert schemas.validate(run, "mvh/envelope/run") == []
    assert all(s["cache"] == "miss" for s in run["stages"].values())
    snap1 = _snap(song_dir)

    # second run: every stage is a cache hit
    r = rr.Runner(_settings(tone48, song_dir))
    r.run()
    assert {st.cache for n, st in r.states.items() if n != "frames"} == {"hit"}

    # --force: everything re-runs, the folder is byte-identical (NF1)
    rr.analyze(_settings(tone48, song_dir, force=True))
    run2 = json.loads((song_dir / "run.json").read_text(encoding="utf-8"))
    assert {s["cache"] for n, s in run2["stages"].items() if n != "frames"} == {"forced"}
    assert run2["stages"]["frames"]["status"] == "pending"   # D55: on-demand stages are listed, not run
    assert _snap(song_dir) == snap1

    # mvh status: all done, frames pending
    st = rr.status(song_dir)
    assert st["ingest"].status == "done" and st["frames"].status == "pending"


def test_overrides_and_user_inputs(tmp_path, tone48, fx):
    song_dir = tmp_path / "song"
    rr.analyze(_settings(tone48, song_dir))
    (song_dir / "meaning").mkdir(exist_ok=True)
    intent = "characters: 2\nsynthetic intent text\n"
    (song_dir / "meaning/intent.md").write_text(intent, encoding="utf-8")
    st = rr.status(song_dir)
    assert st["voices"].status == "stale" and "external changed: intent" in st["voices"].reason
    assert st["lyrics"].status == "done"
    (song_dir / "overrides.json").write_text(json.dumps({"rhythm": {"bpm": 120.0}}), encoding="utf-8")
    st = rr.status(song_dir)
    assert st["rhythm"].status == "stale" and "overrides changed: rhythm.bpm" in st["rhythm"].reason
    assert st["spectral"].status == "done"
    assert st["dynamics"].status == "stale" and "rhythm (stale)" in st["dynamics"].reason
    r = rr.Runner(_settings(tone48, song_dir))
    r.run()
    assert r.states["rhythm"].cache == "miss" and r.states["dynamics"].cache == "miss"
    assert r.states["spectral"].cache == "hit" and r.states["loudness"].cache == "hit"
    assert r.states["rhythm"].record["provenance"]["overrides_applied"] == [
        {"key": "rhythm.bpm", "value": 120.0}
    ]
    assert (song_dir / "meaning/intent.md").read_text(encoding="utf-8") == intent
    assert json.loads((song_dir / "overrides.json").read_text(encoding="utf-8")) == {"rhythm": {"bpm": 120.0}}
    # the runner never deletes user inputs even with --force
    rr.analyze(_settings(tone48, song_dir, force=True))
    assert (song_dir / "meaning/intent.md").read_text(encoding="utf-8") == intent
    man = json.loads((song_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {"path": "meaning/intent.md", "kind": "text", "stage": "_user"} in man["files"]


def test_only_from_and_failures(tmp_path, tone48, skeleton, monkeypatch, no_heavy_locks):
    fx = tmp_path / "fx"
    shutil.copytree(skeleton, fx)
    monkeypatch.setenv("MVH_FIXTURE_DIR", str(fx))
    monkeypatch.setenv("MVH_STAGE_STUBS", "all-but-ingest")
    song_dir = tmp_path / "song"
    # --only without cached deps: nothing runs
    r = rr.Runner(_settings(tone48, song_dir, only=("loudness",)))
    r.run()
    assert r.states["loudness"].status == "pending" and "ingest" in r.states["loudness"].reason
    # a stage failure keeps independent branches going and marks dependants pending
    (fx / "meta/loudness.json").unlink()
    res = rr.analyze(_settings(tone48, song_dir))
    assert res["failed"] == ["loudness"]
    assert "dynamics" in res["pending"] and "spectral" not in res["pending"]
    st = rr.status(song_dir)
    assert st["loudness"].status == "failed" and "MissingFixture" in st["loudness"].reason
    man = json.loads((song_dir / "manifest.json").read_text(encoding="utf-8"))
    assert man["status"]["stages"]["loudness"] == "failed" and "failed:loudness" in man["status"]["flags"]
    assert validate_folder(song_dir).ok
    # fix the fixture: the next run picks up only what is missing
    shutil.copy(skeleton / "meta/loudness.json", fx / "meta/loudness.json")
    r = rr.Runner(_settings(tone48, song_dir))
    r.run()
    assert r.states["loudness"].cache == "miss" and r.states["spectral"].cache == "hit"
    # --only reruns exactly one cached stage; --from forces the stage and everything downstream
    r = rr.Runner(_settings(tone48, song_dir, only=("loudness",), force=True))
    r.run()
    ran = {n for n, s in r.states.items() if s.cache in ("miss", "forced")}
    assert ran == {"loudness"}
    r = rr.Runner(_settings(tone48, song_dir, from_stage="cues"))
    r.run()
    ran = {n for n, s in r.states.items() if s.cache in ("miss", "forced")}
    assert ran == {"cues", "meaning", "brief", "viewer"}


def test_cli_real_run_without_utf8_env(tmp_path, tone48, skeleton):
    """PLAN §7.4: a real CLI run on 'tëst ♪ 曲.flac' in a folder with spaces, no PYTHONUTF8/IOENCODING."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env.update(MVH_FIXTURE_DIR=str(skeleton), MVH_HEAVY_LOCKS="0", PYTHONPATH=str(SRC), MVH_STAGE_STUBS="all-but-ingest")
    out = tmp_path / "out dir with spaces ü" / "tëst"
    r = subprocess.run(
        [sys.executable, "-m", "mvh.cli", "analyze", str(tone48), "--out", str(out), "--slug", "test-song"],
        capture_output=True,
        env=env,
        timeout=600,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-3000:]
    lines = [ln for ln in r.stdout.decode("utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    d = json.loads(lines[0])
    assert set(d) == {"manifest", "brief", "viewer", "warnings", "pending"} and d["pending"] == []
    assert Path(d["manifest"]).is_file() and "ü" in d["manifest"]
    man = json.loads(Path(d["manifest"]).read_text(encoding="utf-8"))
    assert man["slug"] == "test-song" and man["source"]["file_name"] == "tëst ♪ 曲.flac"
    v = subprocess.run(
        [sys.executable, "-m", "mvh.cli", "validate", str(out)], capture_output=True, env=env, timeout=300
    )
    assert v.returncode == 0 and b"valid" in v.stdout
    s = subprocess.run(
        [sys.executable, "-m", "mvh.cli", "status", str(out), "--json"],
        capture_output=True,
        env=env,
        timeout=300,
    )
    rows = json.loads(s.stdout.decode("utf-8"))
    assert {r["status"] for r in rows if r["stage"] != "frames"} == {"done"}
