# ud1-meaning progress (W4 phase 0, UD1 meaning input format)

## Done
- [x] Read BUILD-STATUS UD1, intent.py (v3 heuristic grammar), docs.py (template), stage.py
- Baseline: review M6b 24 fails (rw5_* heuristic tests), W3 critic 5 fails (not meaning; not mine)

## Next
- design v4 grammar: template (fenced/unfenced) + free text = notes + viewer block

## Design (decided 2026-11-09)
- intent.py rewritten as grammar "mvh-intent v2": viewer block (wins) > template regions (fenced ```yaml/yml/mvh-intent or
  unfenced from `# mvh-intent` / column-0 lower-case template key; existing YAML tolerances kept) > free text = notes verbatim.
- free text: notes = blocks (a heading + its content up to the next heading / template region / end), verbatim; never fields/rules.
  Interview echo: harness lines dropped, question titles kept as context only when user text follows; user remainders kept.
- new template key `voices:` (V1 = C1 Name map/list, or an integer singer count) -> also feeds voices stage.
- voices/intent.py becomes an adapter over meaning.intent (template + viewer block only) - UD1 applies to every reader.
- synth fixture INTENT_MD (tests/synth/song/folder.py) -> template + free-text story; rebuild synth (~20 s).
- advisory open question when free-text notes mention never/avoid/don't (no rule is created).
- contract: D78 (UD1) in CONTRACT.md; version bump coordinate with ud2-kick (check docs/build/progress/ud2-kick.md).

## Coordination with ud2-kick (read this, ud2)
- ud1 EDITS (targeted Edit only, please re-read before editing): src/mvh/stages/brief/build.py `_meaning_block` (notes/do_not
  lines), skill/mv-harness/SKILL.md meaning section, tests/synth/song/folder.py `INTENT_MD` only; synth fixture rebuilt by ud1.
- Contract version bump: proposal = ud2-kick does the ONE patch bump (it edits the lib/golden files that carry the version);
  ud1 adds decision D78 (UD1) only. If ud2's progress has not recorded the bump when ud1 finishes, ud1 bumps and says so here.
- D-numbers: ud1 takes D78; ud2 please take D79+.

## Done (milestone 1, code)
- intent.py rewritten (head/layer2/tail assembled; backup of v3 in scratchpad intent_v3_backup.py), interview_text.py (shared
  harness sentences), docs.py (preamble/questions/template v2 + voices line), stage.py (rule-like advisory, draft rule text),
  voices/intent.py adapter, brief _meaning_block notes, stage versions meaning 1.1.0 brief 1.1.0 voices 1.2.0.
- tests/synth/song/folder.py INTENT_MD -> template + prose; synth rebuilt (python -m tests.synth.build --only synth, 19 s).
- tests/unit/meaning/test_intent.py + test_intent_grammar.py rewritten: 167 pass.
## Next
- test_intent_grammar_v3.py (interview copy), new property test, test_merge/test_singing_truth, voices tests, review tests,
  SKILL.md, UD1.md, CONTRACT D78, real runs, gate.
- [milestone 2] unit meaning: test_intent, test_intent_grammar, test_intent_grammar_v3 (interview copy) rewritten,
  test_intent_property.py added (300 template parses, 40 interview round trips, 200 free-text docs), singing_truth to
  template: 820 pass. Grammar fixes found by the property test: '#' inside keys ('chorus#2:'), '- x:' item keeps colon.
- Next: voices unit + integration tests, review M6b rewrite, SKILL.md, UD1.md, CONTRACT D78, real runs, gate.
- [milestone 3] voices unit/integration tests updated (template only); review M6b r-contract (26) + r-words (74) rewritten
  and passing. Next: SKILL.md, UD1.md, CONTRACT D78 + skill sync, ruff, gen --check, real runs, gate.
- [milestone 4] SKILL.md, UD1.md, CONTRACT D78 (+ line 983), catalog: meaning opt notes/references/field_sources/intent_form +
  intent.md description; gen + gen --check OK; skill CONTRACT copy synced; ruff clean; brief unit test for notes added (13 pass).
- Next: real runs (meaning, brief on synth + 2 real songs), M6b gate, report.
- [milestone 5] real runs: `mvh analyze --only meaning,brief` refuses on the integrator copies (ud2's spectral 1.3.0 makes
  every downstream stage stale), so the real stages ran through DevRun (mvh.runner.child.run_stage) on copies in
  out/_wip/ud1-meaning/<slug> (synth, newton-vs-nye, megafauna) x 5 intent cases; scratch script ud1_runs.py; results
  out/_wip/ud1-meaning/ud1_runs.json: schema 0 errors everywhere, untouched template = pending, free text = notes only,
  template = fields + rules, no hook quote in notes, brief 1294-1732 tokens.
- Next: gate M6b (background, log docs/build/progress/ud1-meaning.gate.log), report.
- [milestone 6] gate M6b run 1 (log ud1-meaning.gate.log): fixture/review/ruff/contract/validate/e2e/lib-node PASS; unit FAIL
  only test_skill copy stale (ud2 editing CONTRACT.md); determinism FAIL on brief.md, lib/mvh.d.ts, lib/mvh_load.py,
  manifest.json = ud2's concurrent lib/brief/finalize edits between the two analyze runs. meaning+brief determinism
  checked separately (scratch ud1_det.py: synth + newton, fixture + free intents, 0 differing files). Skill copy re-synced.
  llm_draft SYSTEM prompt mentions notes vs template. Report written (docs/build/reports/ud1-meaning.md).
- gate run 2 started (log ud1-meaning.gate2.log).
- [DONE] gate run 2: all PASS incl. determinism (0/183) except unit test_skill (skill CONTRACT copy stale: ud2 editing
  CONTRACT.md) and ruff (ud2's finalize.py line length). Report final: docs/build/reports/ud1-meaning.md.
  If resumed: nothing left for ud1 except re-running `python skill/mv-harness/scripts/sync_contract.py` after ud2's last
  CONTRACT edit (ud2's plan does this).
