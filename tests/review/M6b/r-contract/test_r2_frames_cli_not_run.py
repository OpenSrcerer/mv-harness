# ruff: noqa: E501
"""R-CONTRACT (M6b) round 2, R2-6 (major): ``mvh frames`` reports success when the frames stage did not run but an
earlier export is still on disk.

``cmd_frames`` only asks why the stage did not run when ``frames/`` is empty
(``blocked = _not_run_reason(rr, folder) if not out else None``). The runner leaves an on-demand stage ``pending``
("upstream not done: <dep> (stale)") when an upstream is stale (e.g. the user fixed beats in the viewer and
``mvh analyze`` has not re-run, or an upstream failed), and it never removes that stage's earlier published files.
A video agent that runs ``mvh frames out/<slug> --fps 30`` (SKILL.md table) then gets exit code 0 and a JSON report
listing only the old ``24fps.csv``: the requested 30 fps export does not exist, and a re-export at the same rate after
a correction silently leaves the stale CSV in place.

The runner is replaced by a stand-in that does exactly what run.Runner does in that state (status ``pending`` with an
"upstream not done" reason, no files touched); the rest is the real CLI code.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mvh.runner import run as rr
from mvh.stages.frames import cli


def test_frames_verb_fails_when_the_stage_did_not_run_even_if_old_exports_exist(tmp_path: Path, monkeypatch, capsys) -> None:
    song = tmp_path / "song"
    (song / "frames").mkdir(parents=True)
    (song / "frames" / "24fps.csv").write_text("frame,t\n0,0.0\n", encoding="utf-8")  # an earlier export
    monkeypatch.setattr(rr, "load_run_settings", lambda folder: {"params_ext": {"input": "song.flac"}, "cli_params": {
        "frames": {"fps": [{"fps": "24", "frame0": 0, "early": False}]}}})
    # finalize lists only analyze-trigger stages under "pending", so an on-demand frames stage never appears there
    monkeypatch.setattr(rr, "analyze", lambda s: {"warnings": [], "failed": None, "pending": []})
    states = {"frames": rr.StageState("frames", status="pending", reason="upstream not done: rhythm (stale)"),
              "rhythm": rr.StageState("rhythm", status="stale", reason="overrides changed")}
    monkeypatch.setattr(rr, "status", lambda folder, **kw: states)
    a = argparse.Namespace(folder=str(song), fps=["30"], frame0=0, early=False, curves="", events="default",
                           format="csv", replace=False, threads=1)
    code = cli.cmd_frames(a)
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert not (song / "frames" / "30fps.csv").exists()
    assert code != 0 and "not_run" in report, (
        f"mvh frames --fps 30 exited {code} with report {report}: success is reported although the stage did not run "
        "and 30fps.csv was not written (only the old 24fps.csv is listed)")
