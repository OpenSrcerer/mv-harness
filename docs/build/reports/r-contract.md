# r-contract report (W1b independent review, video-agent lens)

Verdict: **pass-with-fixes**. No blockers; 5 majors with failing tests; 10 minors. The full findings, with evidence and
suggested fixes, are in [docs/review/w1b-r-contract.md](../../review/w1b-r-contract.md).

## Majors (each has a failing test)
| # | Finding | Tests |
|---|---|---|
| F1 | cues `next()` returns only the first of co-timed items, so iterating cues never reaches build_start (25.0) or the drop (34.5, moment rank 1) | `test_f1_*` (py), `F1` (node) |
| F2 | `lyrics/lines.tsv` `singer` keeps only the lead on duet lines (C2 missing on L005/L006/L009/L010); the format of a multi-singer line is undefined | `test_f2_*` |
| F3 | notes' `{src}` patterns claim `events/notes.vocals.json` and `notes/vocals.mid` (owned by vocals, D6): two producers in the manifest, and publish can unlink vocals' file | `test_f3_*` (incl. a skeleton run in tmp_path) |
| F4 | `vizState(t)` silently pools at 60 fps, and CONTRACT §9 documents no frame rule: at 30 fps, 32/141 bass onsets never report `onset` | `test_f4_*` (py), `F4` (node) |
| F5 | `Events.at` returns one item and there is no all-at query: duet visemes give the backing voice, chords give one note; the CONTRACT §9 recipe misleads | `test_f5_*` (py), `F5` (node) |

## Verified OK
- The walking skeleton runs (exit 0, `mvh validate` 0 errors).
- JS/Python parity is 0 diffs, and the Python loader matches `conventions.py` with 0 diffs, on 2,074 edge times x 10
  extra frame rules (120/144/200 fps, 1 fps, 7.5 fps, frame0 -3 and 1000, early, rationals).
- The flash rule holds at 24/23.976/25/30/60 fps.
- The fixture is internally consistent and matches its own audio (drum sub-stem onsets within 0.1 ms, voice stems active
  only in their singing spans, digital-zero silence, sample-aligned stems).
- Browser/Remotion URL-mode loading works with `ensure('helper:X')`.

## Files
- tests/review/w1b/contract/test_rcontract_video_agent.py (9 failing tests)
- tests/review/w1b/contract/rcontract_video_agent.test.mjs (3 failing tests)
- docs/review/w1b-r-contract.md
- out/_wip/r-contract/synth/ (skeleton output)

## Change requests
None from this reviewer. The fixes for F1, F2, F4 and F5 touch frozen contract semantics (D28 helper rules, the
lines.tsv format, CONTRACT §9), so the orchestrator decides them as CRs. F3 matches fixtures' CR 1 and extends it to
`match_output`, the manifest and publish.
