# w4verify-words-r1 progress (independent verifier of w4fix-words, round 1)

## Done
- started; read fixer report docs/build/reports/w4fix-words.md

## Next
- read intent.py, voices core.py, adversary tests; probe UD1 edge cases; rerun words stages on synth + 2 real songs; write tests.

## Milestone 1: UD1 probes (out/_wip/w4verify-words-r1/probes/ud1_probe.py)
- adversary + fixer UD1 tests pass (15).
- NEW: do_not list + one indented 'key: value' line -> rules silently dropped, that line becomes the only do_not rule, no warning (sub wins over subl in _load_region).
- NOT FIXED: '-<TAB>item' at column 0 under do_not: region ends (scan needs '- '), rules -> note, NO warning, unparsed empty.
- minor: 'do_not:<TAB>text' demoted (warned); mixed tab/space merges two rules (YAML continuation).
## Milestone 2 (running): driver copy out/_wip/w4verify-words-r1/scripts/drive.sh synth newton-vs-nye jeremy versatile (<slug>.DONE markers, resumable)
- tests/review/W4/verify-words/test_w4vw_ud1_do_not.py written: 5 fail (VWU1-a stray colon line x3, VWU1-b tab-after-dash col0 x2), control passes.
- synth driven: 3 backing spans 100% backed kept, lead identical to old/int/fix, mouths 8.44 s (fixture duet) unchanged, brief unchanged; fix-vs-new differ only in provenance.key (path hash). compare: run.ps1 python out/_wip/w4verify-words-r1/scripts/compare.py <slugs>
- newton driven: backing L021 dropped, two mouths 2.29 -> 0.20 s (longest run 0.13 s), lead identical; adversary backing test PASS on out/_wip/w4verify-words-r1/review (MVH_REVIEW_RUNS). S16 FIXED.
- minor: meaning/brief stage versions not bumped (1.1.0) though outputs changed (intent_unparsed, brief line).
- jeremy, versatile driven: unchanged. Words unit/review tests 1039 pass. symbolism has the same sub/subl bug.
- DONE: docs/review/W4-verify-words.md and docs/build/reports/w4verify-words-r1.md written.
