"""R-ML review M3a round 2, finding N3: the F1 drum gates hold only for one exact separation output.

The fix round meets PLAN §7 on the 44.1 kHz synthetic song run end to end (kick 1.000, snare 0.993, hat 0.918, tom
0.857, cymbal 0.769; reproduced exactly on a fresh ROCm run). The SAME song resampled to 48 kHz (a PLAN §7 edge case;
separate_hq resamples it back to 44.1 kHz for the models) gives kick 0.994, snare 0.980, hat 0.908, tom 0.545,
cymbal 0.514. The drum detector is not the cause (the 44.1 kHz run's sub-stems resampled to 48 kHz score the 44.1 kHz
values, the 48 kHz run's sub-stems resampled to 44.1 kHz score the 48 kHz values): DrumSep's ride / crash / tom
stems change between the runs (ride -2.8 dB, crash -5.2 dB relative difference), 10 of the 16 rides and 5 of the 8
toms are then not even candidates, and nothing recovers them from the full drum stem (the classifier cross-check only
raises the conf of hits that already exist). The 44.1 kHz pass rests on margins of 1-2 hits per class.
"""
from __future__ import annotations

import json

import pytest
from m3a_rml_util import scores, truth

pytestmark = [pytest.mark.real, pytest.mark.slow]


def test_drum_gates_hold_on_the_48k_synthetic_song(synth48_e2e):
    with open(synth48_e2e / "events" / "drum_hits.json", encoding="utf-8") as fh:
        items = json.load(fh)["items"]
    f1 = scores(items, truth()["drum_hits"])
    failing = {d: v for d, v in f1.items() if v < (0.9 if d in ("kick", "snare", "hat") else 0.7)}
    assert not failing, f"PLAN §7 drum F1 gates missed on the 48 kHz synthetic song: {failing} (all: {f1})"
