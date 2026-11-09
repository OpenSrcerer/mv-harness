# r-platform-m6a-r5: R-PLATFORM review of M6a Viewer, round 5 (W3 verify)

Verdict: **fail**. There is 1 new blocker, and 1 major from round 4 is still open. Minor findings are in `docs/review/M6a-r-platform.md` under "Round 5".

## 1. Round-4 finding: F-R4-VOICE-FLOOR is NOT fixed
- `src/mvh/stages/voices/intent.py` and `src/mvh/stages/voices/core.py` have not changed since round 4 (mtimes 03:59 and 03:47; round 4 ended at 07:04).
  - `_merge_viewer_block` still raises `n_voices` to the highest mapped voice.
  - `core.run` still clusters into exactly `k = n_int` (`n_source=intent`).
  - No `n_voices_min` or similar exists anywhere.
- `docs/build/reports/fixer-m6a-r4.md` re-applied the round-3 `edit.js` fix and calls the voice-floor test "voices stage, not M6a; change request".
- `tests/review/M6a/r-platform/test_r4_platform.py` still fails 3 of 3 cases (V1 gives 1 voice, V1+V2 gives 2, V2+V3 gives 3); the baseline still gives 4.

## 2. New blocker: F-R5-APPLIED-BOUNDARY
**What breaks.** The viewer cannot be opened in edit mode after a section-boundary edit has been applied by a re-run.

**Cause.**
1. `structure/__init__.py` (lines 326-338 and 726-735) builds `applied` with one entry per edit: `{"key": "structure.boundaries", "value": {action, t, to_t}}`.
2. It returns `applied` as `provenance.overrides_applied`.
3. `runner/child.py` restamps every envelope with `provenance_block(job, res.provenance)`. That replaces the runner's per-key default (`ctx.py` 108-109), so `events/sections.json` carries the per-edit list.
4. `assets/viewer/data.js` `appliedOverrides()` does `out[o.key] = o.value`, so the last edit's object wins.
5. `edit.js` `pendingBoundaries()` then evaluates `(appliedOverrides('sections')['structure.boundaries'] || []).map(J)`, which throws `TypeError ... .map is not a function`.

**Effect.**
- Served (`mvh view`): `initUI -> refreshPanel -> pendingBoundaries` throws, and the page shows only "The viewer could not load this song".
- file://: the Sections lane throws on every draw.

This breaks the main correction loop the brief describes: correct sections in the viewer, re-run, check the result. The user cannot get back into edit mode to undo the edit, because the page itself fails. The only way out is to hand-edit `overrides.json` and re-run.

**Evidence.**
- Real pipeline output: the W3 critic's real round trip `out/_wip/critic-w3/rt-synth` (the runner applied overrides.json `structure.boundaries [{move 16.998 -> 21.0}]`). I copied it to `out/_wip/r-platform-m6a-r5/rt-synth` and rebuilt `viewer.html` with the current code.
- Claude_Browser, served: `fatal` = "The viewer could not load this song / TypeError: (appliedOverrides(...).structure.boundaries || []).map is not a function at pendingBoundaries ... at Object.refreshPanel ... at initUI". The console shows the same error, plus `lane sections TypeError`.
- Headless Edge, file://: state ready, `laneErrors` = 2 Sections errors.
- Failing test: `tests/review/M6a/r-platform/test_r5_platform.py` (2 tests, about 18 s).
  - It runs the real structure stage on the synthetic fixture with one boundary override.
  - It stamps provenance with the runner's own `provenance_block`, builds the folder and the real `viewer.html`, and drives headless Edge.
  - Served: `'fatal' == 'ready'` fails. File: lane errors.
  - Both fail now for exactly this reason.

**Suggested fix (M6a).**
- In `appliedOverrides`, collect repeated keys: `out[k] = k in out ? [].concat(out[k], v) : v`.
- In `pendingBoundaries`, normalise with `[].concat(x || [])`.
- Optionally, structure (M2) could record one entry per key with the full list, as the runner's default does. The viewer should be tolerant either way, because the contract (`arr(obj({key, value}))`) allows repeated keys.
- Also add a review/integration test that runs the R19 round trip and then loads the viewer.

## 3. Regression check on real songs (integrator outputs)
- jeremy and versatile were copied with `out/_wip/r-platform-m6a-r5/copy_song.py` (no `.cache` or `.wav`), and `viewer.html` was rebuilt by calling the real stage (`build_real.py`).
- Served edit mode: all 11 lanes are present with no lane errors.
- Headless Edge, served and file://: ready and playing, with `currentTime` and `V.t` within 10 ms. In file:// the console is clean. In served mode the console shows only 2 favicon 404s (minor m16).
- The Claude_Browser pane was hidden this session, so rAF never fired there. Sync was therefore measured in headless Edge.
- The meaning stage's current parser reads a Unicode viewer block correctly (voices, sections, palette, do-not rules).
- Override keys are consistent between the viewer and the stages.
- m6 (`t1: 1e999` answers 200) is still open. tests/integration has no M6a folder; the only seam test that touches the viewer is M5's, and it is parser-only.

## 4. Gate
`scripts\gate.ps1 M6a` (log: `out/_wip/r-platform-m6a-r5/gate.log`):

| step | result | notes |
|---|---|---|
| fixture | PASS | |
| unit | FAIL | Viewer 51/51 pass. The contract unit tests fail on files M6a does not own (`test_deps_match_plan`, `CONTRACT.md` generated file out of date). |
| review | FAIL | The 5 failures are exactly my findings: `test_r4_platform` x3 and `test_r5_platform` x2. The other 16 pass. |
| ruff | FAIL | Repo-wide only. `ruff check tests/review/M6a src/mvh/stages/viewer src/mvh/assets` is clean. |
| contract | FAIL | Not M6a. |
| validate | PASS | |

The end-to-end analyze and determinism steps were still running when I stopped. The gate was a background task of this session, so it ended with the session.

## Files
- Tests: `tests/review/M6a/r-platform/test_r5_platform.py` (new) and `test_r4_platform.py` (still failing).
- Probes: `out/_wip/r-platform-m6a-r5/` (`copy_song.py`, `build_real.py`, `play_probe.py`, `probe_struct.py`, `probe_meaning_rt.py`).
- Review doc: `docs/review/M6a-r-platform.md` (Round 5).
