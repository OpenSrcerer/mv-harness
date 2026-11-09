"""W3 seam S08 (D64): run.json separates the heavy-slot wait from the stage time, and a no-op re-run (all cache hits)
keeps reporting what each stage cost when it was computed."""

from __future__ import annotations

import json

from mvh.contract import schemas
from mvh.runner import run as rr


def test_wait_and_computed_seconds(tmp_path, tone48, skeleton, monkeypatch, no_heavy_locks):
    monkeypatch.setenv("MVH_FIXTURE_DIR", str(skeleton))
    monkeypatch.setenv("MVH_STAGE_STUBS", "all-but-ingest")
    song = tmp_path / "song"

    def settings():
        return rr.Settings(song=tone48, song_dir=song, slug="tone", progress=lambda m: None, heavy_locks=False)

    rr.analyze(settings())
    run1 = json.loads((song / "run.json").read_text(encoding="utf-8"))
    assert schemas.validate(run1, "mvh/envelope/run") == []
    s1 = run1["stages"]["ingest"]
    assert s1["cache"] == "miss" and s1["wait_s"] is not None and 0 <= s1["wait_s"] <= s1["seconds"]
    rr.analyze(settings())
    run2 = json.loads((song / "run.json").read_text(encoding="utf-8"))
    assert schemas.validate(run2, "mvh/envelope/run") == []
    s2 = run2["stages"]["ingest"]
    assert s2["cache"] == "hit"
    assert abs(s2["computed_seconds"] - s1["seconds"]) < 1e-3
