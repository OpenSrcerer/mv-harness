# w4verify-words-r1 report (independent verifier of w4fix-words, M5 + M6b, round 1)

Verdict: pass-with-fixes. Full review: docs/review/W4-verify-words.md. Failing tests: tests/review/W4/verify-words/test_w4vw_ud1_do_not.py (5 fail, 1 control pass).

## Findings
- W4A-S16 / S16 (M5): FIXED. Independent re-run on Newton: backing span L021 dropped; two mouths open 2.29 s -> 0.20 s
  (longest 0.13 s); lead spans identical; adversary backing test passes on my run (MVH_REVIEW_RUNS=out/_wip/w4verify-words-r1/review).
- W4A-UD1 (M6b): PARTLY FIXED. Named cases pass. Still failing:
  - VWU1-a (major, regression): do_not list + one indented `key: value` line -> `_load_region` keeps `sub if sub else subl`,
    so the rules vanish and the stray line becomes the only rule; no warning, unparsed_keys empty. Same for symbolism etc.
  - VWU1-b (major, not fixed): `-<TAB>item` at column 0 ends the region in `_scan_unfenced` (needs "- "): rules -> note, no warning.
- Minors: m1 meaning/brief stage version not bumped (1.1.0) despite changed output; m2 tautological assert in the fixer's
  test_demotion_reaches_meaning_json_and_the_brief; m3 tab after `do_not:` demoted (warned), mixed tab/space merges two rules.

## Regression hunt
Driver: out/_wip/w4verify-words-r1/scripts/drive.sh synth newton-vs-nye jeremy versatile (copy of the fixer's in-process
driver on out/_wip/ud2-kick cached upstream); compare: run.ps1 python out/_wip/w4verify-words-r1/scripts/compare.py.
synth, jeremy, versatile: voices/lipsync/meaning/brief unchanged (meaning gains `intent_unparsed: []`). Newton: only the
backing-span change and its 2 brief rows. Fix vs my re-run: identical except provenance.key (path hash).
Unit+review words tests: 1039 passed, 11 skipped; ruff clean.
