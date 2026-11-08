"""R-PLATFORM (W1b) finding: the environment points audio-separator at an EMPTY model folder.

``models.lock.json`` installs every separator model under ``<models>/separator/`` (that is where
``mvh models fetch`` put them), but ``scripts/mvh-env.ps1`` (and ``mvh-env.cmd``) export
``AUDIO_SEPARATOR_MODEL_DIR=<mvh home>/models/audio-separator``, an empty folder. The runner's
``_child_env`` only ``setdefault``s its own (correct) ``models/separator`` value, so under the env script -
which every agent, the gate and the user's shell use - every stage child and the sep worker inherit the empty
folder. ``mvh doctor`` reports that variable as OK.

audio-separator 0.48 lets this variable OVERRIDE an explicit ``Separator(model_file_dir=...)`` argument
(``audio_separator/separator/separator.py`` lines 185-194 in envs/sep/.venv-cpu), so "M3a passes the explicit
paths from job.json" (the runtime report's mitigation) does not help: the separator looks in the empty folder
and downloads every model it does not find from its mirrors (HF_HUB_OFFLINE does not stop that): ~1.5 GB of
unpinned files outside ``mvh models fetch`` (PLAN §3.3 "the only downloader"), or a failure offline.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from mvh.runner import models
from mvh.runner import run as rr

REPO = Path(__file__).resolve().parents[4]


def _separator_dir() -> Path:
    files = [f["path"] for e in models.entries() for f in e["files"] if f["path"].startswith("separator/")]
    assert files, "models.lock.json has no separator/ files"
    return models.local_path(files[0]).parent


def _env_script_value() -> str:
    ps = REPO / "scripts" / "mvh-env.ps1"
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f". '{ps}' -Offline | Out-Null; Write-Output $env:AUDIO_SEPARATOR_MODEL_DIR",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    assert lines, r.stdout + r.stderr
    return lines[-1]


@pytest.mark.skipif(os.name != "nt", reason="Windows env script")
def test_stage_children_see_the_separator_model_folder(monkeypatch):
    want = _separator_dir()
    value = _env_script_value()
    monkeypatch.setenv("AUDIO_SEPARATOR_MODEL_DIR", value)  # exactly what mvh-env.ps1 exports
    env = rr.Runner._child_env(SimpleNamespace(s=SimpleNamespace(offline=True)), 3)
    got = Path(env["AUDIO_SEPARATOR_MODEL_DIR"])
    assert os.path.normcase(str(got)) == os.path.normcase(str(want)), (
        f"stage children get AUDIO_SEPARATOR_MODEL_DIR={got} "
        f"({len(list(got.glob('*'))) if got.is_dir() else 'missing'} files) but the separator models are in "
        f"{want}"
    )
