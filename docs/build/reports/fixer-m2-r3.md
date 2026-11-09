# fixer-m2-r3: W3 module fix round 1, M2 Rhythm (structure)

## Scope
Open W2 findings F4-r3 (major) and F6-r3 (major), plus the integration seams S05 (major) and S09 (minor). All four are in
the structure stage. The changes are in `src/mvh/stages/structure/{__init__,features}.py`, with a new unit test
`tests/unit/structure/test_robustness.py`. The decisions are in `docs/contract/decisions/M2.md` (section "W3 module fix
round 1").

## Fixes
- **F4-r3: bar-jitter robustness.** Three changes:
  - `features.bar_pattern` slots are now centred on the 16th-note grid, not bounded by it. The same drum bar now gives
    the same fingerprint up to half a slot of downbeat error (the review test: cosine 0.0 before, >= 0.95 now).
  - The novelty evidence is averaged over bar grids shifted by -2..+2 frames (param `bar_jitter_frames`). This covers
    Foote novelty, energy change, drum-pattern and embedding novelty, and the phrase-grid 4-bar novelty.
  - The DP charges each phrase-breaking section shorter than 4 bars an extra `short_section_margin` x cost (0.25 x
    cost), except a section that ends at a forced boundary or at the song's end. A 2+3 or 2+2 split no longer flips on
    a knife edge.
  - Result: on the synthetic song the boundary F is 1.0 for the real rhythm, the truth rhythm, and shifts of
    -20/-10/+10/+20 ms and real ±15 ms. Before, -10, -20, real and real+15 gave 0.923, and after the bar_pattern fix
    alone +10 and +20 failed.
- **F6-r3: MEGAFAUNA drop extent.** Two changes:
  - The extension is now measured against the drop's plateau level: the mean bar drive over its first 8 bars,
    independent of how the opening is segmented. The tolerance is 0.6 z, or 1.2 z for sections of a repeat group
    already in the drop.
  - A drop-group section with its own drop cue at the drop's energy is also a drop, even below the 70th-percentile
    drive gate.
  - Result: MEGAFAUNA's drop is 141.8-212.7 s, covering 1.0 of the 146.3-212 s plateau (before: 0.454).
  - Versatile gains a build at 44.3 s and a drop at 51.7 s, against SPIKE's "drops at 47.5 s and 171.9 s". The 51.7 s
    section has a +70 dB bass jump and was missed only because its drive (1.39 z) sat just under the percentile gate.
- **S05: the impact snap.** A major impact (strength >= 0.6) on the downbeat one bar before a section start moves that
  start to the impact bar, when that bar clears the section cost by its own evidence (`impact_snap_strength`).
  - Result: Jeremy's verse#1 now starts at 19.47 s, the band entry and the song's only impact. The intro is now 8 bars.
- **S09: form labels.** These apply in allin1-informative labelling:
  - The opening section is labelled `intro` when no other section repeats it and its drive is below the song median.
  - A section is labelled `bridge` when no other section repeats it, it sits between two choruses, and allin1 cannot
    place it (top probability < 0.55).
  - Result: the synthetic labels now equal the truth (intro, verse, chorus, bridge, chorus, outro).
  - Newton is unchanged. A looser bridge rule would have relabelled its confident verse at 41.8 s, so the probability
    test was added.
- Additive: `meta/structure.json` `boundary_components.nov_grid`.

## Tests
- `tests/review/M2/**` with `MVH_REAL_TESTS=1` (includes `test_structure_drop_extent_real.py`): 25 passed.
- `tests/unit/{allin1,rhythm,structure,choreo,cues}`: all pass (41 + 4 new; 7 skipped opt-in).
- The integration tests `tests/integration/M2/*` read `out/_wip/integrator/<slug>`, which I may not write. I checked
  their exact logic on my re-run folders instead (`out/_wip/fixer-m2-r3/compare.py`):
  - S05 Jeremy: the impact-to-section gap is 0.00 s (before: 2.34 s), so it passes.
  - S09 synth: the intro is one section labelled `intro` (before: two sections labelled `verse`), so it passes.
  - The two tests will pass once the integrator re-runs structure, choreo and cues.

## End-to-end comparison
For each song I copied the integrator's max folder to `out/_wip/fixer-m2-r3/<slug>`, ran
`mvh analyze <folder> --only structure,choreo,cues --force structure,choreo,cues --no-network`, then ran validate (0
errors on all 5).

| song | integrator | fixer-r3 |
|---|---|---|
| synth | F 0.923, intro split 2+2 'verse', bridge 'verse' | F 1.0, labels == truth |
| megafauna | drop 141.8-176.1 (cover 0.45), plateau 'inst' | drop 141.8-212.7 (cover 1.0) |
| jeremy | verse#1 at 21.80 (2.34 s after the impact); 20 sections, 12 chorus | verse#1 at 19.47; 4+4 at 254.9 merged to 8; 19 sections, 11 chorus |
| versatile | sections identical | + build 44.3-51.7, + drop 51.7-81.2 |
| newton-vs-nye | identical | identical |

Counts, grooves and cue tier counts are unchanged on all five songs.

## Gate (`scripts\gate.ps1 M2`)
See `out/_wip/fixer-m2-r3/gate.log`. Every M2 step passes: the unit tests of all five M2 stages, review, validate, e2e
and lib-node. The non-M2 failures are below.
- `unit` (tests/unit/contract), `contract` and `ruff` fail on files other agents are editing concurrently:
  - The vocals stage now declares `lyrics` in its deps. This breaks `test_deps_match_plan`, and the generated
    CONTRACT.md is out of date (the vocals row).
  - `src/mvh/stages/notes/__init__.py` has an import-order ruff error (I001).
  - None of these are M2 files.
- `determinism` FAIL: 44 of 181 files differ between the two runs. The earliest stage that differs is `spectral` (M1,
  deps = ingest only). `loudness` has the same single dep and is identical, so the cause is not upstream of spectral.
  - spectral's source files changed while the gate was running: `stage.py` at 06:26, `__init__.py` at 06:33 and
    `dsp.py` at 06:43. These are another agent's edits. The second analyze started at about 06:42, so the two runs used
    different spectral code. The difference cascades into rhythm, dynamics, harmony, structure, choreo and cues through
    the keys and the content.
  - Run in-process twice on the synth fixture, spectral, structure, choreo and cues are each bit-identical
    (`out/_wip/fixer-m2-r3/det_spectral.py`).
  - The integrator's quiet-machine gate-all passed determinism with 0 of 181 files differing.
  - Re-run the gate once the other module fixers have stopped editing.
- Overall `gate.ps1 M2` exit 1. Every failing step is caused by other modules' concurrent edits, not by an M2 file.

## Open issues
- The integration tests `tests/integration/M2/*` read `out/_wip/integrator/*`, which is not my path. They need the
  integrator to re-run `structure,choreo,cues` (plus `lyrics,mood,meaning,viewer,brief` downstream) on the five songs.
- Jeremy still has 11 of 19 sections labelled chorus. The long ending (203-288 s) repeats chorus material by allin1's
  probabilities. No truth exists to justify relabelling it.
- `split_min_novelty` (0.5) still decides the synthetic verse -> chorus split at 17.0 s with a margin of 0.02-0.07.
  It now uses jitter-averaged novelty, and every tested variant passes.
