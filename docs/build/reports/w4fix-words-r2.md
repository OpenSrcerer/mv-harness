# w4fix-words-r2: W4 fixer, words group (M5, M6b), round 2

## Findings fixed (src/mvh/stages/meaning/intent.py)
- VWU1-a (major): `_load_region` per-entry fallback kept `sub if sub else subl`, so under `do_not:` a valid `- ` list
  followed by one indented `key: value` line (`Also: lots of fog please`, `chorus: no close-ups`) dropped every typed
  rule and promoted the stray line to the only rule, silently. Now the entries are kept in typed order and:
  - list keys (`do_not`, `symbolism`, `themes`, `references`, `palette`, `motifs`): the `- ` items are the answer, each
    bare `key: value` line is kept verbatim as a note with a warning and its key goes into `unparsed_keys`
    (-> meaning.json `intent_unparsed`, first open question, brief.md bold line);
  - `notes`: every entry kept, in order, no warning;
  - map keys (`characters`, `voices`, `sections`, `line_singers`): every entry kept, as bullets in order (`_list_answer`).
- VWU1-b (major): `_scan_unfenced` continued a region over column-0 items only for `- `; now `_COL0_ITEM`
  (`^-(?:[ \t]|$)`) also accepts `-<TAB>item`, so `do_not:` then `-<TAB>rule` keeps every rule (tabs after the dash
  were already expanded by `_expand_indent`).
- Tried: dedenting demoted notes; reverted (tests/unit/meaning/test_intent_grammar.py requires verbatim notes).

## Tests
- tests/review/W4/verify-words/test_w4vw_ud1_do_not.py: 6/6 pass (were 4 failing).
- New unit tests in tests/unit/meaning/test_intent_w4_do_not.py (stray colon line in do_not / symbolism / notes, mixed
  map keys, `-<TAB>` at column 0, stray line reaching meaning.json + brief.md).
- tests/unit/meaning + tests/unit/brief all pass; ruff clean on meaning.
- tests/review/W4/verify-words + adversary UD1 + tests/unit/meaning + tests/review/M6b + m6b: 946 passed, 4 skipped.

## No regression
- Words stages (voices, lipsync, meaning, brief) re-driven in process on the cached upstream of out/_wip/ud2-kick/<slug>
  for synth, newton-vs-nye, jeremy, megafauna, versatile (driver: out/_wip/w4fix-words-r2/scripts/drive.sh; outputs
  out/_wip/w4fix-words-r2/<slug>). Against round 1 (out/_wip/w4fix-words/<slug>) every file is byte-identical except
  `provenance.key` in phonemes/visemes/singing/meaning.json (code hash). None of the real runs has an intent.md, so the
  parser change cannot move them; the synth intent parses as before.
- Gate M6b (docs/build/progress/w4fix-words-r2.gate-M6b.log): fixture, unit, review, ruff, contract, validate, e2e,
  lib-node PASS; determinism FAIL with 50/183 files differing incl. curves/core.f32 and rhythm/structure/drums/dynamics
  events: foreign. Other fixers edited rhythm (trackers, fusion), drums, dynamics, structure, spectral, vocals, allin1
  and runner files during the gate's two --force runs (mtimes 18:13-19:49). Words-stage determinism is shown by the
  round-1 vs round-2 driver runs (identical content).

## Open
- tests/review/W3/critic/test_w3c_handoffs.py and adversary test_w4a_backing_spans_..._newton read the review run
  folder (out/_wip/integrator by default), which predates the round-1 voices fix; they pass on the round-1 rerun
  (MVH_REVIEW_RUNS=out/_wip/w4fix-words/review). Needs a fresh integrator run.
