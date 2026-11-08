# ruff: noqa: E501  (long docstrings)
"""R-ML review M3a, finding F2: the classifier path (no DrumSep sub-stems: the degraded htdemucs fallback, or a run
without sub-stems) is far below the PLAN §7 drum gates even on the clean synthetic drum stem.

PLAN §5 drums: "the DrumSep path and the classifier path tested separately"; §7: F1 >= 0.9 kick/snare/hat, >= 0.7
tom/cymbal. The builder's unit test relaxes the gate for this path (snare 0.8, hat 0.7, no tom/cymbal check).
Measured on the generator's clean drum stem: kick 0.977, snare 0.943, hat 0.795, tom 0.421, cymbal 0.160; on the
BS-RoFormer-SW drum stem of the mix: hat 0.787, tom 0.222, cymbal 0.242. Synthetic input only (fast).
"""
from __future__ import annotations

from m3a_rml_util import SYNTH, scores, truth


def test_classifier_path_meets_plan_f1_on_the_clean_synthetic_drum_stem():
    from mvh.io import audio as aio
    from mvh.stages.drums import core

    d = aio.decode(SYNTH / "stems" / "drums.flac")
    hits, _ = core.classify(d.samples, d.sr)
    f1 = scores([{"t": h.t, "drum": h.drum} for h in hits], truth()["drum_hits"])
    failing = {k: v for k, v in f1.items() if v < (0.9 if k in ("kick", "snare", "hat") else 0.7)}
    assert not failing, f"classifier path below the PLAN §7 gates: {failing} (all: {f1})"
