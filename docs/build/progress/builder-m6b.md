# builder-m6b progress (M6b: meaning, brief, frames, skill/)

## Done (all milestones)
- meaning, brief, frames stages (+ cli verbs), skill/mv-harness (SKILL.md, references/{CONTRACT.md, RECIPES.md},
  scripts/sync_contract.py), tests/unit/{meaning,brief,frames} (82 + 12 real, all pass), decisions doc
  docs/contract/decisions/M6b.md, report docs/build/reports/builder-m6b.md.
- intent parser reads the M6a viewer-managed block (round-trip tested against mvh.stages.viewer.intent_block).
- gate M6b: my tests PASS; blocked by tests/unit/contract stub test (rhythm no longer a stub), ruff in other modules,
  e2e dynamics failure (M1). Logs: out/_wip/builder-m6b/gate1.log (full), gate2.log (-SkipE2E).

## Next (if resumed)
- Re-run `scripts\gate.ps1 M6b` after M1/contract fixes; then try `mvh frames`/`mvh meaning` on the e2e folder (-KeepTemp).

## Commands that work
- Git Bash: `export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <script>`
- in-process runs: `from mvh.stages.meaning.devrun import DevRun; dr = DevRun(fixture, work); dr.run("meaning"); dr.run("brief")`
- real tests: `MVH_REAL_TESTS=1 ... python -m pytest -q tests/unit/<stage>`

## Gotchas
- real-* fixtures lack mood/cues/instruments/choreo/voices(except newton): stages degrade gracefully.
- CLAIM_PROV.status is user|draft only: harness-derived facts are labelled source=audio, status=draft.
- conventions.singer_at needs a mouth_open callable.
- JSON args through powershell lose quotes: pass params via a file. Never `cat > file` without a heredoc (hangs).
- Edit tool trims trailing spaces of new_string: check regexes after edits.

## Resume 2 (2026-11-08, after the usage-limit restart)
- Re-ran gate -SkipE2E (gate3.log): unit FAIL only on tests/unit/contract stub test (CR-1); review FAIL = 15 reviewer tests
  (R-CONTRACT F1-F3, R-WORDS F1-F6) that the fixer round owns; ruff FAIL only tests/unit/vocals/test_m3b_real.py (M3b).
- Fixed E501 in skill/mv-harness/scripts/sync_contract.py; contract copy --check OK; 94/94 incl. real tests pass.
- Full gate with e2e running in background -> out/_wip/builder-m6b/gate4.log (-KeepTemp).
- gate4: unit FAIL (CR-1 only), review FAIL (15 reviewer tests, fixer round), ruff PASS, contract PASS, validate PASS,
  **e2e PASS (3205 s)**, lib-node PASS; determinism running.
- e2e folder (copied mid-determinism -> out/_wip/builder-m6b/e2e-synth, stale cache): brief 1297 tokens, zoom S03 441,
  0 untraceable decimals. Found: `mvh frames`/`mvh meaning` exited 0 silently when --only could not run (stale upstream);
  fixed: both now print the reason (`not_run`) and exit 1; test tests/unit/frames/test_frames_cli.py (2 tests).
- Next: after determinism, clean copy of the e2e folder -> run mvh frames (24, 24000/1001 frame0 1), mvh meaning, validate.
- gate4 final: determinism FAIL (44 files, starts at drumsep stems; CR-7). Folder went stale twice (M1/M2 param edits) so a
  clean `mvh frames` CLI run was impossible; ran meaning/brief/frames via DevRun on the e2e folder instead (all ok, 0 NaN).
- Report updated (Gate section, CR-7, CR-8). Build step DONE; remaining failures belong to CR-1 / the fix round / M3a.
