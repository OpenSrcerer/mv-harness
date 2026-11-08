"""`mvh frames` CLI: params are merged into the folder's run settings, and a run that cannot happen
(upstream stale or missing) is reported with its reason and a non-zero exit, never as an empty success."""
from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from mvh.runner import run as rr
from mvh.stages.frames import cli


def _args(folder, **kw):
    base = dict(folder=str(folder), fps=["24"], frame0=0, early=False, curves="", events="default",
                format="csv", replace=False, threads=1)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def fake_runner(monkeypatch, tmp_path):
    seen: dict = {}
    prev = {"slug": "s", "profile": "max", "params_ext": {"input": "x.flac"},
            "cli_params": {"frames": {"fps": [{"fps": "30", "frame0": 0, "early": False}]}}}
    monkeypatch.setattr(rr, "load_run_settings", lambda folder: prev)

    def analyze(settings):
        seen["settings"] = settings
        if seen.get("write"):
            (tmp_path / "frames").mkdir(exist_ok=True)
            (tmp_path / "frames" / "24fps.csv").write_text("frame,t\n0,0\n", encoding="utf-8")
        return {"warnings": [], "failed": []}

    def status(folder):
        ok = SimpleNamespace(status="done", reason="")
        states = {d: ok for d in cli_deps()}
        ran = bool(seen.get("write"))  # a run that wrote its export leaves the stage done
        states["notes"] = SimpleNamespace(status="done" if ran else "stale", reason="")
        states["frames"] = SimpleNamespace(status="done" if ran else "pending", reason="")
        return states

    monkeypatch.setattr(rr, "analyze", analyze)
    monkeypatch.setattr(rr, "status", status)
    return seen


def cli_deps():
    from mvh.stages.frames import STAGE

    return STAGE.deps


def test_rates_are_added_to_the_recorded_ones(fake_runner, tmp_path, capsys):
    fake_runner["write"] = True
    assert cli.cmd_frames(_args(tmp_path, fps=["24", "24000/1001"], frame0=1)) == 0
    rules = fake_runner["settings"].cli_params["frames"]["fps"]
    assert [r["fps"] for r in rules] == ["30", "24", "24000/1001"]
    assert fake_runner["settings"].only == ("frames",)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["frames"] and "not_run" not in out


def test_stale_upstream_is_reported_not_silent(fake_runner, tmp_path, capsys):
    rc = cli.cmd_frames(_args(tmp_path))
    cap = capsys.readouterr()
    out = json.loads(cap.out.strip().splitlines()[-1])
    assert rc == 1
    assert out["frames"] == []
    assert "notes (stale)" in out["not_run"]
    assert "did not run" in cap.err
