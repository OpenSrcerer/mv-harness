# fixer-m2-r4: M2 Rhythm, W3 module fix round 2

## Scope
fixer-m2-r3 (W3 round 1) fixed the routed findings F4-r3, F6-r3, S05 and S09, and the verifier r-dsp-m2-r4 confirmed
all four. The verifier found one new major, **F7-r4**, a regression from the S05 impact snap:
- Jeremy's verse#1 was snapped to the band entry at 19.47 s, which made it 9 bars long.
- Its phrases were laid out as 8 + 1, with the 1-bar remainder at the END.
- As a result, every eight-count of the first verse moved by one bar (4 counts), and a 4-beat partial count was left
  just before the first chorus.

This round fixes F7-r4 and the cheap minor r4-m2.

## Fix: phrases keep the song's phrase grid (M2-D-phrase-grid)
- **What changed.** `src/mvh/stages/structure/__init__.py` has a new pure function,
  `phrase_layout(sec_ranges, phrase_L)`, which the stage now uses to build its phrases.
  - Phrases still restart at every section start.
  - For a section that is not a whole number of phrases, the function decides where the remainder goes: it becomes a
    leading (pickup) phrase when the song's other section starts clearly sit on the grid through `start + remainder`.
  - Support score: an aligned start counts 1 on the phrase_L grid and 0.5 on the 4-bar grid only. The song start is
    excluded.
  - Thresholds: the pickup needs at least half of the other starts and a margin of 1 over the plain section start.
  - Otherwise the remainder still closes the section, as before.
- **It is general, not tied to the snap.** The rule does not check whether the snap fired. It applies to any section
  whose start sits off the song's phrase grid (for example a fill bar before a verse).
- **Effect on Jeremy.** verse#1 is now phrased P 19.47 s (1 bar) + P 21.80 s (8 bars). The choreo eight-counts are
  E 19.47 (4-beat partial pickup), then 21.80 / 26.37 / 30.96 / 35.56 s. These are identical to the pre-snap grid, so
  the vocal entry falls on count 1 and no partial count dangles before the chorus.
- **Provenance.** A note records the placement: "phrase remainder placed at the section start".
- **first_count stays 1.** The pickup count keeps `first_count` 1, because CONTRACT allows 5 only for E000.
- **r4-m2.** The structure StageSpec version goes from 1.0.0 to 1.1.0, so cached structure outputs from before the W3
  changes are invalidated.

## Tests
- **F7-r4 review test.** `tests/review/M2/r-dsp/test_structure_impact_snap_counts_real.py` (`-m real`): 3 passed.
  Before the fix, 2 of its 3 tests failed.
- **All M2 review tests.**
  - `tests/review/M2` default: 22 passed, 6 skipped.
  - `tests/review/M2 -m real`: 6 passed, re-run after the refactor.
  - This covers jitter (F4-r3), MEGAFAUNA drop extent (F6-r3) and the downbeat vote.
- **Unit tests.**
  - The M2 unit tests (allin1, rhythm, structure, choreo, cues): 49 passed, 7 skipped.
  - New: `tests/unit/structure/test_phrase_grid.py` (4 tests): pickup when snapped; an ambiguous grid keeps the
    remainder at the end; whole phrases are unchanged; 4-bar grid support.
- **Ruff.** Clean.
- **Integration tests.** `tests/integration/M2` (S05, S09): 2 FAIL. They only read `out/_wip/integrator/<slug>`, which
  was written at 05:10, before the r3 fix. The same assertions pass on this round's re-run
  (`out/_wip/fixer-m2-r4/probes/seams.py`):
  - S05: gap 0.000 s, below one beat (0.562 s).
  - S09: a single 'intro' section.

  The integrator needs to re-run structure, choreo and cues.

## Real-song re-run (no regression)
**Why not `mvh analyze`.** `mvh analyze <copy of integrator folder> --only structure,choreo,cues --force ...` refuses
to run. The integrator's upstream caches (rhythm, harmony, dynamics, spectral, vocals) are stale against other modules'
current code.

**What I ran instead.** I used the verifier's method: `out/_wip/fixer-m2-r4/probes/runreal.py` re-runs structure,
choreo and cues with the current code on the integrator's runner caches (CacheUpstream).
- Output: `out/_wip/fixer-m2-r4/real/<slug>/`
- Comparison: `probes/cmp.py`, results in `out/_wip/fixer-m2-r4/cmp.txt`. It compares the integrator run, the
  verifier's r4 re-run (the code before this round) and mine.

| song | vs verifier r4 re-run (previous code) | vs integrator (05:10) |
|---|---|---|
| synth | identical | the S09 fix: one intro, the bridge labelled bridge (from r3) |
| jeremy | only verse#1 phrasing and counts changed (as intended) | verse#1 at 19.47 s (S05); the eight-counts are now identical to the integrator's |
| megafauna | identical | the drop runs 141.8-212.7 s (F6-r3, from r3) |
| versatile | identical | build 44.3 s and drop 51.7 s added (from r3) |
| newton-vs-nye | identical | identical |

## Gate
`scripts\gate.ps1 M2`, log at `out/_wip/fixer-m2-r4/gate.log`:

| step | result | cause |
|---|---|---|
| fixture | PASS | |
| unit | FAIL | `tests/unit/contract` only (2 fails), see below |
| review | PASS | |
| ruff | PASS | |
| contract | FAIL | same cause as unit |
| validate | PASS | |
| e2e | FAIL | the lyrics stage (M5) crashed in the first run; see below |
| lib-node | PASS | |
| determinism | FAIL | follows from the e2e failure; see below |

The gate exits 1 on four steps, and none of the failures comes from M2 code.

**Cause of the unit and contract failures.** The vocals StageSpec now depends on lyrics, but neither
CONTRACT.md's generated "consumed" table nor PLAN's dependency list has it. The failing tests are
`test_catalog_dag.py::test_deps_match_plan` and `test_schemas_io.py::test_generated_artifacts_up_to_date`. The other
M2 unit folders all pass.

**Cause of the e2e failure.** In the first run, the lyrics stage failed with
`TypeError: float() argument must be a string or a real number, not 'dict'`.
- `src/mvh/stages/lyrics/core.py` was being edited by M5 at 08:12, during this gate.
- vocals, choreo and cues were therefore not run.
- allin1, rhythm and structure finished.

**Cause of the determinism failure.** Run 2 completed but run 1 did not, so 40 files differ. Most are outputs that run 1
never wrote; `meta/separation.json` is the known GPU drum sub-stem issue (M3a). No M2 output from allin1, rhythm or
structure differs between the two runs.

**Checks I ran instead:**
- **Full pipeline.** After M5's edit I ran my own `mvh analyze` of the synthetic song, using the same command as the
  gate (`out/_wip/fixer-m2-r4/e2e.ps1`, log `e2e.log`). Every stage finished, including choreo and cues. Analyze
  returned 0 and validate returned 0. The sections match the truth: intro / verse / chorus / bridge / chorus / outro.
- **Determinism.** I re-ran structure, choreo and cues twice in-process on real upstream (Jeremy and the synthetic
  song). The outputs are byte-identical.

## Open
- r4-m3 (minor): Jeremy has 11 of 19 sections labelled chorus. These are allin1 labels on the long repeated-chorus
  outro vamp. Not changed.
- r4-m4 (minor): the DSP-only rhythm fallback locks onto the off-beat. Not changed (rhythm is untouched this round).
