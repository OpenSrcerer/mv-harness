# r-contract-m6b-r3 progress (round 3 review of M6b)
## Done
- started
## Next
- run review tests; verify R2-1..R2-6, N1..N6 fixes are real; hunt regressions
- 123 pass / 12 skip on tests/review/M6b + unit meaning/brief/frames
- probes out/_wip/r-contract-m6b-r3/p1-p3.py; run_scen.py <fixture> <name> <intent|none> <authored|none>
- candidate findings: (a) draft perspective has no field_sources (status user); (b) template palette hint '[#1b2a49]' unquoted -> YAML ParserError -> all answers lost;
  unfenced fallback reads template comments as user claims (palette #1b2a49, line_singers L005=C1+C2) => R2-2/N3 reopen;
  (c) do-not label block swallows following bullets (chars/section notes) after blank line; (d) heading with never/don't anywhere (song-title H1) -> whole body = do_not
- gate started in background -> out/_wip/r-contract-m6b-r3/gate.log
- tests written + verified failing (9 fail for stated reasons): tests/review/M6b/r-contract/test_r3_intent_parsing.py (R3-1..R3-4),
  test_r3_perspective_source.py (R3-5)
- next: check skipped tests, gate result, frames e2e (R2-6), minors -> docs/review/M6b-r-contract.md Round 3, report
- minors appended to docs/review/M6b-r-contract.md "Round 3"
- waiting on gate (background); then frames e2e if possible; then report
- gate: review/contract/validate/e2e/lib-node PASS; unit FAIL contract only (not M6b); ruff transient (clean on rerun); determinism FAIL (upstream)
- frames e2e: analyze running in background -> out/_wip/r-contract-m6b-r3/e2e/synth
- R2-6 verified e2e (frames rc=1 not_run when separate_hq stale due to another module's param change)
- report written docs/build/reports/r-contract-m6b-r3.md; waiting for re-analyze + frames export (background) to check CSV
- RESUMED after power outage (02:45): review tests unchanged (9 r-contract r3 fails as stated); analyze2 had died mid-lyrics;
  started `mvh frames e2e/synth --fps 24 --fps 24000/1001 --frame0 1` in background -> e2e/frames3.log
