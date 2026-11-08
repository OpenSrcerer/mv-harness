# r-ml-m4-r3 progress

## Done
- started round 3 (verify B1, M1 from r2; look for regressions)

## Next
- read keys.py / core.py fixes; run r1/r2 review tests; probe noise + real songs
- B1 fix in code: core.analyse_key uses methods.setdefault("skey", ...) + voted flag (real, not test hack)
- M1 fix in code: keys.global_confidence counts ks/temperley/albrecht as one "profiles" source; <2 sources -> conf<=0.25 + no_tonal_evidence
- all fast review + unit tests pass (57)
- fast.py: white noise + ONE spurious 2 s lv chord agreeing with profiles -> conf 0.882 no flags (no non-N-share floor) -> candidate major
- probes running in background: out/_wip/r-ml-m4-r3/probe_{synth,extra,real}.log (probe.py synthetic synthfx | extra | slugs)

## Commands
- Git Bash: export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python ...
- summary: python out/_wip/r-ml-m4-r2/summ.py <log>
