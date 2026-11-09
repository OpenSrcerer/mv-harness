# w4verify-platform-r1 progress (independent verifier of w4fix-platform, round 1)

## Done
- (start) read fixer report docs/build/reports/w4fix-platform.md.

## Next
- read finalize.py pack_curves, curvefile.py, locks.py song_lock, run.py changes, cli pack; run W4 review tests;
  hunt for hacks and regressions; real-song checks.
- Ran W4 review tests: dogfood (3 skill-doc + stale curves) + platform (4) + unit test_w4_platform: 17 pass. Skill docs
  were edited by someone else (M6b fixer) at 17:35/17:47; API names checked against src/mvh/assets/mvh.js: OK.
- Repack regression (out/_wip/w4verify-platform-r1/repack.py): new curvefile.pack over integrator cache entries is
  byte-identical to integrator curves/ on synth + 4 real songs (index identical modulo schema_version).
- Read finalize.pack_curves, locks.song_lock, run.py (_content_equivalent, missing input), cli (relink slug, pack).
- Candidate issues to test: stale song.lock with a reused live pid (power failure) hangs forever; SongBusy uncaught
  in mvh meaning/frames; rename relink leaves old name in meta/source.json; mvh meaning --draft anthropic writes outside lock.
- Tone experiments (out/_wip/w4verify-platform-r1/exp.py rename|stalelock|failedingest|heldindex):
  rename keeps old file_name in meta/source.json (DOCUMENTED in RUNS §5: not a finding); stale song.lock whose pid is
  reused by a live process -> waits forever (75 only with MVH_SONG_LOCK_TIMEOUT); mvh meaning/frames: SongBusy traceback;
  forced ingest with missing input: fails OK but manifest warning says "cached canonical audio is used".
- Real stale copies (stale-megafauna via mvh meaning, stale-versatile via --only meaning,brief,viewer): curves +
  events byte-identical, index differs only schema_version, validate 0 errors BUT only 20 files: manifest.files drops
  every events/meta/audio file of stale stages (42 events -> 0). libcheck.mjs: eventNames 0; kickSource drums->mix
  (rc.2 meta/drums.json has no kick_source), kicks 647->188. => FINDING (W4D-1 manifest half not fixed).
- NEXT: write tests under tests/review/W4/verify-platform/, check mvh pack on a real folder, inspect rc.3 real runs.
- Tests written (all fail as intended, ruff clean): tests/review/W4/verify-platform/
  test_w4vp_stale_manifest.py (W4VP-1 major, 2 tests), test_w4vp_song_lock.py (W4VP-2 reused pid, W4VP-3 SongBusy
  traceback in meaning/frames; 3 tests), test_w4vp_missing_input_messages.py (W4VP-4 minor).
- mvh pack on integrator megafauna: 42 MB, lib loads fine (42 events, drums kick); validate on packed folder 17 errors
  (stems/viewer listed in manifest but not copied) - note only.
- NEXT: inspect rc.3 real runs (w4fix-platform/newton-stale, w4fix-analysis/* when done) for tmp leftovers, locks,
  validate; then report.
- fixer's rc.3 Newton run (out/_wip/w4fix-platform/newton-stale): 25 done + frames pending, no tmp/lock left, 116 files, 42 events, kick_source drums.
- RUNNING (background): out/_wip/w4verify-platform-r1/synth_run.sh -> synth full max run A + concurrent run B on the
  same folder (B printed the waiting message: lock works on real stages). Results in synth.rc / synth.validate.
  Resumable: re-run the script (cache hits).
- unit runner/cli/io: 60 pass. RUNNING: pytest tests/review/w1b tests/review/M6a tests/unit/contract tests/unit/ingest.
- NEXT: write docs/review/W4-verify-platform.md + report; compare synth with integrator synth when done.
- tests/review/w1b + review/M6a + unit/contract + unit/ingest: 135 passed, 1 skipped (no regression).
- docs/review/W4-verify-platform.md drafted (W4VP-1 major, W4VP-2..4 minor). Waiting for synth full run.
- synth full run: A rc 0, B (concurrent, waited) rc 0 with 25 cache hits, validate 119 files 0 errors, files = integrator
  + meta/drums.json, 240 channels identical, same degraded stage (notes). Review doc updated.
- NEXT: write docs/build/reports/w4verify-platform-r1.md and return.
- DONE: report written docs/build/reports/w4verify-platform-r1.md; returning structured summary.
