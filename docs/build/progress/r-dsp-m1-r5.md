# r-dsp-m1-r5 progress (round 5 / W3 verify reviewer, M1 Signal, lens R-DSP)

## Done
- started 2026-11-09; no prior progress file.

## Next
- run review suite M1 + unit spectral/loudness/dynamics (bg, log out/_wip/r-dsp-m1-r5/suite.log)
- read dsp.py kick code; verify R4-M1/M2/M3 fixed for real (variants beyond the tests)
- probe regressions; integration tests M1; rerun 2 real songs
- probes out/_wip/r-dsp-m1-r5/probe_vars.py {bass,duck,quiet} -> vars_*.log. Findings so far:
  R4-M1 NOT fixed beyond the test point: tr808 bass .5 F1 .809 @100 BPM, .567 @140 (passes .968 only @120); acoustic bass .7 F1 .83 (R .71), bass 1.0 .55
  R4-M2: duck tr808 (clickless) R .02 at bass .7; fixture/909 bass 1.4 F1 .80/.75. MEGAFAUNA strong kicks still .22 per fixer report.
  R4-M3: -14/-20 ok for fixture/909; -26 dB intro 0/16 for all designs (cause TBD: gate vs quiet_conf); acoustic+bass -20: R .75; tr808 -20 no bass R .75
- suite (review M1 + unit M1): 117 pass, 12 skip, 1 xfail (3m42). R4 tests all pass now.
- -26 dB intro: kicks conf 1.0 but viz kick gate (abs -46 dB) = 0.07 -> minor (gate tied to viz absolute gate).
- dbg.py <case> prints evidence per truth kick. tr808 misses: glide 1.04-1.12 (<1.2 808 route), f1 61-65 (<68 body), conf .64-.69.
- MEGAFAUNA (fixer out, same code): strong recall .22; at misses mix attack med 2, click 1, low_ex .4 (mega_ev.py). M1-S13 revised -> drum_hits rows.
- rerun megafauna+jeremy running (rerun.ps1, bg) into out/_wip/r-dsp-m1-r5/<slug>
- my megafauna hits.kick == fixer's (byte-identical). kick_prec.py: MEGAFAUNA 188 hits.kick, only 36 strong + ~36 kick-stem; ~116 snare/toms/bass/other/none (kick_conf p50 .74)
- NEW regression candidate: 'click' route (fixer-m1-r4) fires on kick-free textures: pluck bass 8ths + hats 50 false (38 click, 12 sweep), low piano 21/48 (all click), snare+bass onsets 7/24 (click). probe_fp.py, fp_routes.py
- real-song route counts (manifest hits.kick.routes): duck 1 / click 3 on MEGAFAUNA, 0 on jeremy -> new routes inert on real mixes.
- probe_bed.py: + quiet bright lead chord (peak .1 vs kick .9): duck 909 R .04, duck fixture R .67, acoustic held bass R .58; fixture held bass 1.0 (sweep robust).
  => click>=15 dB (duck/click routes) only reachable in sparse synthetic mixes. Re-raise R4-M1, R4-M2; new regression click-route FPs.
- Next: write tests/review/M1/r-dsp/test_rdsp_r5_kicks.py; check dynamics/loudness on reruns; S06 test.
- Milestone: tests/review/M1/r-dsp/test_rdsp_r5_kicks.py (+ rdsp_r5_signals.py): 9 FAIL as intended (tr808 100/140, acoustic bass .7,
  acoustic+bed, duck 909/fixture+bed, kick-free pluck_hats/piano_low/snare_bass). ruff clean.
- rerun megafauna+jeremy done (out/_wip/r-dsp-m1-r5/<slug>), megafauna hits.kick identical to fixer's.
- Next: dynamics/loudness check on reruns; integration test M1; minors; report.
- R4-M3 half fixed: quiet_conf 0.7 (song-global body ref) drops 808/click-route kicks in quiet intros (tr808 -20 R .75, acoustic+bass -14 R .875; quiet_conf=0 -> 1.0). Test added (2 FAIL). probe_quiet3.py
- dynamics rerun == fixer's (megafauna 12 parts, drops 96.1/141.8; jeremy 13 parts, breakdown hints 288.1/306.4 score 1.0 on the outro fade -> minor m26)
- integration M1 (S06) still fails on integrator's pre-fix folder (0.42).
- Next: Round 5 minors in docs/review/M1-r-dsp.md, report, StructuredOutput.
- DONE: report docs/build/reports/r-dsp-m1-r5.md, Round 5 minors (m25-m28) in docs/review/M1-r-dsp.md; 11 failing tests in test_rdsp_r5_kicks.py. Only StructuredOutput left.
