# w4fix-platform-r2: report (W4 fixer, platform group M6a/RUNTIME, round 2)

## Finding W4VP-1 (major): fixed
`finalize.build_manifest` listed only the outputs of stages current in the run, while pack_curves (round 1, W4D-1)
kept the curves of stale/pending/failed stages. Now, for every stage the run left stale, pending or failed,
build_manifest uses the same `_last_good` rule as pack_curves (last committed cache entry exists, stage still in
`_published.json`) and lists its published outputs that are still on disk, with their kind/events name taken from
that entry. One warning names the stages: `outputs and curves of stages not current in this run kept from their
previous run: ...` (moved from pack_curves; it now covers files and curves). No per-file marker (status.stages has
the status; token budget). CONTRACT D34 amended; decision W4-P6.

Real check (own copy of out/_wip/integrator/megafauna, rc.2, `mvh meaning` -> everything stale):
manifest.files 111 -> 111 (none lost), events 42 -> 42, `mvh validate` 119 files, 0 errors; lib (the verifier's
libcheck.mjs) eventNames 42, drum_hits 2412, counts 52, sections 17. The review test's assertion applied to the copy:
40 events files on disk, 42 listed: pass. kickSource on this copy is `mix` because the rc.2 folder has no
meta/drums.json and D79 says finalize writes `mix` then (the integrator manifest predates D79 and had no
kick_source, so the lib chose drums by its older-folder rule). Not caused by this fix; it disappears with the full
rc.3 re-run that writes meta/drums.json. Noted for the integrator: finalize (D79: mix) and lib (older folders: drums
when drum_hits is listed) disagree for pre-D79 folders.

## Minor findings fixed (same review file set)
- W4VP-2 a power-cut song.lock whose pid is reused blocked forever: `locks.pid_started` (Windows GetProcessTimes,
  Linux /proc) and `_song_lock_stale` treats a live pid whose process started > 2 s after the lock's `started` as
  stale. `test_w4vp_song_lock.py::test_power_cut_lock_with_a_reused_pid_does_not_block_forever` passes.
- W4VP-3 `mvh meaning` / `mvh frames` traceback on a busy folder: `cli.main` catches SongBusy for every verb -> one
  message, exit 75. Unit test with a genuinely held lock passes.
- W4VP-4 forced ingest without its input kept the "cached canonical audio is used" warning: the runner drops it when
  the stage must run and fails with the relink command. Review test passes.

## Left failing (test shown wrong)
`test_w4vp_song_lock.py::test_meaning_and_frames_report_a_busy_folder_cleanly[meaning|frames]` plants exactly the
same lock as the reused-pid test (started 2026-11-01, pid of a process started now) and requires it to be HELD (exit
75), while the reused-pid test requires that lock to be STALE (exit 0). Both cannot pass. With the W4VP-2 fix the lock
is cleared, meaning/frames run and exit 1 (upstream not cached in the 2-stage tone folder). The W4VP-3 behaviour
itself is fixed and covered by tests/unit/runner/test_w4_platform_r2.py::test_every_verb_reports_a_busy_folder_with_exit_75
(lock written after its live process started). Fix for the test: plant `started` = now (after the child started).

`test_w4vp_stale_manifest.py::test_real_megafauna_meaning_on_stale_folder_lists_its_events` reads the verifier's
folder out/_wip/w4verify-platform-r1/stale-megafauna, whose manifest was written by the old code; it is not my path
so it was not re-finalized. Re-running `mvh meaning out/_wip/w4verify-platform-r1/stale-megafauna` (seconds) makes it
pass, as shown on my own copy above.

## Files changed
- src/mvh/runner/finalize.py (build_manifest kept files, `_kept_curves`, warning moved from pack_curves)
- src/mvh/runner/locks.py (`pid_started`, `PID_REUSE_SLACK_S`, `_song_lock_stale`)
- src/mvh/runner/run.py (W4VP-4 warning drop)
- src/mvh/cli.py (SongBusy -> 75 in main)
- tests/unit/runner/test_w4_platform_r2.py (new, 7 tests); tests/unit/runner/test_w4_platform.py (held-lock test
  plants started=now)
- docs/CONTRACT.md D34, docs/RUNS.md §5, docs/contract/decisions/W4-platform.md (W4-P6..P9)

## Verification
- ruff src/mvh tests/unit/runner scripts: clean.
- pytest tests/unit/runner tests/unit/cli tests/unit/io tests/unit/contract: 157 passed.
- W4 review (verify-platform, platform, dogfood stale curves) + W4 unit tests + cli: 31 passed, 3 failed (the 3 explained above).
- gate W1b: running at report time, log out/_wip/w4fix-platform-r2/gate-W1b.log (unit steps passing so far).
