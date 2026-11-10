"""fverify F-V2 (major, weakened bar): F-gain-5 picks onsets.* on the mix scaled to -10 LUFS. On the -16 LUFS synthetic
groove the default high-band onset recall fell from 0.77 to 0.64, and the unit test's bar for the default was lowered
from 0.7 to 0.6 (tests/unit/spectral/test_spectral.py::test_onsets_mid_high_on_snares_and_hats[analysis_level]).
Level invariance was bought by moving every quieter-than -10 LUFS master onto the lower-recall operating point.
This keeps the original PLAN bar (0.7) for the DEFAULT parameters."""

from __future__ import annotations

from tests.synth.m1.harness import run_m1
from tests.synth.m1.signals import f1, groove


def test_default_high_onsets_keep_the_original_recall(tmp_path):
    x, sr, truth = groove(duration_s=16.0, bass=False, pad=False, syncopated=False)
    r = run_m1(x, sr, tmp_path, stages=("spectral",))
    hi = [it["t"] for it in r["ctx"]["spectral"].written_events("onsets.high")["items"]]
    _, p, rc, _ = f1(hi, sorted([k["t"] for k in truth["hat"]] + [k["t"] for k in truth["snare"]]), 0.02)
    assert p >= 0.9 and rc >= 0.7, (
        f"default onsets.high on the -16 LUFS groove: precision {p:.3f}, recall {rc:.3f} (< 0.7; was 0.77 before F-gain-5)"
    )
