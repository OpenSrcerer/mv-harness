"""The mvh CLI: verbs, module-verb discovery, models/validate/doctor output shapes."""

from __future__ import annotations

import json
import sys

import pytest

import mvh.stages
from mvh import cli


def test_core_verbs_present():
    p = cli.build_parser(with_stage_verbs=False)
    a = p.parse_args(
        [
            "analyze",
            "x.flac",
            "--profile",
            "draft",
            "--only",
            "ingest,spectral",
            "--force",
            "--from",
            "rhythm",
        ]
    )
    assert a.verb == "analyze" and a.profile == "draft" and a.force == "all" and a.from_stage == "rhythm"
    a = p.parse_args(["analyze", "x.flac", "--force", "rhythm,cues", "--param", "rhythm.bpm_min=60"])
    assert a.force == "rhythm,cues" and cli._parse_params(a.param) == {"rhythm": {"bpm_min": 60}}
    for v in cli.CORE_VERBS:
        assert v in p._subparsers._group_actions[0].choices


def test_stage_cli_discovery(tmp_path, monkeypatch, capsys):
    pkg = tmp_path / "mvh" / "stages" / "demo_verbs"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "cli.py").write_text(
        "def register(sub):\n"
        "    p = sub.add_parser('demo', help='a module verb')\n"
        "    p.add_argument('--n', type=int, default=1)\n"
        "    p.set_defaults(func=lambda a: print('demo', a.n) or 0)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mvh.stages, "__path__", list(mvh.stages.__path__) + [str(tmp_path / "mvh" / "stages")]
    )
    try:
        assert cli.main(["demo", "--n", "3"]) == 0
        assert capsys.readouterr().out.strip() == "demo 3"
    finally:
        for m in [m for m in sys.modules if m.startswith("mvh.stages.demo_verbs")]:
            del sys.modules[m]


def test_models_list_json(capsys):
    assert cli.main(["models", "list", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 28 and {"id", "envs", "present", "licence"} <= set(rows[0])


def test_validate_reports_errors(tmp_path, capsys):
    (tmp_path / "manifest.json").write_text('{"schema": "mvh/manifest"}', encoding="utf-8")
    assert cli.main(["validate", str(tmp_path), "--json"]) == 1
    d = json.loads(capsys.readouterr().out)
    assert not d["ok"] and d["errors"]


def test_status_needs_a_song_folder(tmp_path):
    assert cli.main(["status", str(tmp_path)]) == 2


def test_analyze_rejects_missing_file(tmp_path):
    assert cli.main(["analyze", str(tmp_path / "nope.flac")]) == 2


@pytest.mark.timeout(600)
def test_doctor_quick_json(capsys):
    rc = cli.main(["doctor", "--quick", "--json"])
    checks = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in checks}
    assert {"ffmpeg", "ffprobe", "Rhubarb"} <= names and any(n.startswith("models") for n in names)
    assert any(n.startswith("free disk") for n in names) and any(n.startswith("env main") for n in names)
    assert rc == (1 if any(c["level"] == "FAIL" for c in checks) else 0)
