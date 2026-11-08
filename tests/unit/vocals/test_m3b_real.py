# ruff: noqa: E501  (long numeric tables / docstrings)
"""M3b on the four real songs (opt-in: MVH_REAL=1; minutes per song). Snapshot assertions with tolerances.

Upstream comes from the real-song overlays (``python -m tests.synth.m3b.stem_overlay``); each test runs instruments ->
notes -> vocals through the direct harness inside one heavy slot. No lyric text is read or printed.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from tests.synth.m3b.scoring import events, jload

pytestmark = [pytest.mark.real, pytest.mark.slow, pytest.mark.timeout(7200)]
REPO = Path(__file__).resolve().parents[3]


def _run(slug: str, tmp_path: Path) -> Path:
    from tests.synth.m3b.fxctx import run_stage

    from mvh.testing import heavy

    fx = REPO / "out" / "_wip" / "builder-m3b" / "fx" / slug
    if not fx.is_dir():
        pytest.skip(f"no overlay for {slug}: run python -m tests.synth.m3b.stem_overlay {slug}")
    out = tmp_path / slug
    with heavy("builder-m3b:pytest-real", threads=3):
        for st in ("instruments", "notes", "vocals"):
            run_stage(importlib.import_module(f"mvh.stages.{st}"), fx, out, roots=[out])
    return out


def _cov(meta: dict, inst: str) -> float:
    return next((r["coverage"] for r in meta["summary"] if r["instrument"] == inst), 0.0)


def test_jeremy(tmp_path):
    out = _run("jeremy", tmp_path)
    inst = jload(out / "meta/instruments.json")
    for k in ("guitar", "bass", "drums", "voice"):
        assert _cov(inst, k) > 0.6, k
    assert _cov(inst, "piano") < 0.1 and inst["vocal_style"]["dominant"] == "singing"
    vr = jload(out / "meta/vocal_range.json")
    assert vr["present"] and vr["voiced_s"] > 100
    assert 51 <= vr["p2"] <= 56 and 67 <= vr["p98"] <= 73            # W0: sustained G3-G#4, RMVPE p98 ~73.8
    assert 50 <= vr["lowest"]["midi"] <= 56 and 66 <= vr["highest"]["midi"] <= 75
    assert vr["register"] in ("baritone", "tenor")
    nn = jload(out / "notes/notes.json")["sources"]
    assert 500 <= nn["bass"]["count"] <= 2000 and nn["bass"]["lowest"] >= 24 and nn["bass"]["highest"] <= 64
    assert nn["piano"]["count"] == 0                                   # silent piano stem: no invented notes
    assert len(events(out, "vocal_phrases")) >= 20


def test_newton_vs_nye(tmp_path):
    out = _run("newton-vs-nye", tmp_path)
    inst = jload(out / "meta/instruments.json")
    assert inst["vocal_style"]["dominant"] == "rap" and _cov(inst, "voice") > 0.6
    vr = jload(out / "meta/vocal_range.json")
    assert vr["present"] is True and vr["p2"] is None                 # rap: no sung-range statistics (docs/SPIKE.md)
    assert vr["spoken_pitch"]["seconds"] > 20
    assert jload(out / "notes/notes.json")["sources"]["bass"]["count"] > 150


def test_megafauna_vocal_stem_is_not_a_voice(tmp_path):
    out = _run("megafauna", tmp_path)
    inst = jload(out / "meta/instruments.json")
    assert _cov(inst, "voice") < 0.15                                  # the vocals stem carries synth leads
    vr = jload(out / "meta/vocal_range.json")
    assert vr["voiced_s"] < 30
    assert jload(out / "notes/notes.json")["sources"]["piano"]["count"] == 0


def test_versatile_near_instrumental(tmp_path):
    out = _run("versatile", tmp_path)
    inst = jload(out / "meta/instruments.json")
    assert _cov(inst, "bass") > 0.5 and _cov(inst, "voice") < 0.35
    assert jload(out / "meta/vocal_range.json")["present"] is False
