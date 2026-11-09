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
- probes done (probe_synth/extra/real.log): B1 FIXED (noise no crash; methods.skey voted:false p_max .092); M1 FIXED (white/pink/synth_noise conf .25 + no_tonal_evidence)
- real songs unchanged vs r2 (jeremy .836, megafauna .50, versatile .50, newton .902; synth_fx A minor .515) -> no regression
- review tests: 3 fast + 4 real all PASS
- minors for round 3: band-limited noise F minor .708 (S-KEY p_max .41 votes, nc 1.0) = m10 stronger; no non-N floor on chord source (fast.py: 1 spurious 2 s chord -> .882) but real lv gave nc 1.0 on all noise; template fallback on drums 41% chords; no unit tests for gate paths (m9 still open); vocals-only no-skey -> 'no_tonal_evidence' label
- gate running -> out/_wip/r-ml-m4-r3/gate.log
