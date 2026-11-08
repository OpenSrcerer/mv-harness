# r-contract-m6b-r2 progress (round 2 review of M6b)

## Done
- started; read fixer-m6b progress and round-1 review doc

## Next
- verify round-1 findings (r-contract F1-F3, r-words F1-F6) are really fixed
- hunt new blockers/majors (regressions)

## Commands
- all 100 M6b unit+review tests pass (8.5 s)
- probes in out/_wip/r-contract-m6b-r2/probe1-5.py, run_scen.py, recipes_all.mjs
- F1 (recipes include) fixed (remotion recipe runs in URL mode). Loading list still lacks events:sections for meaningAt (minor m7 stays).
- F5 fixed (warnings carry no values; kind_of is fullmatch).
- REOPEN F4: untouched template still flips status to user when voices absent (template writes voices: [V1] from vhow default 'user')
  and on instrumental songs (template prefill lead_backing: lead). probe1/probe2.
- REOPEN F3 (partial): template after a heading/story, unclosed fence, or prose after it -> free-text fallback: do_not dropped,
  C1 name '{name', S05 feel = YAML comment (warning now emitted). probe4.
- NEW: draft-filled character name/description shown as user (characters have no field_sources; brief no label). probe5.
- F2 code path: RECIPES still says only provenance.status==='draft' marks agent text; meaningAt has no field_sources.
- gate M6b started in background -> out/_wip/r-contract-m6b-r2/gate.log

## Commands
- MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python out/_wip/r-contract-m6b-r2/probeN.py
- run_scen.py <fixture> <name> <intent|-> <authored|-> -> out/_wip/r-contract-m6b-r2/runs/<name>/
- tests written + verified failing (10 failed for stated reasons, round-1 tests pass):
  tests/review/M6b/r-contract/rc2_support.py, test_r2_untouched_template.py (R2-1), test_r2_template_in_context.py (R2-2, R2-3),
  test_r2_draft_characters_and_recipes.py (R2-4, R2-5)
- note: r-words-m6b-r2 reviewer independently found overlapping N1-N6 (tests/review/M6b/r-words/test_rw2_*.py)
- next: gate result; frames CLI stale-upstream probe; minor list -> docs/review/M6b-r-contract.md Round 2; report
- R2-6 frames CLI exit 0 when stage not run but old export exists: test_r2_frames_cli_not_run.py (fails as expected)
- minors appended to docs/review/M6b-r-contract.md "Round 2"
- gate: unit FAIL only test_stub_files_are_stubs (not M6b); e2e blocked by M1 spectral TypeError
- report written: docs/build/reports/r-contract-m6b-r2.md; DONE (StructuredOutput returned)
