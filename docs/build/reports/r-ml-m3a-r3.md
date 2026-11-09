# r-ml-m3a-r3: R-ML review of M3a Separation, round 3

Verdict: **pass-with-fixes**. All five round-2 findings (F2, F3-R, N1, N2, N3) are fixed. One new major finding, a
recall collapse on 8th-note rides, and six minor ones. Full detail is in `docs/review/M3a-r-ml.md`, section "Round 3".

## How the fixes were checked

Every check ran the code:
- Review tests: the fast ones, and the real/slow ones on fresh ROCm runs under `out/_wip/r-ml-m3a-r3/pt/`. All five
  real tests pass:
  - synthetic song at 44.1 kHz: kick 1.000, snare .993, hat .926, tom 1.000, cymbal .800
  - synthetic song at 48 kHz: kick .994, snare .980, hat .917, tom .889, cymbal .714
  - mono and near-mono (side 24 dB under mid) excerpts: the split is flagged and dropped
- Two new separation variants, both above the gates (`out/_wip/r-ml-m3a-r3/variants/`):
  - -6 dB master: hat .910, cymbal .821
  - 0.5 s of leading silence (moves every chunk boundary): hat .916, cymbal .757
- `drums.core` on the W0 stems of newton-vs-nye, jeremy, megafauna and versatile.
- The new karaoke rules on the W0 lead and backing stems. They only flag there, because all four masters are wide.
- Sweeps on the generator's clean sub-stems:
  - soft passages from 0 to 24 dB down, in four windows
  - crash / ride level balance
  - hi-hat EQ: high-cuts of 6-25 dB and low-passes at 6-12 kHz
  - open hats darkened on their own
  - tom strokes removed from the toms stem, to exercise the classifier-only recovery

## Per finding
- **F2 fixed.** The fix uses one of the round-2 options: hat and cymbal vel is scaled by 0.45, with the raw value in
  `vel_raw`, and the fallback `drums:low_confidence(hat,cymbal)` is set. I checked it on the stage with
  `drums.path="classifier"`. Round 2 asked for the review test to follow the chosen fix, so
  `test_drums_classifier_path.py` now checks the PLAN gates on kick, snare and tom plus the scaling.
- **F3-R fixed.** The width is graded, a suspect split is flagged, the split is dropped on narrow masters, and
  `lead_share_frames` gives a per-second confidence.
- **N1 fixed.** The leak gates are relative to the kit's local level. Cymbal recall in a softened window does not move
  between 0 and 24 dB down.
- **N2 fixed.** The brightness threshold is relative to the stem's typical brightness. Darkened stems keep all open
  hats.
- **N3 fixed.** Ring plus classifier confirmation keeps ride and crash hits past the tight gate, and classifier-only toms
  are added. Four different separation outputs now pass the gates, but hat and cymbal have only 1-2 hits of margin.

## New major
- **R3-1:** ride / crash candidates need a broadband rise of `cymbal_rise_db` = 8 dB. A ride in 8th notes rises
  6.4-6.5 dB over the ring of the previous stroke:
  - Clean sub-stems at 140 or 150 bpm: about 95 % of the strokes are lost (recall .057 / .053).
  - At 120 bpm the rise is 8.2 dB, which clears the floor by 0.2 dB.
  - End to end on the real separation: ride recall .219, song cymbal F1 .385.
  - With a 4 dB floor, recall is 1.0 on the clean sub-stems.

  Failing test: `tests/review/M3a/r-ml/test_r3_drums_ride_eighths.py`.

## Minor findings (in docs/review/M3a-r-ml.md)
- r3-m1: duplicate drum events from `classify`; `(32.132, tom)` appears twice in the 48 kHz run.
- r3-m2: classifier-only toms (conf 0.5) get vel .74-1.0 on newton, above every DrumSep tom. The vel scales of the two
  sources are pooled.
- r3-m3: `detect()` has a threshold cliff near the -60 dBFS level window.
- r3-m4: open hats 10 dB darker than the closed hats are still relabelled as cymbals.
- r3-m5: hat F1 is exactly .900 when the hi-hat stem is band-limited at 10-12 kHz.
- r3-m6: the 3 dB `lead_suspect_db` fires on the stereo synthetic variant (2.7 dB) and on versatile.

## Files
- Tests: `tests/review/M3a/r-ml/test_r3_drums_ride_eighths.py` (new, fails) and
  `tests/review/M3a/r-ml/test_drums_classifier_path.py` (updated, passes).
- Review notes: `docs/review/M3a-r-ml.md`, section "Round 3".
- Probes and runs: `out/_wip/r-ml-m3a-r3/`.
