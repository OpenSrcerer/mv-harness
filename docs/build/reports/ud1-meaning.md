# ud1-meaning report (W4 phase 0, user decision UD1: the meaning input format)

## Result
UD1 is implemented. `meaning/intent.md` is read in exactly two ways plus the viewer block, by one parser that both
readers (meaning, voices) use:
1. **the interview template** (fenced or unfenced, one documented tolerant grammar "mvh-intent v2"): the only source of
   structured fields and of do-not rules;
2. **free text**: the user's notes, verbatim, `field_sources.notes = user`, never parsed into a field or a rule;
3. the viewer's managed block (M6a grammar) wins as the latest edit.
The heuristic markdown guessing (bold labels, colon labels, "Avoid..." / "Never show" headings, title-word do-not
detection, character / voice / section / line-singer lines in prose, the voices stage's own regexes) is deleted.
interview.md, request.md, SKILL.md and brief.md say "anything that must be obeyed goes in the template".
Contract: **D78** in docs/CONTRACT.md; details in docs/contract/decisions/UD1.md.

## What changed (files)
- `src/mvh/stages/meaning/intent.py`: rewritten (grammar in the docstring). Kept: template regions + YAML tolerances.
  New: `voices:` key (`V1: C1 Name`, `- V1 = C1 Name`, or a singer count), free text -> notes (heading blocks), interview
  copy recognition from shared sentences, failed template entries / unknown keys kept verbatim as notes (warned),
  `RULE_WORDS` (advisory only), `free_text_notes()`. Fixes found by the new property test: a `#` inside a map key
  (`chorus#2:`) and a bare list item `- x:` (kept its colon).
- `src/mvh/stages/meaning/interview_text.py` (new): the interview's fixed sentences, shared by writer and reader.
- `src/mvh/stages/meaning/docs.py`: interview preamble / questions / template intro say where obeyed answers go;
  template v2 (`# Anything that must be obeyed goes here ...`, `voices:` line); request.md explains notes vs template;
  meaning.md shows every note as a block quote.
- `src/mvh/stages/meaning/stage.py`: open question when a free-text note reads like a rule (note numbers only, never the
  text); draft do-not suggestions point at the template. `llm_draft.py` system prompt: notes are not rules.
- `src/mvh/stages/voices/intent.py`: adapter over the meaning parser (template + viewer block only); D51/D69 floor
  unchanged; free-text counts and mappings removed (they are notes for both stages, so the two never disagree).
- `src/mvh/stages/brief/build.py` `_meaning_block`: "User notes (N, user-authored ...; direction, never rules)" with the
  notes verbatim up to 120 words, do-not line names the template, the "Anything that must be obeyed ..." line.
- Stage versions: meaning 1.1.0, brief 1.1.0, voices 1.2.0.
- Contract: `src/mvh/contract/catalog.py` meaning schema documents optional `notes`, `references`, `field_sources`,
  `intent_form`; the `meaning/intent.md` file description; regenerated schemas (`gen --check` passes); docs/CONTRACT.md
  D78 + the meaning-files paragraph; skill CONTRACT copy synced. The version bump to 1.0.0-rc.3 is done ONCE by ud2-kick
  (agreed in the progress files).
- `skill/mv-harness/SKILL.md` meaning rule.
- Fixture: `tests/synth/song/folder.py` `INTENT_MD` is a template plus prose; synth rebuilt (`--only synth`, 19 s).

## Tests
- Rewritten to the new rule (free text is preserved as notes, never silently dropped, never a field / rule / `*`):
  tests/review/M6b/r-contract/test_r2_template_in_context.py (R2-3), test_r3_intent_parsing.py (R3-3, R3-4);
  tests/review/M6b/r-words/test_rw2_intent_reopened.py (N2, N4), test_rw3_do_not_overcapture.py, test_rw4_do_not_recall.py,
  test_rw4_interview_copy.py, test_rw5_bold_colon_labels.py, test_rw5_do_not_headings.py, test_rw5_voice_answers.py,
  test_rw_intent_parsing.py (F3). Template round-trip / hex / fence / untouched-template tests kept unchanged.
  No W3 critic test is meaning-related (feel, grooves, handoffs, hats), so none was touched.
- Unit: tests/unit/meaning/test_intent.py, test_intent_grammar.py (variants: 5 palettes x 4 wraps x 5 surroundings,
  5 voice-mapping styles incl. 'V1 = C1 Name', untouched template x 4 wraps x 3 shapes, free-text cases, tolerances),
  test_intent_grammar_v3.py (interview copy: 3 shapes x 5 layouts x 2 extents, untouched copy, sync guard on every
  interview line, keys answered with bullets, hint comments), test_singing_truth.py (template forms), new
  **test_intent_property.py** (300 generated template answer sets parsed exactly; 40 generated sets round-tripped through
  build -> interview template -> build with a fixed point; 200 generated free-text documents give notes only, every
  line kept); tests/unit/brief/test_brief.py (+ notes / obey line); tests/unit/voices/test_voices_logic.py (template).
- Results: unit meaning 820 pass (4 real skipped), brief 13 pass, contract 90 pass, review M6b r-contract 26 + r-words 74
  pass (was 24 failing), voices logic + M5 seam + viewer intent block pass, ruff clean, `gen --check` OK.
- Gate `scripts\gate.ps1 M6b`: see "Gate" below.

## Runs (meaning + brief, real stage code)
`mvh analyze --only meaning,brief` refuses on copies of the integrator's max folders because ud2-kick's spectral 1.3.0
makes every downstream stage stale, so the stages ran through `DevRun` (`mvh.runner.child.run_stage`, same Ctx, Writer,
schema checks) on copies in `out/_wip/ud1-meaning/<slug>` for synth, newton-vs-nye and megafauna, each with five
intent.md cases (results `out/_wip/ud1-meaning/ud1_runs.json`, outputs `out/_wip/ud1-meaning/_dev/<slug>/<case>/song`):

| case | status | intent_form | user fields | notes | do_not | schema errors |
|---|---|---|---|---|---|---|
| none | pending | none | - | 0 | 0 | 0 |
| template + notes | user | yaml+text | logline, notes, palette (+ C1 via `voices:`, S02 feel) | 2 | 2 | 0 |
| free text only | user | text | notes | 2 | 0 | 0 |
| interview copy with answers | user | text | notes | 2 | 0 | 0 |
| untouched template | pending | yaml | - | 0 | 0 | 0 |

Identical on all three songs. brief.md 1294-1732 tokens (cap 4000); the obey line is in every brief; no hook quote of
the interview leaked into a note; a rule-like note raises the open question.

## Gate (`scripts\gate.ps1 M6b`, run twice while ud2-kick was editing in parallel)
| step | run 1 (ud1-meaning.gate.log) | run 2 (ud1-meaning.gate2.log) |
|---|---|---|
| fixture | PASS | PASS |
| unit | FAIL: only test_skill `references/CONTRACT.md is stale` (ud2 edited docs/CONTRACT.md after my sync); contract, meaning, frames 0 | same single failure, same cause |
| review (M6b, m6b) | PASS (was 24 failing) | PASS |
| ruff | PASS | FAIL: line-too-long in src/mvh/runner/finalize.py 156-157 (ud2's in-progress D79 code) |
| contract (gen --check) | PASS | PASS |
| validate | PASS | PASS |
| e2e | PASS | PASS |
| lib-node | PASS | PASS |
| determinism | FAIL: brief.md, lib/mvh.d.ts, lib/mvh_load.py, manifest.json (ud2 changed lib / brief / finalize between the two analyze runs) | **PASS (0 of 183 files differ)** |

Every M6b-owned step passes; the remaining failures are ud2-kick's unfinished work (it re-syncs the skill copy and
finishes finalize.py by its plan). Independently, meaning + brief were run twice through the real stages on synth and
newton-vs-nye with two intents each: 0 differing files (scratch `ud1_det.py`).

## Open issues / notes for the reviewers
- `tests/unit/brief/test_skill.py::test_contract_copy_is_current` fails while ud2-kick is still editing docs/CONTRACT.md
  (D79); the skill copy must be re-synced after ud2's last CONTRACT edit (`python skill/mv-harness/scripts/sync_contract.py`).
- docs/contract/decisions/M6b.md still documents the old intent grammar (not in my paths): UD1.md / D78 supersede it.
  docs/SEAMS.md "M6b r-words R5-1..R5-4" can be closed.
- The voices stage's intent reading changed (prose counts like "voices: 4" or "## Characters" bullet counts are no
  longer read); real folders had no intent.md, so no real output changes. `test_voices_synth_models.py` (heavy) still
  expects `n_source = intent` from the synth fixture's template (2 characters).
