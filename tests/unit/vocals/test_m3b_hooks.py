# ruff: noqa: E501  (long numeric tables / docstrings)
"""Human-correction hooks of the M3b stages (``--param notes.piano_mode=...``, ``vocals.present``, ``vocals.style``).

Runs the stages directly on the synthetic fixture with the cached instruments output as upstream (seconds each).
"""

from __future__ import annotations

import importlib

import pytest
from tests.synth.m3b.scoring import events, jload

pytestmark = [pytest.mark.slow, pytest.mark.timeout(5400)]  # includes waiting for a machine-wide heavy slot


def _run(stage: str, synth_out, tmp_path, params):
    from tests.synth.m3b.fxctx import run_stage
    from tests.synth.m3b.synthrun import FIXTURE

    from mvh.testing import heavy

    out = tmp_path / stage
    with heavy("builder-m3b:pytest-hooks", threads=3):
        res, _ctx = run_stage(importlib.import_module(f"mvh.stages.{stage}"), FIXTURE, out, roots=[out, synth_out],
                              params=params)
    return res, out


def test_vocals_present_false_forces_absence(synth_out, tmp_path):
    res, out = _run("vocals", synth_out, tmp_path, {"present": False})
    vr = jload(out / "meta/vocal_range.json")
    assert vr["present"] is False and vr["p2"] is None and vr["lowest"] is None
    assert vr["voiced_s"] >= 8                                     # the detector's measurement is still reported
    assert any("presence set by the user" in n for n in res.provenance["notes"])


def test_vocals_style_rap_skips_sung_statistics_basis(synth_out, tmp_path):
    res, out = _run("vocals", synth_out, tmp_path, {"style": "rap"})
    vr = jload(out / "meta/vocal_range.json")
    assert vr["style"] == "rap"
    assert vr["basis"] in (None, "sung frames (rap/speech-dominant lead)")
    assert any("dominant style set by the user: rap" in n for n in res.provenance["notes"])


def test_notes_piano_mode_off(synth_out, tmp_path):
    res, out = _run("notes", synth_out, tmp_path, {"piano_mode": "off"})
    assert events(out, "notes.piano") == []
    assert "piano:basic_pitch" not in res.fallbacks
    assert jload(out / "notes/notes.json")["sources"]["piano"]["midi"] is None
    assert any("piano_mode=off" in n for n in res.provenance["notes"])
