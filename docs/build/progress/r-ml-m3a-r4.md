# r-ml-m3a-r4 progress (R-ML reviewer, M3a, round 4 / W3 verify)

## Done
- started; read r3 progress

## Next
- verify R3-1 fix (drums ride eighths); look for regressions; check tests/integration/M3a; rerun on 2 real songs

## Commands / gotchas
- fast review tests: 6 pass (R3-1 ride test passes; fixer set cymbal_rise_db 8->4)
- R3-1 e2e on r3's separated ride8 stems (copied to out/_wip/r-ml-m3a-r4/variants/synth_ride8; drums core re-run via probe/p_ride8_core.py): ride recall .812, cymbal F1 .806 -> fixed on synth
- REGRESSION candidate: fixer's real reruns (out/_wip/fixer-m3a-r3/<slug>) add cymbals mostly from CRASH stem, at chance 16th-grid alignment
  (jeremy added crash 81 on16th .16 vs chance .28; kept ride .80; added ride .69 = real). probes p_grid.py, p_added.py, p_attack.py
- command: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>
- R4-1 (major, regression of R3-1 fix): crash-stem low-rise hits are not events in DrumSep input (jeremy .06, megafauna .07 HF-rise; random .09-.13);
  test tests/review/M3a/r-ml/test_r4_drums_crash_floor.py FAILS (jeremy .27, megafauna .10 vs >= .5), 24 s
- D47 CPU DrumSep vs W0 ROCm newton sub-stems: residual -92..-139 dB (wav); equivalent. OK
- probe bug lesson: 1 ms blocks are round(sr/1000)=44 samples: index = int(t*sr)//44, not int(t*1000)
- launched bg out/_wip/r-ml-m3a-r4/run_real.sh -> run_real.log (real review tests, then module rerun newton+versatile into out/_wip/r-ml-m3a-r4/real/<slug>)
- synth (integrator stems): 4 dB adds 2 FPs: ride 30.875 (snare leak rise 5.7), crash 42.54 (40 ms after true crash, tail bump rise 4.5); 23 vs 20 truth
- added crash artefacts: conf med .81/.84, vel med .46; classifier cymbal hits jeremy 1002 (non-specific confirmation; 24/81 agree)
- 48k synth (r3 ROCm stems, core re-run): cymbal F1 .714 (8 dB) -> .596 (4 dB) BELOW gate; 44.1k .800->.791; -6dB .821->.791
- 48k new FPs at 4 dB: 22.543/24.01/42.543/52.55 = cymbal tail bumps 40-50 ms after a true stroke (rise 4-6), 30.875 snare leak, 34.786 open-hat copy
- FRESH e2e (current code, CPU drumsep): synth 44.1 k1.0 s.993 h.926 t1.0 c.791; 48k k.994 s.98 h.915 t.889 c.596 (<.7 gate; r3 .714) -> existing test_r2_drums_separated_synth_48k regresses
- real review tests (bg): 4 pass, test_r2_drums_separated_synth_48k FAILS cymbal .596 (regression by R3-1 fix). now module rerun newton (06:53) then versatile
- review doc Round 4 status + R4-1 written; minors next
- minors r4-m1..m3 written
- newton module rerun rc 0: drums 14->31 cymbals (as fixer). SW stems + CPU DrumSep byte-identical vs integrator, BUT Mel vocals differ (max 4e-7, 87%), lead -75 dB, backing -52 dB
  -> R4-2 (major): D47 claim "RoFormer bit-identical" false; test tests/review/M3a/r-ml/test_r4_hq_vocals_determinism.py (compares integrator vs my rerun)
- review doc: R4-2 section added. waiting versatile rerun (bg) then compare + run R4-2 test, then report
- versatile module rerun rc 0: all stems byte-identical (R4-2 intermittent); cymbal 24->32, hats 659->658; R4-2 test: newton FAIL, versatile pass
- next: write report docs/build/reports/r-ml-m3a-r4.md, StructuredOutput
- DONE: report written
