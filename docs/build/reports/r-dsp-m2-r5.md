# r-dsp-m2-r5: independent review of M2 Rhythm, lens R-DSP, round 5 (W3 verify)

## Verdict
pass-with-fixes. F7-r4 is fixed for Jeremy, and the fix is a general rule, not a hack written for the test. The rule it
introduces has one new major, F8-r5.

## F7-r4 re-check: FIXED
- `structure.phrase_layout` now places a section's phrase remainder first (as a pickup) when the other section starts sit
  on the grid through `start + remainder`.
- Jeremy verse#1 is phrased P02 19.47 s (1 bar) + P03 21.80 s (8 bars). The eight-counts are:
  - E005 at 19.47 s, a 4-beat partial;
  - then 21.80, 26.37, 30.96 and 35.56 s, which is the pre-snap grid.

  No partial count dangles before the chorus. The cues are a tier-1 section cue at 19.47 s and a tier-2 phrase cue at
  21.80 s.
- tests/review/M2/r-dsp/test_structure_impact_snap_counts_real.py (`-m real`): passes.
- r4-m2 is fixed too: structure StageSpec is now 1.1.0.

## Runs
**Real songs.** I re-ran structure, choreo and cues with the current code on the integrator's real caches:
- songs: jeremy, megafauna, versatile, newton-vs-nye and synth;
- output: out/_wip/r-dsp-m2-r5/real/<slug>{,_det};
- probe: probes/runreal.py.

Results (probes/cmp.py):
- Byte-identical to fixer-m2-r4's re-run.
- Deterministic across two runs.
- No regression on the other songs.

**Tests.**

| tests | result |
|---|---|
| review M2/r-dsp + M2 unit tests | 75 passed, 13 skipped |
| `-m real` | 6 passed |
| tests/integration/M2 | 2 fail |

The 2 integration failures come only from stale integrator outputs (05:10, before the r3 fix). My re-run satisfies both
checks:
- S05: the section start at 19.466 s is on the impact.
- S09: the synthetic intro is one 'intro' section.

## New major F8-r5: the phrase grid depends on sections elsewhere in the song
**Where.** `src/mvh/stages/structure/__init__.py` `phrase_layout`.

**Cause.** Where a remainder goes is decided by a global vote of all other section starts:
- Starts after the section vote for "pickup".
- Starts before it vote for "trailing".
- The song start is excluded.

**Evidence: a late edit re-grids the bridge.** On the synthetic song, one `structure.boundaries` add at 42.5 s splits
the final chorus at its truth phrase boundary. That one edit flips the bridge (25.0 s, 5 bars, truth 4 + 1) to 1 + 4.

| | bridge eight-counts |
|---|---|
| truth, and the default run | 25.0/8, 29.0/7p, 32.5/4p |
| after the 42.5 s edit | 25.0/4p, 27.0/8, 31.0/7p |

**Evidence: the same layout gets opposite answers by position.** A first verse with a trailing stop bar has the same
sec_ranges as Jeremy's snapped verse, and it is always given a pickup. The same trailing bar late in the song is
phrased with the remainder at the end (probes/p_layout.py).

**Test.** tests/review/M2/r-dsp/test_phrase_grid_nonlocal.py. It is fast and synthetic: the edit-only test fails for
the stated reason and the precondition passes.

**Suggested fix:**
- Use local evidence.
- Keep the original boundary as the phrase anchor when the impact snap moved this start (the snap knows).
- Otherwise compare the music at `a + r` and at `b - r`: novelty, a stop/silent/no-pulse or 3/4 bar at the end, a vocal
  entry.
- Never let a section's grid change because of the count of sections elsewhere.

## Minors
In docs/review/M2-r-dsp.md, Round 5:
- r5-m1: the positional bias in detail.
- r5-m2: an odd pickup of 3 or more bars still leaves a partial count before the main phrase. choreo cuts phrases
  forward from their start.
- r5-m3: with the snap disabled, Jeremy's 9-bar intro gets a pickup at the song start.
- r5-m4: the pickup count is numbered 1-4. CONTRACT D13 allows `first_count` 5 only for E000.
