# r-ml-m4-r3 progress

## Done
- B1 verified FIXED (core.analyse_key setdefault skey + voted; real noise no crash, p_max .092 voted false)
- M1 verified FIXED for named cases (profiles counted as one source; white/pink/synth_noise conf .25 + no_tonal_evidence)
- real songs unchanged vs r2 -> no regression; fast suite 57 pass
- NEW major: band-limited noise, lv 100% N, S-KEY p_max .41 votes -> F minor .79-.80 no low flag.
  test: tests/review/M4/r-ml/test_key_gating_band_noise.py (stub + real) FAILS as stated
- minors m12, m13, m9(open) appended to docs/review/M4-r-ml.md Round 3
- gate stops at tests/unit/contract stub test (rhythm no longer stub; not M4)
- report written: docs/build/reports/r-ml-m4-r3.md

## Next
- nothing; finished

## Commands
- Git Bash: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q <path> -p no:cacheprovider
