# r-ml-m3a-r5 progress (R-ML reviewer, M3a, round 5 / W3 verify)

## Done
- started; read r4 progress

## Next
- read fixer-m3a-r4 progress (locate changes only); verify R4-1, R4-1b, R4-2; regressions; tests/integration/M3a; real reruns
- launched out/_wip/r-ml-m3a-r5/run_det.sh (newton detA normal, detB with GPU hog 0.8) -> run_det.log
- fast review+unit tests: 66 pass, R4-2 test fails (compares STALE integrator vs r4 folders, both old code: cannot pass; need new-run comparison)
- det3 vs det4 (fixer, newton) all identical; fixer real newton vs integrator: vocals -133 dB, drums -131 dB, lead -76 dB (karaoke amplifies) -> quality same
- probe/p_coinc.py: coinc rule drops megafauna 5 ride hits (rise 11.5-23.8, decay 10.8-19.4) while megafauna kept non-coincident rides decay >9 dB 88% (median 17.4) -> rule is synth-tuned; jeremy 3, versatile 1; investigating if real rides
- queued run_synth.sh (synth44/synth48 analyze into r5 wip, then real review tests -> real_tests.log)
- R5-1 (major candidate): coinc_decay rule (R4-3) drops kick-only-coincident real rides (megafauna 4, jeremy 2); synth drops all snare-coincident (truth snare). test tests/review/M3a/r-ml/test_r5_drums_coinc_kick_rides.py FAILS megafauna+jeremy, passes synth/versatile (criterion sanity)
- detA done 11:40 (rc 0, 9 min); detB (hog) started 11:40
- R4-2 VERIFIED FIXED: detA vs detB (hog 12.6 GiB of 15.8 + matmul churn) all stems/drum_hits/stems.json/curves identical; detA == fixer det3 (1 h earlier) stems identical. separate_hq 534/540 s.
- updated test_r4_hq_vocals_determinism.py to compare current-code runs r5 detA/detB (old pair was 2 old-code runs: could never pass)
- queued run_vers.sh (versatile module rerun after synth)
- R4-1 VERIFIED: jeremy cymbals ride 139->163 (grid .79), crash 25->22 (artefacts filtered); megafauna ride 35->31 (R5-1 coinc drops)
- synth44 F1 k1 s.993 h.929 t1 c.895; synth48 k.994 s.98 h.921 t.889 c.737 (gate ok, margin ~1 hit); synth48 coinc drops all snare-coincident (truth snare) -> snare-only rule keeps gate; R5-1 test passes on synth48
- separate_hq newton 534 s (integrator 552 s): no time regression from math SDPA
- next: wait real_tests.log + versatile rerun; write review doc Round 5, report
- review doc Round 5 written (R5-1 major, r5-m1..m3)
- real review tests (synth44/48 reuse): 5 passed
- report draft written; waiting versatile rerun to fill in
- versatile rerun rc 0, counts = integrator (hat -1); diff vs fixer 09:11 run explained by later rocBLAS fix. DONE: report final
