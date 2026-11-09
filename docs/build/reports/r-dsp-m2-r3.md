# r-dsp-m2-r3: independent review, round 3 (M2 Rhythm, lens R-DSP)

Verdict: **fail**. F4-r2 is fixed for the fixture's (truth) rhythm only. Two majors remain, each with a failing test.

## F4-r2 re-check
- tests/review/M2/r-dsp all pass (19, including the real tests). M2 unit tests: 41 pass, 7 skipped.
- The fix is genuine and not a single-parameter hack. With the recorded real allin1, harmony and dynamics plus the
  fixture rhythm, F stays 1.0 and the choruses share group C across wide parameter ranges (out/_wip/r-dsp-m2-r3/p_sens.log).
- The fresh full `mvh analyze` of the synthetic song (out/_wip/r-dsp-m2-r3/synth) gives sections at
  0.99/5.0/9.0/17.0/25.0/34.5/50.52 s, F 0.923.
- p_full.py swaps the full run's inputs into the test harness one at a time. Only the real rhythm reproduces the
  failure: its beats F1 is 1.0, but the downbeats at 7.018 and 50.518 s are 18 ms late.

## Findings
- **F4-r3 (major).** The structure result flips on 1-2 frames of bar jitter.
  - **Cause:** `features.bar_pattern` slot edges sit on the 16th grid, so on the hits. A bar that starts one frame late
    has orthogonal patterns (cosine 0.0). The merge guard also has only a 3 % margin: score 2.34 against 2.41.
  - **Evidence:** a constant -10 ms shift splits the bridge (F 0.923).
  - **Test:** tests/review/M2/r-dsp/test_structure_rhythm_jitter.py (+ data/synth_real_rhythm.npz). 3 tests fail;
    the precondition and +10 ms tests pass.
- **F6-r3 (major, regression).** The MEGAFAUNA drop goes from 141.8-212.7 s to 141.8-176.1 s, against the SPIKE loud
  plateau of 146-217 s.
  - **Cause:** the new grouping puts 151.0 s in another group, so the merge no longer rejoins the 8-bar drop opening.
    The drop extent is measured from the drive of its first section, which is now hotter.
  - **Test:** tests/review/M2/r-dsp/test_structure_drop_extent_real.py (-m real, about 3 min). It fails with a cover of
    0.45, and still fails with the refinement off.
- **Minors r3-m1..m5** are in docs/review/M2-r-dsp.md "Round 3":
  - the refinement over-splits a uniform loop (6 -> 9 sections);
  - the dynamics gate saturates;
  - repeat groups mix roles, and a mid-song section is labelled outro;
  - the DSP fallback locks onto off-beat hats;
  - test coverage.

## Not changed or not checked
- Production code was not changed. The gate was not re-run; the fixer's gate2.log was used. Other modules' determinism
  failures were out of scope.
- Real-song replays (structure only; rhythm, choreo and cues sources are unchanged since round 2):
  - versatile 18 -> 18 sections;
  - jeremy 19 -> 19 sections (194.1 s verse -> chorus, no truth to judge);
  - newton 14 -> 14 sections;
  - megafauna 17 -> 18 sections (see F6-r3).
