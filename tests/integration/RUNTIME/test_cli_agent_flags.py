"""W3 (D52, M6b CR-2 / M6a CR-2): mvh analyze --intent / --meaning-draft / --no-lyrics-to-agents, and re-runs keep
the earlier run's --lyrics and --param values."""

from __future__ import annotations

import json

import pytest

from mvh import cli
from mvh.runner import run as rr


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def fake_analyze(settings):
        seen["s"] = settings
        if settings.song is not None:   # what Runner.__init__ records
            settings.params_ext.setdefault("input", str(settings.song.resolve()))
        elif "input" not in settings.params_ext:
            settings.params_ext["input"] = rr.load_run_settings(settings.song_dir)["params_ext"]["input"]
        rr._write_run_settings(settings)
        return {"manifest": None, "brief": None, "viewer": None, "warnings": [], "pending": [], "failed": [], "valid": True}

    monkeypatch.setattr(rr, "analyze", fake_analyze)
    return seen


def _run(argv):
    a = cli.build_parser(with_stage_verbs=False).parse_args(argv)
    return a.func(a)


def test_no_lyrics_to_agents_sets_meaning_and_viewer(tmp_path, captured):
    song = tmp_path / "a.flac"
    song.write_bytes(b"x")
    out = tmp_path / "out"
    assert _run(["analyze", str(song), "--out", str(out), "--slug", "a", "--no-lyrics-to-agents",
                 "--meaning-draft", "off"]) == 0
    cp = captured["s"].cli_params
    assert cp["meaning"] == {"lyrics_to_agents": False, "draft": "off"}
    assert cp["viewer"] == {"inline_lyrics": False}


def test_rerun_keeps_params_and_lyrics(tmp_path, captured):
    song = tmp_path / "a.flac"
    song.write_bytes(b"x")
    lyr = tmp_path / "l.txt"
    lyr.write_text("la la\n", encoding="utf-8")
    out = tmp_path / "out"
    assert _run(["analyze", str(song), "--out", str(out), "--slug", "a", "--lyrics", str(lyr),
                 "--param", "rhythm.bpm_hint=120", "--no-lyrics-to-agents"]) == 0
    assert _run(["analyze", str(out), "--param", "viewer.inline_cap_mb=10"]) == 0
    s = captured["s"]
    assert s.params_ext.get("lyrics") == str(lyr.resolve())
    assert s.cli_params["rhythm"] == {"bpm_hint": 120}
    assert s.cli_params["viewer"] == {"inline_lyrics": False, "inline_cap_mb": 10}
    assert s.cli_params["meaning"]["lyrics_to_agents"] is False
    assert _run(["analyze", str(out), "--lyrics", "-"]) == 0
    assert "lyrics" not in captured["s"].params_ext


def test_intent_is_copied_but_never_replaces_a_different_file(tmp_path, captured):
    song = tmp_path / "a.flac"
    song.write_bytes(b"x")
    it = tmp_path / "my intent.md"
    it.write_text("## Characters\n- C1 Ann\n", encoding="utf-8")
    out = tmp_path / "out"
    assert _run(["analyze", str(song), "--out", str(out), "--slug", "a", "--intent", str(it)]) == 0
    dst = out / "meaning" / "intent.md"
    assert dst.read_text(encoding="utf-8") == it.read_text(encoding="utf-8")
    assert _run(["analyze", str(song), "--out", str(out), "--slug", "a", "--intent", str(it)]) == 0
    other = tmp_path / "other.md"
    other.write_text("different\n", encoding="utf-8")
    assert _run(["analyze", str(song), "--out", str(out), "--slug", "a", "--intent", str(other)]) == 2
    assert json.dumps(dst.read_text(encoding="utf-8")) == json.dumps(it.read_text(encoding="utf-8"))
