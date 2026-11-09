# w4fix-words-r2 progress (W4 fixer, words group, round 2)

## Findings
- VWU1-a: intent.py _load_region per-entry branch `sub if sub else subl` drops list items when a stray colon line follows.
- VWU1-b: _scan_unfenced column-0 `-<TAB>item` not recognised.
Tests: tests/review/W4/verify-words/test_w4vw_ud1_do_not.py

## Done
- (start) read round-1 progress + tests.
- Milestone 1: intent.py fixed: _COL0_ITEM regex in _scan_unfenced (VWU1-b); _load_region keeps typed order, for
  _LIST_KEYS (not notes) mixed '- ' items + 'k: v' lines -> items kept, k: v lines demoted to note + warning + unparsed_keys;
  notes and map keys -> all entries as bullets in typed order (VWU1-a). Tried dedenting demoted notes: REVERTED
  (test_intent_grammar expects verbatim). Unit tests appended to tests/unit/meaning/test_intent_w4_do_not.py.
- Next: full meaning/brief tests, gate M6b, rerun meaning+brief on synth + real copies.
- Milestone 2: unit+review tests: verify-words 6/6 pass, tests/unit/meaning+brief pass. Remaining W3/W4 review failures are
  other groups (sections/kicks/grooves/hats/half-time/vocal_phrases) or read out/_wip/integrator runs (Newton backing, fixed r1).
- Running: drive (out/_wip/w4fix-words-r2/scripts/drive.sh synth newton-vs-nye jeremy megafauna versatile, .DONE markers)
  and gate M6b (docs/build/progress/w4fix-words-r2.gate-M6b.log).
- Milestone 3: decisions W4-W3 in docs/contract/decisions/W4-words.md; extra unit test (build + brief); report draft
  docs/build/reports/w4fix-words-r2.md. Waiting on drive + gate.
- synth driven: vs round 1 only provenance.key differs (phonemes/visemes/singing/meaning.json); content identical.
  compare: sh out/_wip/w4fix-words-r2/scripts/cmp.sh <slug>; then scripts/jd.py r1dir r2dir <rel json...> via run.ps1.
- newton driven: only provenance.key differs (if jd shows 1 each)
- gate M6b: fixture/unit/review/ruff/contract/validate/e2e/lib-node PASS; determinism running
- ALL 5 driven (round 2): vs round 1 every file identical except provenance.key in JSON (code hash). No regression.
- DONE: gate M6b all PASS except determinism (foreign mid-gate edits). Report docs/build/reports/w4fix-words-r2.md
