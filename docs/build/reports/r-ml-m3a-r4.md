# r-ml-m3a-r4: R-ML review of M3a, round 4 (W3 verify)

Verdict: **fail**. There are 2 new majors and no blockers. R3-1 is fixed for the ride, but the fix causes R4-1.

## What was run
- Review tests in tests/review/M3a/r-ml:
  - fast: 6 pass, including `test_r3_drums_ride_eighths.py`;
  - real / slow, with fresh end-to-end synthetic runs on the current code and CPU DrumSep: 4 pass and
    `test_r2_drums_separated_synth_48k.py` **fails** (cymbal .596, gate .7; it passed at .714 in round 3).
- tests/integration/M3a plus the M3a unit tests: 56 passed, 10 skipped.
- `drums.core.drumsep_hits` at rise floors of 4, 6 and 8 dB on:
  - the round-3 separated variants (ride-8ths mix, 48 kHz, -6 dB master);
  - the integrator's real sub-stems (jeremy, megafauna, newton-vs-nye, versatile).
- The four stages re-run (`--force`) on copies of the integrator's newton-vs-nye and versatile folders
  (out/_wip/r-ml-m3a-r4/real/<slug>): rc 0 on both.
- Probes: out/_wip/r-ml-m3a-r4/probe/.

## R3-1 (8th-note ride)
Fixed for the ride stem. On the round-3 separated ride-8ths mix, ride recall goes from .219 to .812 and cymbal F1 from
.385 to .806. On jeremy, the 35 ride-stem hits the new floor adds are real strokes: 69 % sit on the 16th grid (chance
28 %), and 71 % show a 6-16 kHz rise in the drums stem.

## New majors
- **R4-1** (`src/mvh/stages/drums/core.py` drumsep_hits, `cymbal_rise_db=4.0` applied to the crash stem too): crash-stem
  artefacts and ring bumps become cymbal hits.
  - 48 kHz synthetic song: cymbal F1 .714 -> .596, below the gate.
  - Real songs: jeremy +81 crash hits and megafauna +34. They are at chance on the 16th grid and show no onset in the
    DrumSep input, yet carry conf about .8.
  - Tests: `tests/review/M3a/r-ml/test_r4_drums_crash_floor.py` (new, 24 s) and
    `tests/review/M3a/r-ml/test_r2_drums_separated_synth_48k.py` (existing, real).
- **R4-2** (`src/mvh/sep/hq_worker.py` and D47): the Mel-RoFormer vocals and the karaoke lead / backing are not
  bit-reproducible on ROCm. On newton-vs-nye:
  - vocals: max 4e-7, 87 % of samples differ;
  - lead: -75 dB residual;
  - backing: -52 dB residual.

  The SW 6-stem and CPU DrumSep outputs are identical, and versatile matched. NF1 therefore still fails
  intermittently. Test: `tests/review/M3a/r-ml/test_r4_hq_vocals_determinism.py`.

## Verified OK
- D47: CPU DrumSep matches the W0 ROCm sub-stems (residual -92 to -139 dB), and `worker.devices` is recorded.
- Separator invariants on the reruns: sum and gain pass; instrumental + vocals and lead + backing at -150 dB.
- Karaoke flags are unchanged.

## Minors
In docs/review/M3a-r-ml.md, Round 4:
- r4-m1: jeremy's crash stem was already mostly artefacts at 8 dB.
- r4-m2: the classifier's cymbal confirmation is not specific (1002 cymbals on jeremy).
- r4-m3: hats -14 on jeremy at 4 dB.

The review doc also notes that real kick and snare FLACs exceed full scale, and the stage reads their WAV copies. That
is a contract note, not a model-use defect.
