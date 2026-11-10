# F-verify: independent check of the final fix pass (ffix-gain, ffix-form, ffix-small)

Verifier: fverify. Failing tests: `tests/review/F/verify/` (run with `-m "real or not real"`; numbers only, no lyric text).
Runs: `out/_wip/fverify/{jeremy,newton-vs-nye}` (copies of `w4fix-analysis-r2`, re-analysed in place with current code and
`--force separate_hq`), `out/_wip/fverify/rescue-me` (new CC BY test track, fresh analyze, see docs/build/test-tracks.md).
Comparisons: `out/_wip/fverify/cmp.py <old> <new>`; synthetic drum F1: `out/_wip/fverify/synthf1.py`.

## Verdict per fixer

| Fixer | Verdict | Why |
|---|---|---|
| ffix-form | pass | Rules are generic (recurrence, share, allin1 margin, near-repeat); no test-specific branches. Jeremy re-run reproduces the report (176.1 s hook = chorus, 220-288 s = outro). Independent pop song (Rescue Me): chorus kept (6 of 14 sections), so the evidence rule does not erase real choruses. |
| ffix-small | pass-with-fixes | Target tests pass (verify-words, verify-platform, platform: 30 passed). Ruff is clean now (the `_chorus_evidence` failure was a mid-edit state of structure). W4VP-8 still open in `finalize.build_manifest` (minor, below). |
| ffix-gain | fail | Invariance tests pass for a real reason (generic level scaling, no test hacks), but it brought two quality regressions and one weakened test bar, and its fix does not reach existing caches. |

## Findings

| ID | Sev | Where | Finding | Test |
|---|---|---|---|---|
| F-V1 | major | `src/mvh/stages/separate_hq/__init__.py` (version 1.0.0) | CR-F-gain-1 not applied: the worker now runs DrumSep at the analysis level, but the stage version did not move and the cache key has no code hash, so every existing folder keeps master-level DrumSep sub-stems on a re-run. | `test_fv_separate_hq_cache.py` |
| F-V2 | major | spectral 1.5.0, F-gain-5 | Default `onsets.high` recall on the -16 LUFS synthetic groove fell 0.77 -> 0.643; the unit test bar for the default was lowered 0.7 -> 0.6 (`test_onsets_mid_high_on_snares_and_hats[analysis_level]`). Every master quieter than -10 LUFS (Rescue Me is -14.6) now gets the lower-recall operating point. | `test_fv_spectral_onset_recall.py` |
| F-V3 | major | separate_hq worker + drums 1.4.0, F-gain-1 | DrumSep at the analysis level costs cymbal accuracy on a quiet mix: synthetic 44.1 kHz cymbal F1 vs truth 0.895 -> 0.778, -12 dB copy 0.919 -> 0.833, 48 kHz copy 0.686 (< 0.7 PLAN gate; `tests/review/M3a/r-ml/test_r2_drums_separated_synth_48k.py` passed at the W4 final gate and fails now, per the fixer's own `gate-M3a-final.log`). | `test_fv_gain_real_runs.py::test_fv_synthetic_cymbals_do_not_regress` |
| F-V4 | major | lyrics (M5), CR-F-gain-2 | W4V2-GAIN-VOCALS still open: MEGAFAUNA -12 / -20 dB vocal phrase IoU 0.788 (lyrics aligns the first lines differently). The vocals stage itself is invariant (fixer's base-lyrics swap gives 1.000). | `test_fv_gain_real_runs.py::test_fv_megafauna_vocal_phrases_survive_a_gain_change` |
| F-V5 | minor | `instruments/lead.py` F-gain-6 | Versatile now tracks the lead stem instead of the full vocals stem: vocal phrases 10 (6.0 s) -> 6 (3.4 s), notes.vocals 27 -> 17. Level invariant, but a content loss on the master; whether the karaoke "backing" holds the main chops is unverified. | none |
| F-V6 | minor | `src/mvh/runner/finalize.py` build_manifest | W4VP-8: an on-demand stage (frames) that is not current is skipped when status.stages is built, but its kept files are listed. `tests/review/W4/verify-platform/test_w4vp_kept_ondemand_status.py` (real) still fails. | existing |
| F-V7 | minor | structure 1.5.0 | Rescue Me: 131.1 s falls back to allin1's `outro` (not recurring) but is followed by a 3.7 s `chorus` (group D) and then the real outro: an outro in the middle of the ending. Cosmetic; label_evidence explains it. | none |

## Regression scan (old = w4fix-analysis-r2, new = current code)

- Jeremy: sections as the form report; drum hits within 2 %, hits.high +8 %, onsets +1-3 %, vocal phrases 41 -> 41, stem activity within 3 s.
- MEGAFAUNA (ffix-gain run): sections and EDM roles identical; drums within 2 % except toms 63 -> 49; onsets within 1 hit.
- Versatile (ffix-gain run, -6.1 LUFS, DrumSep at -3.9 dB): snare -6 %, tom -13 %, cymbal +5 hits; vocals see F-V5.
- Newton vs Nye (fresh re-run, rc 0, validate 0): 7 chorus -> 0 (11 verse, 2 outro, silence; right for a rap battle); drum hits, hits and onsets identical; vocal phrases 12 -> 12, notes.vocals 259 -> 258.
