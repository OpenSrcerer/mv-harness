# fixer-m6b-r4: M6b W3 module fix, round 2

## Summary
The 8 round-3 findings listed in the brief (R-CONTRACT R3-1..R3-5 and R-WORDS R3-1..R3-3) were already fixed in
round 1 (fixer-m6b-r3), and their tests still pass. In round 4 the verifier (r-words-m6b-r4) found 3 new majors, with
14 failing tests:
- R4-1: a template key followed by markdown bullets is silently dropped.
- R4-2: do-not headings and bulleted do-not labels are not read as rules (recall).
- R4-3: an interview.md copied into intent.md and answered there turns the harness's own text into claims.
It also reported minors m16, m17 and m18.

All of them are fixed in the grammar itself, now "THE INTENT GRAMMAR (v3)" in the docstring of
`src/mvh/stages/meaning/intent.py`. No fix is a test-specific special case. A new property-style test,
`tests/unit/meaning/test_intent_grammar_v3.py` (120 cases), covers the variants the earlier tests missed. No
tests/integration/M6b seams were routed to M6b.

## Changes (owned paths only)
### `src/mvh/stages/meaning/intent.py` (grammar v3)
- **Layer 2, template keys answered with bullets (R4-1).** `_list_answer` covers `characters:`, `sections:`,
  `line_singers:` and `perspective:` when the value is a YAML list.
  - A `- key: value` item is that map entry.
  - A text item is read by the key's free-text rule: a character line, per-line singers or section notes.
  - An item that matches nothing is kept in `notes`, with a warning.
  - A string value for a character (`C1: The Keeper = V1`) is read as a character line, so its voices are found.
- **Template hints (m17).** The template's own hint comments (`TEMPLATE_HINTS`) are comments whatever the spacing
  before them. `palette: #c93523 # hex (#1b2a49) ...` no longer adds #1b2a49.
- **Rule 0, interview echo (R4-3).** A question line from `interview.md` (`_IV_QUESTIONS`) whose remainder is the
  harness's own text, or is empty, becomes a heading for the answer below it.
  - Block classes: meaning -> story, the world -> setting, colours -> palette, never show -> do-not, any other
    question -> notes.
  - Text after the harness's part of the line is the answer. Dynamic questions end at their fixed closing text, so an
    answer written inline after them is kept too.
  - The preamble, the status line, "Already answered", the voice-fact bullets and `## Open questions` bullets are
    never claims.
  - A question line with any other remainder is the user's own label: `9. **Never show**: blood` is the rule `blood`.
- **Rule 1, do-not headings (R4-2).** Besides a whole do-not phrase, a heading made only of do-not vocabulary is a
  do-not heading: at least one trigger word plus filler words.
  - Now read as do-not: `What I don't want`, `Avoid these`, `Things I never want to see`, `Never show these`.
  - Still not do-not: `Never Let Me Go`, `Don't Stop Me Now: my notes`, `The story: a night that never ends`,
    `Avoiding the obvious`, `Never Again`, `Things to do`.
- **Rule 1, palette headings.** A new `Palette` / `Colours` heading class: each item is a colour.
- **Rule 3, do-not labels (R4-2).** Labels may be bullets or numbered: `- Never show: X`, `* **Never show**: X`,
  `9. **Never show**: X`, `1) Do not: X`.
  - A bare label that is itself a bullet lists the bullets indented under it.
  - When the first bullet after it is at the label's own level, it lists the bullets at that level instead.
- **Field labels.** `The world:` is now a field label.

### Other files
- `src/mvh/stages/brief/build.py` (m18): one line, `User notes (meaning/meaning.json notes, references): N note(s)
  "..." · M reference(s) ...`. It shows at most 3 of each, shortened, with counts from meaning.json, and appears only
  when notes or references exist.
- `skill/mv-harness/SKILL.md` §3 mentions `notes` and `references`.
- `skill/mv-harness/references/RECIPES.md` (m16): `isDraft` is now `=== 'draft'`, so an `audio` source is a measured
  fact, not a draft.
- `docs/contract/decisions/M6b.md` has a new section, "W3 round 2 (fixer-m6b-r4): intent grammar v3".
- `tests/unit/meaning/test_intent_grammar_v3.py` covers:
  - answers under copied questions: 3 song shapes x 5 answer layouts (indented, flush, blank line between, inline,
    bullet) x 2 copy extents. Each case checks logline, summary, setting, palette and the do-not rule, and that no
    harness text becomes a claim.
  - an untouched interview copy: 3 shapes x with/without a draft x 3 cuts. It must stay pending or draft with no user
    fields.
  - a sync guard: every numbered question that `docs.interview_md` writes is a rule-0 question.
  - the interview answers' round trip through the template.
  - key lists: 4 keys x 5 wrappings.
  - do-not heading vocabulary, both positive and negative.
  - bulleted labels x 3 surroundings, and bare bulleted labels.
  - the template hint comments being known to the parser, and hint spacing x fence.

## Tests
- Before: tests/review/M6b had 14 failing tests (test_rw4_key_lists, test_rw4_do_not_recall,
  test_rw4_interview_copy).
- After, tests/review/M6b plus tests/unit/{meaning,brief,frames}: all pass (420 with the new file), 12 skipped
  (real-song tests, opt-in).
- tests/unit/{voices,viewer}, tests/review/M5 and tests/integration/M5 (the voices stage uses meaning's parser): no
  failure caused by M6b. The 3 failing tests in tests/integration/M5 are M5 real-song checks of lyrics and lipsync
  output (`test_real_versatile_mouth_stays_closed`, `test_real_jeremy_*`). They do not use the intent parser.
- `ruff check` on the M6b paths is clean.

## Real songs
`mvh analyze <copy> --only meaning,brief,frames --force meaning,brief,frames` on a copy of `out/_wip/integrator/synth`
still refuses: every upstream stage is "stale" there. The integrator ran at 05:10, and other modules have changed their
code or params since. So, as in round 1, I ran the real stage code through `mvh.stages.meaning.devrun.DevRun`, which
uses `runner.child.run_stage`, with `out/_wip/integrator/<slug>` as upstream.
- Script: scratchpad `m6b_r4_devrun.py`.
- Outputs: `out/_wip/fixer-m6b-r4/dev/<slug>`.
- Log: `out/_wip/fixer-m6b-r4/devrun.log`.

| song | stages | frames 24 / 24000/1001 | template round trip | interview Q&A copy | untouched interview copy |
|---|---|---|---|---|---|
| synth | ok, 0 warnings | 1356 / 1355 rows, 0 NaN | ok, fixed point | ok, 0 notes, 0 warnings | pending, no user fields |
| megafauna | ok | 5214 / 5209, 0 NaN | ok | ok | pending, no user fields |
| versatile | ok | 5466 / 5461, 0 NaN | ok | ok | pending, no user fields |
| newton-vs-nye | ok | 4091 / 4087, 0 NaN | ok | ok | pending, no user fields |
| jeremy | ok | 7599 / 7591, 0 NaN | ok | ok | pending, no user fields |

**Comparison with the integrator, without an intent (the baseline):** there is no regression. The only differences are
the additive ones round 1 already reported:
- meaning.json gains `references` and `notes`;
- interview.md gains 3 template lines;
- the provenance keys differ (DevRun);
- 2 brief lines differ: the flags line, because DevRun's stubs carry no upstream fallbacks.

lines.tsv, the singing.json items, input.json, orphans.json, meaning.md and request.md are identical to the
integrator's. Against round 1's baseline (`out/_wip/fixer-m6b-r3/dev/<slug>/baseline`), every M6b file on all 5 songs
is byte-identical, brief.md included. No lyric text was printed.

## Gate (`scripts\gate.ps1 M6b`, exit 1; log in out/_wip/fixer-m6b-r4/gate.log)

| step | result | owner of the failure |
|---|---|---|
| fixture | PASS | |
| unit | FAIL | Only tests/unit/contract fails, with the same 2 tests as in round 1. `test_deps_match_plan`: vocals now depends on lyrics, which PLAN_DEPS does not list. `test_generated_artifacts_up_to_date`: docs/CONTRACT.md is stale. Both belong to the integrator or the contract owner. The M6b unit tests (meaning, brief, frames) PASS. |
| review | PASS | tests/review/M6b: all pass |
| ruff | PASS | |
| contract | FAIL | `mvh.contract.gen --check`: docs/CONTRACT.md is out of date (integrator) |
| validate | PASS | |
| e2e | PASS | 1198 s |
| lib-node | PASS | |
| determinism | FAIL | 25 of 181 files differ: curves/core.f32, drum_hits, beats.csv, sections, voice_spans, lyrics, visemes, ... (upstream GPU/separation nondeterminism). meaning.json and singing.json follow from the upstream voice_spans and lyrics. brief.md, meaning.md, interview.md and lines.tsv are not in the list. |

M6b determinism with identical upstream: two DevRuns of meaning, brief and frames each give byte-identical files, 12 on
synth (with the fixture's intent.md) and 11 on newton-vs-nye (scratchpad det_m6b_r4.py,
out/_wip/fixer-m6b-r4/det). Every failing gate step belongs to another module or to the integrator. No M6b test fails.
