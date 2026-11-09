# r-dsp-m2-r4 progress (independent reviewer round 4, M2 Rhythm, lens R-DSP, W3 verify)

## Done
- started fresh (no prior r4 progress). Targets: verify F4-r3 (jitter), F6-r3 (megafauna drop extent), S05 (jeremy impact in intro), S09 (synth intro labels).

## Next
- run tests/review/M2/r-dsp + tests/integration/M2, read structure changes, rerun synth + 2 real songs.
- synth via integrator upstream (runreal.py): F 1.0, labels intro/verse/chorus/bridge/chorus/outro (S09 synth fixed). const jitter -40..+40 ms: F 1.0 all (p_jit2_const.log). real 4 songs rerun -> out/_wip/r-dsp-m2-r4/real/<slug>; jeremy verse at 19.5 (S05 ok), megafauna drop 141.8-212.7 (F6 ok), versatile new drop 51.7 (+build 44.3; SPIKE says drop 47.5 -> plausible).
- random per-bar jitter +-20/+-30 ms (12 seeds): F 1.0 all -> F4-r3 FIXED (p_jit2_rand.log). F6-r3 fixed (megafauna drop 141.8-212.7).
- impact snap (S05 fix) fires only on jeremy (diff vs impact_snap_strength=0). S05 integration test fails only because
  integrator outputs are stale (pre-fix); my rerun has verse#1 at 19.47.
- CANDIDATE MAJOR (regression of S05 fix): jeremy verse#1 is now 9 bars (19.47-40.13); phrases 8+1 with the 1-bar remainder
  at the END (P03 37.86) -> eight-counts E005-E008 start on bar 9 (band entry), E009 is a 4-beat partial before chorus.
  Song hypermeter (all other sections 8/4 bars from 21.80) puts count 1 on bar 10 -> verse#1 counts off by 4 counts.
- NEXT: write tests/review/M2/r-dsp/test_structure_impact_snap_counts_real.py (real), then other probes.
- WROTE tests/review/M2/r-dsp/test_structure_impact_snap_counts_real.py (real): 2 fail (grid moved 21.80->24.10..; partial E009 4 beats before chorus), precondition passes. => F7-r4 major.
- minors appended (Round 4: r4-m1..m4 + r3 recheck). p_loop rerun: r3-m1 fixed; r3-m4 still open.
- NEXT: report docs/build/reports/r-dsp-m2-r4.md, StructuredOutput.
- report written (docs/build/reports/r-dsp-m2-r4.md). DONE except StructuredOutput.
