# w4fix-platform-r2 progress (W4 fixer round 2, platform group)

## Finding
- W4VP-1 build_manifest drops events/meta/audio files of stale/pending/failed stages
  (tests/review/W4/verify-platform/test_w4vp_stale_manifest.py)

## Done
- finalize.build_manifest: non-current stages with a _last_good entry list their published files that exist on disk;
  one warning "outputs and curves of stages not current in this run kept from their previous run: ..." (moved from
  pack_curves, which no longer warns itself).

## Next
- run review test + unit tests; real check on a stale MEGAFAUNA copy; CONTRACT D34 text + decisions doc; gate W1b/M6a.
- Also fixed minors W4VP-2 (locks.pid_started, reused pid = stale), W4VP-3 (cli.main catches SongBusy -> 75),
  W4VP-4 (run.py drops the cache-used warning when the stage must run and fails). Unit tests:
  tests/unit/runner/test_w4_platform_r2.py (7); r1 test lock planted with started=now.
- Review: stale_manifest synthetic PASS; real megafauna test reads the VERIFIER's folder (not re-finalized; not my path).
  Own copy out/_wip/w4fix-platform-r2/stale-megafauna after `mvh meaning`: files 111->111, events 42->42, validate 119
  files 0 errors, lib eventNames 42. kickSource mix (no meta/drums.json in rc.2 folder: D79 rule), not a regression of this fix.
- test_w4vp_song_lock meaning/frames: CONTRADICTS test 1 (same planted reused-pid lock must be stale there) -> left failing.
- Docs: RUNS.md §5, CONTRACT D34, decisions W4-P6..P9.
## Next
- full runner/cli unit suites + ruff; gates W1b (RUNTIME) and M6a.
- gate W1b running (log out/_wip/w4fix-platform-r2/gate-W1b.log); report written.
