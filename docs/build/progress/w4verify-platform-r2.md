# w4verify-platform-r2 progress (independent verifier of w4fix-platform-r2)

## Scope
- W4VP-1 (major): build_manifest lists kept outputs of stale/pending/failed stages. Also check the fixer's minors
  W4VP-2..4 (locks.pid_started, cli SongBusy->75, run.py warning drop) for regressions.

## Done
- Read fixer report/progress, r1 report/review, finalize.py build_manifest diff area.

## Next
- run review + unit tests; real stale copies (MEGAFAUNA, Versatile) under out/_wip/w4verify-platform-r2/; edge cases
  (different audio in folder, unpublished stage, failed stage); fix r1 meaning/frames test (contradictory lock).

## Milestone 1 (done)
- r1 test test_w4vp_song_lock meaning/frames corrected (held lock started=now; fixer was right it contradicted test 1).
- review dir + fixer unit tests: 21 pass, 1 fail (real megafauna test reads r1's old-code folder; expected).
- Real: copies out/_wip/w4verify-platform-r2/stale-{megafauna,versatile} (integrator rc.2) after `mvh meaning` /
  `--only meaning,brief,viewer`: files 111->111 / 118->118, events 42/40 kept, entries identical, validate 119/126 files 0
  errors, lib eventNames 42/40. kickSource drums->mix (pre-D79 folder, D79 rule; note only). Flags degraded:/fallback: of
  kept stages and summary.stages are dropped (pre-existing; status.stages=stale).
- E1 exp_newaudio.py: different audio (6 s) into a 3 s folder with --only ingest: loudness/spectral curves dropped
  ("do not fit") but meta/loudness.json + events/hits.*/onsets.* of the OLD audio listed -> NEW finding (major).
## Next
- write test for E1; E2 frames on-demand kept listing on r1 synth copy; synth no-op regression compare; report.

## Milestone 2 (done)
- tests written (all fail on current code, ruff clean): test_w4vp_kept_outputs_other_audio.py (W4VP-5 major, E1),
  test_w4vp_lock_unreadable_pid.py (W4VP-6 minor: W4VP-2 partly fixed; pid_started None for 135/400 live pids, svchost
  etc. -> lock held forever; boot-time rule missing). stale_manifest real test now prefers the r2 copy (passes).
- W4VP-3 confirmed fixed (corrected meaning/frames test passes, exit 75). W4VP-4 review test passes.
- background: synth re-run (spectral 1.4.1 bump -> 19 stages) on out/_wip/w4verify-platform-r2/synth (copy of r1
  rc.3 synth), log synth.rerun.err, rc in synth.rerun.rc. If interrupted: just re-run the same command (cache resumes).
## Next
- after synth: compare manifest vs r1 synth; E2 frames on-demand kept listing; report + review doc.

## Milestone 3 (done)
- test_w4vp_kept_stage_flags.py (W4VP-7 minor): kept stages lose warnings/summary/degraded+fallback flags (fast + real,
  both fail). NOTE: a failed pathlib write_text(newline=...) truncated a file once; rewrite whole files with Write.
## Next
- wait synth re-run; compare with r1 synth manifest; E2 frames; then review doc + report + StructuredOutput.

## Milestone 4 (done)
- synth re-run rc 0 (19 stages re-ran): file set == r1 synth (111), entries identical, flags identical, validate 119/0,
  no lock/tmp left. frames: after `mvh frames` + `mvh analyze --param meaning.foo=2`, frames/24fps.csv listed, no
  status.stages entry -> test_w4vp_kept_ondemand_status.py (W4VP-8 minor). Review dir: 5 fail (intended), 6 pass.
## Next
- unit runner/cli suites; review doc + report + StructuredOutput.

## Milestone 5 (done) - FINISHED
- unit runner/cli + review W4/platform: 55 pass. Review doc (round 2 section prepended) and report written.
- Findings: W4VP-5 major (other audio), W4VP-6/7/8 minor. Only StructuredOutput left.
