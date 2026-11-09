# r-ml-m3a-r3 progress
- started round 3 review (fresh; no prior progress file)
- fast review tests: classifier_path FAILS (hat .793 / cym .444, unchanged; fixer chose vel x0.45), dark_hihat + soft_passage PASS
- real review tests running in bg: pytest -m real --basetemp=out/_wip/r-ml-m3a-r3/pt (log out/_wip/r-ml-m3a-r3/real_tests.log); first 4 pass
- probes in out/_wip/r-ml-m3a-r3/probe/: p_n1n2 (soft sweep: OK except detect() cliff when ride stem ~-50 dBFS, minor),
  p_gain (single-stem gain sweep), p_reallvl, p_real (real W0 stems counts), p_ridebal (ride ghost strokes -6 dB -> ride recall 0.56)
- command: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>
- real review tests: all 5 PASS on fresh ROCm runs (synth 44.1: tom 1.0 cym .80 hat .926; 48k: hat .917 tom .889 cym .714; mono + narrow flagged)
- N3 robustness variants (out/_wip/r-ml-m3a-r3/variants): -6 dB master PASS (hat .91, cym .821), 0.5 s pad PASS (hat .916, cym .757)
- F3-R: real W0 stems: megafauna lead-back -33 dB, versatile +2.5 -> suspect flag only (wide), no drop; OK
- F2: accepted chosen mitigation (vel x0.45, fallback); rewrote tests/review/M3a/r-ml/test_drums_classifier_path.py (passes)
- NEW major R3-1: 8th-note ride at 140/150 bpm loses ~95% strokes on clean stems (cymbal_rise_db=8);
  test tests/review/M3a/r-ml/test_r3_drums_ride_eighths.py FAILS (recall .057/.053); cymbal_rise_db=4 -> 1.0
- minors: duplicate classifier events (same sample, e.g. tom 32.132 x2 in 48k run); classifier_only toms vel 0.74-1.0 on newton
  (conf 0.5) above every DrumSep tom; detect() spread cliff at ~-50 dBFS ride; open hats >=10 dB darker than closed -> cymbal;
  lowpass 10-12 kHz hi-hat -> hat F1 0.900; tom vel corr with truth 0.41 on clean stems
- next: wait ride8 e2e (out/_wip/r-ml-m3a-r3/ride8.log), write docs/review Round 3, report
- ride8 e2e: ride recall .219, cymbal F1 .385; karaoke suspect flag fired (2.7 dB) -> minor r3-m6
- DONE: review doc Round 3 appended, report written (docs/build/reports/r-ml-m3a-r3.md)
