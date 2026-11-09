# fixer-m5-r4 report (W3 module fix, round 2, M5 Words)

Round 1 (fixer-m5-r3) had already fixed R3-1..R3-4, S03 (grade) and S07, and the verifier (r-words-m5-r4) confirmed it.
This round fixes the one new major the verifier found (R4-1) and the cheap minors r4-m1, r4-m2 and r4-m4. It also tried
r3-m1 and then withdrew that fix, because it changed a real-song result. No real lyric text appears here.

## Fixed
| id | fix | where | decision |
|---|---|---|---|
| R4-1 (major) | A `Name:` line on its own is now only a marker CANDIDATE. The file accepts the set of candidates (`text._scan_labels`) when there are >= 2 distinct names and either (a) one of them recurs with DIFFERENT text after it, or (b) every one is a strict name (capitalised words and name particles, no pronoun or common verb) in a file that is not written in Title Case. Otherwise the lines stay sung: `I said to John:`, Title Case `Tell Me Why:`, and a chorus line written out twice that ends in `:`. This applies to every parser, including LRCLIB synced LRC. | `lyrics/text.py` `_scan_labels`, `_lone_marker`, `_strict_name`, `_title_case`, `_MARKERS` contextvar, `_plain_header` | M5-D54 |
| r4-m1 | Header long tail: `*Chorus*` / `**Bridge**`, `Chorus (repeat)` (re-inserts the chorus), `1st Verse:` / `2nd Verse`, `[Verse 1 - Name]` / `Verse 1 - Name` (a dash works like a colon), `Name (Verse 1):` and 5-word marker names. A lone `(x2)` line repeats the line before it. `[Intro: Spoken]` names no speaker. | `lyrics/text.py` | M5-D54 |
| r4-m2 | Joint speaker labels (`Ann & Bob`, `and`, `,`, `+`, `/`, `feat.`) are split into their singers, and `Both` / `All` / `Everyone` name no singer. With `n_source = hints`, k counts the single names. A joint line goes to the nearest centroid among its own singers (source `embedding`). | `voices/core.py` `hint_parts` | M5-D55 |
| r4-m4 | New partial-version control: a text with every 5th line sung differently. The near-miss snapping (M5-D53) changes its G1 by < 0.03. | `tests/unit/lyrics/test_r4_fixes.py` | - |

Withdrawn: **r3-m1 / M5-D56**, which capped a line's held last word at the next lead line's start.
- On newton it removed all 47 overlaps, but voices items went from 52 to 49, because chunking follows the line duration.
- The estimated k then flipped from 4 to 3 (silhouette at k = 3: 0.344; at k = 4: 0.338).
- I reverted it so that no real-song result regresses.
- A safe fix would take the voices item windows from word starts. That is a coupled change, left for a later round.

## Real-song comparison
Method:
- Upstream is the integrator's W3 max outputs, read through their cached stage outputs.
- The driver is `out/_wip/fixer-m5-r4/scripts/m5drive.py`, the same approach as round 1 and the verifier. The runner treats
  other modules' changed stages as stale.
- Outputs are in `out/_wip/fixer-m5-r4/<slug>/<stage>`.
- Compare with `python out/_wip/fixer-m5-r4/scripts/compare.py <slugs>`. It prints numbers only, for integrator, r3 and r4.

| song | integrator (W2/W3 max) | fixer-m5-r3 | **fixer-m5-r4** |
|---|---|---|---|
| jeremy | D, G1 0.697, 1 voice, mouth 22838 | B, G1 0.7705 | **B, G1 0.7705, G2-G7 identical, 1 voice, mouth 22838** |
| newton-vs-nye | B, G1 0.864, 4 voices | B, G1 0.8786 | **B, G1 0.8786, G2 0.7537, G5 0.98, G7 0.944, 4 voices, mouth 12185** |
| megafauna | D, G1 0.571 | D, G1 0.667 | **D, G1 0.667 (G2 0.618 remains)** |
| versatile | instrumental, mouth 55 frames > 0.1 | 0 | **0** |
| synth | B (transcribed), 2 voices | B | **B, 2 voices, mouth 1881** |

- Every number matches round 1. The cached LRCLIB / embedded sources of the 4 real songs contain no header or marker
  lines under the new parser: there are 0 hinted lines in all 30 cached candidates (`scripts/count_hdr.py`, counts only).
- The leak scan of all non-lyrics outputs and the run logs is clean (jeremy, newton and megafauna).

## Tests
- Text tests: tests/review/M5/r-words plus the new unit tests: 52 passed. This includes `test_rw5_r4_colon_lyric_lines.py`
  (5/5) and every R3 test.
- Full set: `pytest tests/review/M5 tests/integration/M5 tests/unit/{identity,lyrics,voices,lipsync}` gave 134 passed,
  7 skipped (`-m real`) and 3 failed. That run started before my last core.py edit, which was later reverted. The 3
  failures are the integration tests below.
- New: tests/unit/lyrics/test_r4_fixes.py (15 tests) and tests/unit/voices/test_joint_hints.py (a fake ctx with a fake
  embedder: a joint label does not become a third voice). Updated: test_r3_fixes.py (a lone `Name:` is now a candidate,
  decided per file).
- Integration tests: `test_real_instrumental_mouth` (S07) and `test_real_jeremy_correct_synced_text_is_not_graded_wrong_text`
  (S03) read `out/_wip/integrator/<slug>`, which holds the pre-fix run, so they fail until the integrator re-runs M5. On my outputs
  their assertions hold: versatile has 0 frames > 0.1, and jeremy is grade B with G2-G5 passing.
  `test_real_jeremy_sung_outro_is_not_wordless` cannot pass honestly (see open issues).
- Gate (`scripts\gate.ps1 M5`, log docs/build/progress/fixer-m5-r4.gate.log): **exit 1, and only for failures in other modules' files.**
  - PASS: fixture, review (M5=0), validate, e2e, lib-node and determinism (analyze --force twice).
  - The M5 unit folders (identity, lyrics, voices, lipsync) all exit 0.
  - FAIL: `tests/unit/contract/test_catalog_dag.py::test_deps_match_plan`. The vocals deps include lyrics (M3b vs PLAN_DEPS),
    and the lyrics deps match.
  - FAIL: `test_generated_artifacts_up_to_date` and the contract step (`mvh.contract.gen --check`: CONTRACT.md is out of date,
    which the integrator owns).
  - FAIL: ruff I001 in `src/mvh/sep/determinism.py` (another module's in-flight edit). Ruff on the M5 paths is clean.
  - The first gate run was aborted. It had caught a bug in the D56 cap (a variable shadowed the lead audio), which I fixed
    and then reverted with the rest of D56.

## Open issues
- `tests/integration/M5/test_real_jeremy_sung_outro_is_not_wordless` (S03 part 2) is wrong as written; this is the verifier's r4-m3.
  The outro is wordless singing: W0 VAD whisper has 0 words after 218 s, and the VAD-free gap retry keeps 3 words in 92 s.
  The stage flags it instead (`alignment.vocals_after_last_line_s` 75 s, plus a warning), and lipsync's ungated fallback
  animates it. Passing the test would mean inventing lyric lines.
- The S03 part 1 and S07 integration tests read the integrator's pre-fix folders. They clear once the integrator re-runs M5.
- r3-m1 (sustain-hold overlap) is still open. A fix needs voices item windows that do not depend on held word ends (see M5-D56).
- r2-m1 and r2-m2 (seam clamp; the order checks run before the final word times) are not addressed.
- megafauna stays grade D, unchanged since W2 (G2 0.618: the karaoke split leaves the lead stem nearly empty).

## Files changed
- src/mvh/stages/lyrics/text.py
- src/mvh/stages/voices/core.py
- src/mvh/stages/lyrics/core.py: D56 was added and then reverted, so the net change is none.
- tests/unit/lyrics/test_r4_fixes.py (new) and tests/unit/lyrics/test_r3_fixes.py
- tests/unit/voices/test_joint_hints.py (new)
- docs/contract/decisions/M5.md (M5-D54, D55, D56 withdrawn)
