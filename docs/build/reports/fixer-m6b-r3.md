# fixer-m6b-r3: M6b W3 module fix, round 1

## Summary
All 8 open W2 majors for M6b (R-CONTRACT R3-1..R3-5, R-WORDS R3-1..R3-3) are fixed with real changes. The intent.md
parsing heuristics were replaced by ONE documented grammar ("THE INTENT GRAMMAR (v2)", the docstring of
`src/mvh/stages/meaning/intent.py`), and the interview template now round-trips through it exactly. A new property-style
unit test (`tests/unit/meaning/test_intent_grammar.py`, 145 cases) checks the round trip and the template variants.
No tests/integration/M6b seams were routed to M6b.

## Changes (owned paths only)
- `src/mvh/stages/meaning/intent.py`: rewritten around the grammar.
  - Layer 1 is the viewer block (M6a V7 grammar, unchanged, wins).
  - Layer 2 is template regions. A region is fenced (the closing fence is optional) or unfenced (from `# mvh-intent` or a
    column-0 lower-case template key, over template-shaped lines only). Parsing is YAML with three tolerances:
    - a hex colour that starts a value is a value;
    - a `#` comment needs 2+ spaces, a tab, or a closed flow/quoted value before it;
    - plain values that YAML would misread are quoted first.
    A region that still fails is parsed per key and per nested entry. A failing entry gives a warning and is read as
    free text, with comments removed and never as prose.
  - Layer 3 is line-classified free text, where the first rule that matches wins:
    - a do-not heading must be a whole do-not phrase (anchored), so `# Never Let Me Go` is not one;
    - an inline do-not label is one rule;
    - a bare label lists only the bullets below it;
    - field labels such as `Logline:`, `Narrator:` and `Notes:` are recognised;
    - any unmatched user text is kept in `notes`.
- `src/mvh/stages/meaning/docs.py`:
  - `yaml_template` writes back every user claim: motifs, symbolism, references, notes, each section's own `do_not`,
    and newlines as `\n`.
  - A third header comment explains how to type hex colours and comments. The review tests' preconditions are kept
    verbatim: `palette: []   # hex (#1b2a49) ...` and `{L005: C1+C2}`.
  - meaning.md labels a draft narrator or addressee `(draft)` and lists References and Notes.
- `src/mvh/stages/meaning/stage.py`: the top-level `field_sources` now has `perspective.narrator` and
  `perspective.addressee` (user or draft), plus `references` and `notes`. meaning.json gains the additive `references`
  and `notes` fields, and both count as user answers.
- `skill/mv-harness/SKILL.md` and `references/RECIPES.md` say that perspective has per-part field_sources.
- `docs/contract/decisions/M6b.md` has a new section, "W3 round 1": the grammar, the additive fields and the round trip.
- `tests/unit/meaning/test_intent_grammar.py` is new and covers:
  - an exact round trip plus a fixed point (the template of the template is identical) for three intents: the free-text
    fixture, a full YAML file and a labels-only file;
  - 4 wrappings (fenced, unfenced, unclosed fence, no marker) x 5 palette spellings x 5 surroundings, each checking that
    every answer is kept and that no template comment becomes a claim;
  - the untouched template, which must stay pending (3 song shapes x 4 wrappings);
  - a do-not detection table, `tolerant_yaml_line` cases, and a broken entry that is warned about while the rest is kept.

## Tests
- Before: tests/review/M6b had 18 failing and 123 passing.
- After:
  - tests/review/M6b plus tests/unit/{meaning,brief,frames}: 141 passed, 12 skipped (real-song tests, opt-in).
  - With the new grammar test and tests/unit/{voices,viewer}: 347 passed, 12 skipped.
  - tests/integration/M5/test_voices_intent_seams.py plus tests/review/M5 (the voices stage uses meaning's parser): 56
    passed, 3 skipped.
- `ruff check` on the M6b paths is clean.
- Gate: see the bottom of this report.

## Real songs
`mvh analyze <copy> --only meaning,brief,frames --force meaning,brief,frames` cannot run on copies of the integrator
folders. `structure` became stale there because the M2 fixer changed its params (bar_jitter_frames,
impact_snap_strength, short_section_margin), and that cascades to every downstream stage, so `--only` refuses. Re-running
the whole chain on four real songs would need the heavy slots the other fixers and the gate are using. Instead I used
`mvh.stages.meaning.devrun.DevRun`. It runs the real meaning, brief and frames code through
`mvh.runner.child.run_stage`, exactly as the runner does, with `out/_wip/integrator/<slug>` as upstream. The scripts and
log are in the scratchpad (devrun_songs.py, cmp_songs.py) and in out/_wip/fixer-m6b-r3/devrun.log.

| song | meaning / brief / frames | vs integrator | frames 24 and 24000/1001 | template round trip |
|---|---|---|---|---|
| synth | ok / ok / ok, 0 warnings | additive only | 1356 / 1355 rows, 0 NaN | ok, fixed point |
| megafauna | ok / ok / ok | additive only | 5214 / 5209 rows, 0 NaN | ok |
| versatile | ok / ok / ok | additive only | 5466 / 5461 rows, 0 NaN | ok |
| newton-vs-nye | ok / ok / ok | additive only | 4091 / 4087 rows, 0 NaN | ok |
| jeremy | ok / ok / ok | additive only | 7599 / 7591 rows, 0 NaN | ok |

The integrator's folders have no intent.md, so the baseline comparison has no intent. The only differences from the
integrator's outputs are:
- meaning.json gains `references` and `notes`;
- interview.md gains 3 template lines;
- the provenance keys differ (DevRun uses fake keys);
- brief.md's flags line lists fewer flags, because DevRun's upstream stubs carry no upstream fallback records (a harness
  artefact).

lines.tsv, singing.json items, input.json, orphans.json, meaning.md and request.md are identical. No regression was
found.

For the round trip, each song's own interview template was filled with a logline, `palette: [#c93523, night blue]`, a
do_not rule and one S01/S02 feel. It was written unfenced, with a `## Notes` / `Chorus:` note after it. Every song came
back with status user, form yaml+text, 0 warnings and none of the template comment's #1b2a49. The template of the
result kept the same claims.

## Gate (`scripts\gate.ps1 M6b`, exit 1; log in out/_wip/fixer-m6b-r3/gate.log)

| step | result | owner of the failure |
|---|---|---|
| fixture | PASS | |
| unit | FAIL | Only tests/unit/contract fails, with 2 tests, neither M6b's. `test_deps_match_plan`: the vocals stage now depends on lyrics, which PLAN_DEPS does not list. `test_generated_artifacts_up_to_date`: docs/CONTRACT.md is out of date. Both come from another module's spec change in this round. The M6b unit tests (meaning 175, brief 12, frames 42) PASS. |
| review | PASS | tests/review/M6b: 57/57 |
| ruff | FAIL | src/mvh/stages/structure/__init__.py:260 (unused `S_list`) and src/mvh/stages/vocals/__init__.py:86 (unsorted imports): M2 and M3a/M5 edits made during this round. The M6b paths are clean. |
| contract | FAIL | docs/CONTRACT.md is out of date (`mvh.contract.gen --check`); this is the integrator's job. |
| validate | PASS | |
| e2e | PASS | 1350 s, slowed by contention for the heavy slots |
| lib-node | PASS | |
| determinism | FAIL | 69 of 181 files differ, starting at stems/*.flac and meta/separation.json (GPU separation). The difference cascades to every downstream file. brief.md, meaning.md and interview.md are not in the list. |

M6b determinism was checked separately, with identical upstream: two DevRuns of meaning, brief and frames on synth (with
the fixture's intent.md) and on newton-vs-nye are byte-identical (12 and 11 files). The meaning.json, input.json,
singing.json and lines.tsv differences in the gate come from the upstream lyrics and voices differences.

All failing gate steps belong to other modules or the integrator. No M6b test fails.
