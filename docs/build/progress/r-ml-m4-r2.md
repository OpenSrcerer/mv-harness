# r-ml-m4-r2 progress

## Done
- started round 2; read fixer/r1 progress
- Fixes present in code: F1 recover_probs + p_max gate (keys.py), F2 tuning*BPO/12 (chroma.py), F3 len(winners)<2 cap (keys.global_confidence)
- probe script out/_wip/r-ml-m4-r2/probe.py (args: synthetic | synthfx | <slug>); summ.py summarises logs
- NEW BLOCKER: KeyError 'skey' core.py:193 when song-level S-KEY p_max < 0.2 (white/pink noise, synth_noise) -> tests/review/M4/r-ml/test_skey_gate_crash.py (fast stub test FAILS as intended)
- zeros20/60 -> conf .25 + no_tonal_evidence (F3 fixed for silence)
- probe synth with synthetic beat grid: C major conf .968 (truth A minor) -> rerunning with fixture beats (probe_real.log)

## Commands
- Git Bash: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python ...  (no system python)
- r1 tests (4) PASS after fix (out/_wip/r-ml-m4-r2/review_tests.log); fixes verified in code, not test hacks
- real songs unchanged vs r1 (probe_real.log); synth w/ fixture beats A minor .515 as before
- per-window S-KEY p_max real songs (probe_pmax.log): no real song hits the crash (min song mean .366 megafauna)
- MAJOR F3 reopened: white noise skey-absent/gated -> D minor .609 flags [] (3 profile methods counted as independent) -> test_key_gating_noise.py FAILS
- real white-noise crash test FAILS with KeyError (verified)
- next: append Round 2 to docs/review/M4-r-ml.md (minors), write report, StructuredOutput
- DONE: minors m8-m11 appended to docs/review/M4-r-ml.md; report docs/build/reports/r-ml-m4-r2.md. Only StructuredOutput remains.
