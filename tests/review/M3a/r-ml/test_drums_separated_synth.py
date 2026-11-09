"""R-ML review M3a, finding F1: the drum stage misses the PLAN §7 gates on the synthetic song when it runs on what
the separators actually produce.

PLAN §7 / module brief: drums F1 >= 0.9 kick/snare/hat and >= 0.7 tom/cymbal **on the synthetic song**, event time =
the one-shot's sample onset. The builder's ``tests/unit/drums`` score the DrumSep path on the generator's own clean
sub-stems (``tests/contract/synth/stems/drums/*.flac``), i.e. an oracle separation: the models are never in the loop.
Here the synthetic MIX goes through separate_hq (BS-RoFormer-SW -> MDX23C DrumSep) and the drum stage, as in
production. Measured (ROCm, overlap 4, 2026-11-08): kick 1.000, snare 0.979, hat 0.749, tom 0.800, cymbal 0.615;
the crashes on the drop (34.5 s) and on the final hit (52.5 s), both velocity 1.0, come out as ``hat`` (DrumSep routes
them into its hi-hat stem and nothing re-labels them), and 52 quiet off-beat drop hats are lost.
"""
from __future__ import annotations

import json

import pytest
from m3a_rml_util import scores, truth

pytestmark = [pytest.mark.real, pytest.mark.slow]


def _items(out):
    with open(out / "events" / "drum_hits.json", encoding="utf-8") as fh:
        return json.load(fh)["items"]


def test_drumsep_path_meets_plan_f1_on_the_separated_synthetic_song(synth_e2e):
    items = _items(synth_e2e)
    assert {it["source"] for it in items} == {"drumsep"}
    f1 = scores(items, truth()["drum_hits"])
    failing = {d: v for d, v in f1.items() if v < (0.9 if d in ("kick", "snare", "hat") else 0.7)}
    assert not failing, f"PLAN §7 drum F1 gates missed on separated stems: {failing} (all: {f1})"


def test_loud_crashes_are_reported_as_cymbals(synth_e2e):
    """Every crash of velocity >= 0.8 (the drop at 34.5 s, the impact at 42.5 s and the final hit at 52.5 s) is a
    cymbal hit within 10 ms. These are the strongest visual accents of the song."""
    items = _items(synth_e2e)
    crashes = [h for h in truth()["drum_hits"] if h.get("inst") == "crash" and h["vel"] >= 0.8]
    assert crashes
    missing = []
    for h in crashes:
        near = [it for it in items if abs(it["t"] - h["t"]) <= 0.010]
        if not any(it["drum"] == "cymbal" for it in near):
            missing.append((h["t"], sorted({it["drum"] for it in near})))
    assert not missing, f"crashes not reported as cymbal (t, labels found instead): {missing}"
