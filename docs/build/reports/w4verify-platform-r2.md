# w4verify-platform-r2 report (independent verifier of w4fix-platform-r2)

Full review: docs/review/W4-verify-platform.md (round 2 section on top). Tests: tests/review/W4/verify-platform/
(11 tests: 6 pass, 5 fail on the current code as intended; ruff clean). Scratch: out/_wip/w4verify-platform-r2/.
No production code was changed. No lyric text was printed.

## Outcome per addressed finding

- W4VP-1 (major): **fixed** for the file listing. Real copies of integrator rc.2 MEGAFAUNA (`mvh meaning`) and
  Versatile (`--only meaning,brief,viewer`) keep every manifest entry (111 / 118, identical to the integrator's),
  42 / 40 events, `mvh validate` 0 errors over 119 / 126 files, lib eventNames 42 / 40. No test-specific hack.
  New issues around it:
  - **W4VP-5 (major, regression)**: outputs kept from a different audio are listed while their curves are dropped as
    unfit (`test_w4vp_kept_outputs_other_audio.py`).
  - W4VP-7 (minor): kept stages lose degraded/fallback flags, warnings and summaries (`test_w4vp_kept_stage_flags.py`).
  - W4VP-8 (minor): a kept frames CSV is listed with no status.stages entry (`test_w4vp_kept_ondemand_status.py`).
- W4VP-2 (minor, also fixed by the fixer): **partly fixed**. A reused pid of a process the user cannot open (svchost
  etc., a third of live processes) still blocks forever: W4VP-6 (`test_w4vp_lock_unreadable_pid.py`).
- W4VP-3: fixed. The r1 meaning/frames test contradicted the reused-pid test (the fixer was right); corrected to plant
  a genuinely held lock, and it passes (exit 75).
- W4VP-4: fixed.

## Regression checks

- Synth max re-run on a copy of r1's rc.3 synth (19 stages re-ran after the spectral 1.4.1 bump): exit 0, the same
  111 manifest entries and flags as r1, validate 0 errors, no lock or temp file left.
- kick_source drums -> mix on the stale rc.2 copies: D79 rule for folders without meta/drums.json (note only).
- tests/unit/runner, tests/unit/cli, tests/review/W4/platform: 55 pass.
