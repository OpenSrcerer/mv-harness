# r-dsp-m2-r2 progress (independent reviewer round 2, M2 Rhythm, lens R-DSP)

## Done
- started; read round-1 review (docs/review/M2-r-dsp.md), fixer report.

## Next
- run tests/review/M2/r-dsp (incl -m real), inspect each fix for genuineness, probe regressions.

## Commands that worked
- Git Bash: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>
- 23:55 review tests all pass (14 incl. real); M2 unit tests 39 pass. Code-read F1-F5 fixes: F1 genuine (pin leads merged cue),
  F2 smooth_same == np.convolve same (verified) but tempogram_peaks still crashes for non-silent input < 0.68 s (ac length) -> minor,
  F3 segment_dp short-first path removed, F5 phase-shift correction self-reinforcing (rotates trackers to first-pass decode) -> check.
- Probes: out/_wip/r-dsp-m2-r2/probes/{replay.py, replay_all.sh, p_edge2.py, p_struct_a1.py, cmp_sections.py, cmp_meter.py}
- Background: replay_all.log (4 songs), synth rerun (copy of r1 synth, --from rhythm) -> synth.log
- Observed: versatile r2 labels 29.5 s and 144 s 'outro' (group with real outro) -> minor label plausibility.
- 00:10 synth full rerun (--from rhythm) done: rhythm still F1 1.0 / downbeat 1.0; structure F 0.615 (1.0/5.0/9.0/25/34.5/42.5/52.5),
  chorus#1 missed -> F4 NOT fixed in the real pipeline. Cause: fixture dynamics segments == truth sections (2nd circular input),
  and real harmony chroma alone already breaks it (F 0.909). New failing test tests/review/M2/r-dsp/test_structure_real_upstream.py
  (+ data/synth_real_harmony_dynamics.npz); 4 fail / 1 pass (circularity demo). Fixture md5 unchanged.
- Real-song replays r2 vs r1: versatile 3/4 bar gone (F5 fixed); other songs' meter unchanged; jeremy/megafauna 1-bar S01 now
  absorbed into a 9-bar intro, 1-bar phrase moved to the END of the intro (counts shift one bar) -> minor; newton loses both
  allin1 choruses into verse group B, versatile 'outro' at 29.5 s -> minor (over-grouping by max(main, melody) sim).
- Gate M2 running in background -> out/_wip/r-dsp-m2-r2/gate.log
## Next
- minors -> docs/review/M2-r-dsp.md Round 2; report docs/build/reports/r-dsp-m2-r2.md; StructuredOutput.
- DONE: minors appended (docs/review/M2-r-dsp.md Round 2), report written (docs/build/reports/r-dsp-m2-r2.md). Gate: e2e PASS,
  review fails only on the new test. Remaining: return StructuredOutput.
