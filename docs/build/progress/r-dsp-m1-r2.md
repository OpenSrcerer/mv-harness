# r-dsp-m1-r2 progress (round 2 reviewer, M1 Signal, lens R-DSP)

## Done
- started; round-1 material: docs/build/progress/r-dsp-m1.md, docs/review/M1-r-dsp.md, tests/review/M1/r-dsp/.

## Next
- verify B1, M1, M2 fixes (read code, not just tests); look for regressions; new findings.

## Milestone 1 (fix verification, probes in out/_wip/r-dsp-m1-r2/)
- round-1 suite: 8 passed. M1 (kick gate) FIXED: piano/snare+hats 0 events at 0/-12/-20/-30 dBFS; quiet kicks keep R 1.0.
- B1 NOT fully fixed: kicks+bass+16th hats F1 0.721 (P 0.56), offbeat hats F1 0.854; kicks+16th hats no bass 0.846.
  Fixture song F1@10 0.88 (P 0.856 R 0.906): kicks with a hat 100 ms before are timed onto the hat (probe_fixture.py).
- regression: refractory 0.30 s drops kicks under a crash wash: 8ths@130 + crash R 0.828 (no refractory 1.0, viz 60/64).
- pre-existing: 16th kicks at 160 BPM (94 ms) -> 3-4 events of 96 (viz too); 140 BPM ok.
- real songs running: out/_wip/r-dsp-m1-r2/real.log

## Milestone 2 (tests written)
- tests/review/M1/r-dsp/test_rdsp_r2_kicks.py (+ helpers appended to rdsp_m1_support.py): 8 FAIL as intended
  (3 hats cases + fixture F1 0.88 = B1 reopened; crash 130/150 + Jeremy real (recall 0.733 vs 0.977 w/o refractory) = new
  refractory regression; 16th kicks @160 = 3/96 pre-existing).
- builder's own tests/unit/spectral::test_real_song_kick_counts (MVH_REAL_TESTS=1) now FAILS megafauna/versatile/jeremy
  (viz-flag 280/155/451 vs W0 refs 464/208/617).
- M2 fixed: drop hint at offsets 0.3..1.7 s and Versatile real (drop hints 51.72, 162.48). M1 fixed.
- real log: out/_wip/r-dsp-m1-r2/real.log; Jeremy kick-stem analysis real_strict.py / real_dropped.py.
## Next
- gate (background), minors (Round 2 section of docs/review/M1-r-dsp.md), report, StructuredOutput.

## Milestone 3
- report docs/build/reports/r-dsp-m1-r2.md and Round 2 minors (m13-m15) in docs/review/M1-r-dsp.md written; ruff clean.
- gate running: out/_wip/r-dsp-m1-r2/gate.log (unit step fails on rhythm stub test, other module). Then StructuredOutput.

## Done (final)
- gate: e2e PASS; unit/ruff/determinism FAIL from other modules; review FAIL = my round-2 tests (intended);
  M1 curves deterministic in-process (det.py). Report final. StructuredOutput returned.
