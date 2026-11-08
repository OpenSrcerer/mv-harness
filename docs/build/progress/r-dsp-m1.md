# r-dsp-m1 progress (independent reviewer, M1 Signal, lens R-DSP)

## Done
- read PLAN/SPIKE/CONTRACT/audio.js and all M1 code; M1 unit tests pass (60 passed, 12 skipped real).
- synth fixture run (out/_wip/r-dsp-m1/run_synth.py): kick F1@10ms 0.693 (P 0.55, R 0.93); loudness matches truth.
- isolated: kicks + sustained bass note per bar -> F1 0.54 (P 0.37): weak-hit path emits a 2nd kick 40-160 ms after
  each kick (kick_conf evaluated inside the previous kick's decay reads 1.0). viz itself (Node, real audio.js) ~55 hits.
- built real causal viz reference: tests/review/M1/r-dsp/viz_causal.cjs + rdsp_m1_support.py (analyser_frames).
  Offline viz curves corr 0.99 vs real viz @100 fps; onset counts match viz@100fps (viz is fps-dependent).
- EBU: 3341 #5/#9/#12 and 3342 #4 pass. True peak (own 4x Kaiser) reads -5.62/-5.32 dBTP on 3341 #17/#18 (exp -6.0,
  tol +0.2); ffmpeg -6.0/-5.9. Edge Gibbs ringing on abrupt starts (minor).
- dynamics on synth: impacts miss 17.0 (chorus), FPs at 5.0/9.0/29.0; build 25-32.5 not separated, false build hint 5-9 s.

## Next
- real songs (background: out/_wip/r-dsp-m1/real.log), edge cases via mvh analyze, write failing tests, report.

## Commands
- Git Bash: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>
- scripts need sys.path.insert(0, repo) (mvh-env resets PYTHONPATH)

## Milestone 2 (tests written)
- tests/review/M1/r-dsp/: conftest.py, rdsp_m1_support.py, viz_causal.cjs, test_rdsp_kick_events.py (5 FAIL as intended),
  test_rdsp_dynamics.py (offset 0.9 FAIL, 0.0 pass), test_rdsp_viz_parity.py (PASS guard). ruff clean.
- real songs (out/_wip/r-dsp-m1/real.log): loudness within 0.08 LU of ffmpeg; Versatile main drop 50.96 s snapped to
  51.72 and hinted 'build' (role_hints 0.6 s tolerance < half-bar snap); MEGAFAUNA drops found (96.1, 141.6).
  Versatile kick events 350 vs viz 212-227 hits.
- kick-free material: piano 37 / snare+hats 18 kick events (quiet-master gate); PLAN gate gives 0.
- edge: dynamics crashes on <= 2 s input (minor). CLI edge cases (mono, 48k, mp3, corrupt, 10 s, unicode) run.
- gate M1 running (out/_wip/r-dsp-m1/gate1.log); ruff fails on other modules' tests (M3b), not M1.

## Next
- docs/review/M1-r-dsp.md (minors), report docs/build/reports/r-dsp-m1.md, StructuredOutput.

## Milestone 3
- docs/review/M1-r-dsp.md and docs/build/reports/r-dsp-m1.md written; review suite: 6 failed (intended), 2 passed.
- waiting for gate e2e/determinism (gate1.log) to fill the report's Gate section, then StructuredOutput.
