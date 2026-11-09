# w4verify-platform-r1 report (independent verifier of w4fix-platform, round 1)

Full review: docs/review/W4-verify-platform.md. Tests: tests/review/W4/verify-platform/ (6 tests, all failing on
the current code as intended; ruff clean). Scratch: out/_wip/w4verify-platform-r1/. No production code was
changed. No lyric text was printed.

## Outcome per addressed finding

- W4D-1: half fixed. Curves are kept, byte-identical on real stale copies of MEGAFAUNA and Versatile. The manifest
  still drops every events, meta and audio file of the stale stages, so lib eventNames becomes 0 and kickSource
  falls back to mix. New finding: **W4VP-1 (major)**.
- W4D-2, W4D-3 and W4D-4 (skill docs): fixed in skill/ by the M6b side. The API names used in the docs exist in
  mvh.js. `mvh pack` works on a real folder (42 MB, and the lib loads it).
- W4P-1: fixed. One wrong warning remains after a forced ingest with a missing input (**W4VP-4, minor**).
- W4P-2: fixed. The held file case and concurrent runs work, including a real synth max run with a second run on
  the same folder. Two edge cases remain:
  - a power-cut lock whose pid was reused waits forever (**W4VP-2, minor**);
  - `mvh meaning` and `mvh frames` print a traceback on SongBusy (**W4VP-3, minor**).

## Regression checks (no regressions found)

- **Packing.** `curvefile.pack` output is byte-identical to the integrator's curves/ on the synth and all four real
  songs.
- **Tests.** Unit runner, cli and io: 60 pass. Review w1b, review M6a, unit contract and unit ingest: 135 pass and
  1 is skipped. The W4 dogfood and platform review tests, with the fixer's unit file: 17 pass.
- **Synth full max run.**
  - Both concurrent runs exit 0, and the second one makes 25 cache hits.
  - validate checks 119 files and reports 0 errors.
  - The file set matches the integrator's plus meta/drums.json, the 240 channels are identical, and the same stage
    (notes) is degraded.
- **Fixer's rc.3 Newton run.** 25 stages done, no tmp files or lock left, 42 events.
