"""W4 R-PLATFORM, finding W4P-1 (RUNTIME, major): a song folder stops being re-runnable once its input file is
renamed or moved, and a rename alone re-runs the whole DAG.

* The folder remembers the input as an absolute path (``.cache/_run.json params_ext.input``). After the file is
  moved, renamed or deleted, ``mvh analyze <folder>`` (what RUNS.md section 5 and the viewer's Re-run button do)
  fails ingest with "ingest needs an input file" and every other stage becomes pending, although the ingest cache
  entry still holds the canonical audio.
* Pointing at the renamed file (same bytes) re-runs every stage: the ingest key hashes the file *name*
  (``{"sha256", "name"}``), and the changed ingest key cascades to all 25 stages (about 45 min for a real song).

Real ingest + loudness on a 3 s tone (seconds, no models).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def _analyze(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["MVH_OFFLINE"] = "1"
    env.pop("MVH_FIXTURE_DIR", None)
    env.pop("MVH_STAGE_STUBS", None)
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "mvh.cli", "analyze", *args],
        env=env, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )


def _stages(folder: Path) -> dict:
    with open(folder / "run.json", encoding="utf-8") as fh:
        return json.load(fh)["stages"]


@pytest.fixture()
def analysed(tmp_path):
    from mvh import testing

    src = testing.tone(tmp_path / "in" / "my song.flac", seconds=3.0, sr=44100)
    folder = tmp_path / "out" / "my-song"
    r = _analyze(str(src), "--out", str(folder), "--only", "ingest,loudness")
    assert r.returncode == 0, r.stderr[-800:]
    assert _stages(folder)["loudness"]["status"] == "done"
    return src, folder


def test_folder_rerun_survives_a_moved_input(analysed):
    """`mvh analyze <folder>` after the song file moved: nothing changed, so everything must be a cache hit."""
    src, folder = analysed
    moved = src.parent.parent / "elsewhere" / src.name
    moved.parent.mkdir(parents=True)
    src.rename(moved)
    r = _analyze(str(folder), "--only", "ingest,loudness")
    st = _stages(folder)
    assert st["ingest"]["status"] == "done", (
        f"folder re-run after the input moved: ingest {st['ingest']['status']} ({st['ingest'].get('warnings')}); "
        "the cached canonical audio is not used"
    )
    assert st["loudness"]["cache"] == "hit", f"loudness {st['loudness']}"
    assert r.returncode == 0


def test_renamed_input_does_not_rerun_downstream(analysed):
    """Same bytes under a new file name: downstream stages must stay cache hits."""
    src, folder = analysed
    renamed = src.with_name("my song (final).flac")
    src.rename(renamed)
    r = _analyze(str(renamed), "--out", str(folder), "--only", "ingest,loudness")
    assert r.returncode == 0, r.stderr[-800:]
    st = _stages(folder)
    assert st["loudness"]["cache"] == "hit", (
        f"renaming the song re-ran loudness (cache {st['loudness']['cache']}): the ingest key hashes the file name, "
        "so every stage of a real song re-runs"
    )
