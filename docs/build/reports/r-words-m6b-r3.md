# r-words-m6b-r3: round-3 review of M6b (meaning, brief, frames), lens R-WORDS

Verdict: **fail** (3 new majors, all in parsing and round-tripping the user's intent; every round-2 major is fixed).

## Round-2 findings re-verified (by running code, not only the tests)
All 39 earlier review tests (r-words + r-contract) and the M6b unit tests pass (123 passed, 12 skipped).
- R2-1 / N1 (untouched template): fixed for real. Fallback V1 is stamped `proposed`; the template writes `lead_backing: ""`
  and only `voices` the user mapped. Probe p1: synth, synth without voices, synth without lyrics, megafauna,
  versatile, jeremy, newton-vs-nye; fenced and unfenced; with and without the synthetic draft: status never changes.
- R2-2 / N3 and R2-3 / N4 (template inside other text, lowercase free-text keys): fixed with `_template_region`
  (marker, or two template keys and no foreign `key:` line and no value cut by ` #`). See minor m15 for an edge.
- R2-4 / N5: `characters[].field_sources` is emitted, brief.md labels `(draft name + description)`, meaning.md says
  `draft name`, and the template prefills only intent fields.
- R2-5 / N6: SKILL.md §3 and RECIPES.md document `sections[]/characters[]/top-level field_sources`; the change
  request for `meaningAt` to return them is recorded in docs/contract/decisions/M6b.md.
- R2-6: `mvh frames` now always checks the stage status (outside this lens; the r-contract test passes).
- N2 (do-not label forms): fixed, but the fix over-captures (R3-3).

## New majors
- **R3-1** `docs.py yaml_template`: the template always writes `motifs: []`, `symbolism: []` and per-section
  `do_not: []`, although its docstring says it can replace the user's answers without loss. Copying the regenerated
  template back drops the user's section-level prohibition, motifs and symbolism.
  Test: tests/review/M6b/r-words/test_rw3_template_roundtrip.py.
- **R3-2** `intent.py _parse_yaml` + template palette line: hex typed the way the template comment shows
  (`palette: [#0e2346, ...]`) is a YAML comment. Fenced: the block fails and is also removed from the free text, so
  ALL answers (logline, do_not) are lost while the warning says "free text used". Unfenced: logline and do_not lost and
  the comment's example `#1b2a49` becomes a user colour. Block list `- #0e2346`: nulls dropped silently.
  Test: tests/review/M6b/r-words/test_rw3_template_hex.py.
- **R3-3** `intent.py _blocks/_DO_NOT_LABEL/_DO_NOT_HEAD`: a label line (`Avoid: x`) keeps the do-not block open across
  blank lines, so a following list of section notes becomes do_not rules (regression of the N2 fix); a heading that
  merely contains a do-not word (`## The story: a night that never ends`) turns the story into a do_not rule and loses
  the logline. Test: tests/review/M6b/r-words/test_rw3_do_not_overcapture.py.

## Minors (docs/review/M6b-r-words.md, Round 3)
m14 no-heading section notes also become the summary/logline; m15 a trailing comment on one key line makes a
marker-less template free text; m16 RECIPES `isDraft` treats `audio` facts as drafts.

## Gate
`scripts\gate.ps1 M6b`: review, ruff, contract and validate PASS; unit FAIL only in tests/unit/contract
`test_stub_files_are_stubs` (rhythm is now implemented; not M6b). Log: out/_wip/r-words-m6b-r3/gate.log.
No real lyric text appears in any probe output, test or report.
