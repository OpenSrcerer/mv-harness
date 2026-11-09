# W4 verify-words, round 2 (w4verify-words-r2): independent check of the w4fix-words-r2 fixes (M6b intent.py)

Verdict: **pass-with-fixes**. The fixes for VWU1-a and VWU1-b work for every shape that round 1 reported, and for the
similar cases I tried. I found no regression in the words stages on the synth song or on three real songs.

Still open:
- one residual path of VWU1-a (minor);
- two similar minor cases;
- one gate break in an M6b unit test (major; the cause is another fixer's change, and one command fixes it).

Failing tests:
- `tests/review/W4/verify-words/test_w4vw_r2_ud1.py`: 10 fail, 1 control passes.
- `test_w4vw_r2_skill_copy.py`: 1 fails.

The round-1 file `test_w4vw_ud1_do_not.py` now passes 6/6.

## Status of the round-1 findings

### VWU1-a (stray `key: value` line under a list key): fixed, with one residual path (VWR2-1)

- **Parser probes** (`out/_wip/w4verify-words-r2/probes/p1.py`). I tried a stray line placed:
  - after, before or between the items;
  - twice in one list;
  - as a nested `chorus:` block;
  - inside a tab-indented list;
  - under symbolism, themes, palette, motifs and references.

  In every case:
  - every `- ` item is kept;
  - the stray line is kept verbatim as a note;
  - a warning is raised and the key is recorded in `unparsed_keys`.

  `notes` keeps both forms with no warning. The map keys (characters, voices, sections, line_singers) keep both forms
  when entries are mixed with bullets.
- **End to end.** I drove meaning and brief on the synth fixture intent plus the line `  Also: lots of fog please`.
  - Both rules stay in meaning.json.
  - `intent_unparsed == [{do_not, 1}]`.
  - The first open question and the brief.md line report it.
  - No fog rule appears.
- **No test-specific code.** The fix is a general `_LIST_KEYS` branch in `_load_region`.

### VWU1-b (`-<TAB>item` at column 0): fixed

The fix is `_COL0_ITEM = ^-(?:[ \t]|$)` in `_scan_unfenced`. It works with:
- blank lines between items;
- CRLF line endings;
- two tabs after the dash;
- a list that mixes `- ` and `-<TAB>`;
- an unclosed ```` ```yaml ```` fence;
- a template key on the next line;
- the same shape under symbolism.

## Findings

### VWR2-1 (minor, residual of VWU1-a): when every `- ` item fails, a stray line still becomes the only hard rule
- **Location:** `src/mvh/stages/meaning/intent.py`, `_load_region`, the line
  `elif sub or subl: merged[key] = sub if sub else subl`.
- **Cause:** the round-2 rule says that a bare `key: value` line among a list key's entries is a note. That rule applies
  only when both `sub` and `subl` are non-empty.
  - Suppose the only typed item fails, for example through an unclosed quote. The fixture itself quotes its rules this
    way: `- "No text on screen ...`.
  - Then `subl` is empty, and the stray line is promoted to a rule.
- **Input:** `do_not:` / `  - "No text on screen except the lyrics.` / `  Also: lots of fog please`.
- **Result** (end to end, in `out/_wip/w4verify-words-r2/synth_vwr21s`):
  - meaning.json has `do_not == ["Also: lots of fog please"]`;
  - brief.md lists it as a do-not rule;
  - the warning and the open question name the broken item, never the promoted wish, so an agent would avoid fog.

  With two items of which one parses (`synth_vwr21`), the fix works.
- **Fix:** for the keys in `_LIST_KEYS` other than notes, always treat a map entry as a warned note, whether or not a
  `- ` item survived. One way is to take the list-key branch whenever `sub` is non-empty, not only when both `sub` and
  `subl` are.
- **Tests:**
  - `test_vwr2_1_stray_line_never_becomes_a_rule_when_the_items_fail[unclosed_quote|unclosed_bracket|section_line]`
  - `test_vwr2_1_same_stray_line_same_outcome`

### VWR2-2 (minor): `* rule`, `• rule`, `– rule` and `-<NBSP>rule` under `do_not:` silently become a note
- **Location:** `intent.py`, `_scan_unfenced`. The case is a valueless template key followed by a column-0 line that
  does not start with `-`.
- **Result:**
  - `do_not == []`, and the rules become one free-text note;
  - 0 warnings, and `unparsed_keys == []`;
  - the rule-word advisory catches only rules phrased with never, avoid or don't.

  VWU1-b fixed the same silent demotion for `-<TAB>`. These markers are common: Markdown users type `* `, and word
  processors autocorrect `- ` to `–` or `•`.
- **Fix:** read these markers as `- `. They are not valid YAML, so rewrite them in `_safe_lines`. At minimum, warn and
  record the key when a valueless list key is followed directly by bullet-like lines at column 0.
- **Tests:** `test_vwr2_2_rules_typed_as_other_bullets_are_at_least_surfaced[star|bullet|en_dash|dash_nbsp]`

### VWR2-3 (minor): a stray line indented deeper than its item takes that rule with it
- **Inputs:**
  - `  - show the singer's face` / `    Also: lots of fog please` / `  - use red light`;
  - a column-0 list followed by an indented `  Also: ...` line.
- **Result:**
  - `_chunks(entries=True)` splits entries only at the item's indent, so the stray line joins the item's entry.
  - The entry then fails YAML.
  - That rule is demoted to a note. The demotion is warned and recorded, but the grammar promises that one bad line
    never takes the other rules with it.
- **Fix:** inside a failing entry, retry the `- ` line on its own and demote only the continuation lines.
- **Tests:** `test_vwr2_3_a_deeper_stray_line_does_not_take_its_rule[indented_list|col0_list]`

### VWR2-4 (major, caused by another fixer): the M6b unit test `test_contract_copy_is_current` fails, so the M6b gate fails
- **Cause:** the platform fixer edited `docs/CONTRACT.md` at 19:46 for W4VP-1. The generated copy
  `skill/mv-harness/references/CONTRACT.md` (15:28) was not regenerated.
- The w4fix-words-r2 gate ran its unit step before that edit, so its log shows PASS. The test fails now.
- **Fix:** run `python skill/mv-harness/scripts/sync_contract.py`, then re-run the unit step (tests/unit/brief).
- **Test:** `test_w4vw_r2_skill_copy.py::test_vwr2_4_skill_contract_copy_is_current`

## Regression hunt

Only `src/mvh/stages/meaning/intent.py` changed after round 1.

I re-drove the words stages in process (voices, then lipsync, meaning and brief) on the cached upstream of
`out/_wip/ud2-kick/<slug>`.
- Driver: `out/_wip/w4verify-words-r2/scripts/drive.sh`.
- Compare script: `scripts/cmp.py <slug> [tag]`.

| Song | Against w4fix-words-r2 | Against the integrator run |
|---|---|---|
| synth | All 18 files identical (JSON compared without provenance) | Differences only in `schema_version`, the new `intent_unparsed` field, `backing_unbacked_lines`, and the text of interview.md, request.md and schema.json |
| newton-vs-nye | All 20 identical | The same, plus the effects of the round-1 S16 voices fix: 55 → 54 spans, backing span L021 dropped; the mouth curve and phoneme/viseme counts change with it |
| jeremy | All 16 identical | The same differences as synth |

None of the real songs has an intent.md. So I also drove meaning and brief on the synth song with probe intents:
- probe song folders: `out/_wip/w4verify-words-r2/songdirs/`;
- probe intents: `probes/intent_*.md`;
- results: `probes/e2e.py`.

| Probe | Result |
|---|---|
| `_ctrl` (the fixture intent) | Clean: status user, 2 do_not rules, `intent_unparsed` empty, no open question |
| `_vwu1a`, `_vwr21` | Behave as described under VWU1-a and VWR2-1 |
| `_vwr21s` | Reproduces VWR2-1 |

Tests run:

| Suite | Result |
|---|---|
| tests/unit/meaning, tests/unit/brief, verify-words (before my r2 tests) | 853 pass, 1 fail (VWR2-4) |
| M6b review, adversary UD1, contract, frames, viewer | 288 pass |
| M5 review, voices, lipsync, lyrics | 138 pass |

ruff is clean on my tests.

The fixer's gate log shows a determinism FAIL. The differing files belong to other modules: other fixers were editing
rhythm, drums, dynamics and structure during the gate's `--force` runs. The words stages give the same output in my
run, the fixer's run and round 1.

---

# W4 verify-words, round 1 (w4verify-words-r1): independent check of the w4fix-words fixes (M5, M6b)

Verdict: **pass-with-fixes**. S16 is fixed. W4A-UD1 is only partly fixed: the three cases the adversary named now
work, but two ordinary ways of typing a do_not list still lose the hard rules without a word, and one of them is a
regression the fix introduced. Failing tests: `tests/review/W4/verify-words/test_w4vw_ud1_do_not.py` (5 fail, 1 control passes).

## Status of the findings

| id | status | evidence |
|---|---|---|
| W4A-S16 / S16 (M5 voices backing span, Newton L021) | **fixed** | My own re-run of voices -> lipsync -> meaning -> brief (same in-process driver as the fixer, cached upstream of `out/_wip/ud2-kick/<slug>`, outputs `out/_wip/w4verify-words-r1/<slug>/<stage>`). Newton: the backing span L021 (22 % backed) is gone, 0 backing spans; two per-voice mouths open (> 0.1, 100 Hz): 2.29 s -> 0.20 s in total, longest run 2.09 s -> 0.13 s (critic limit 1.5 s; my method gives 2.29 s on the old curves, matching the critic's 2.3 s). The 54 lead spans are identical to ud2-kick, the integrator run and the fixer run. The adversary test `test_w4a_backing_spans_are_backed_by_the_backing_stem_newton` passes on my run (`MVH_REVIEW_RUNS=out/_wip/w4verify-words-r1/review`). No test-specific code: the gate is a general support test on `stem_activity` backing_vocals (`voices/core.py backing_window`). |
| W4A-UD1 (M6b intent.py) | **partly fixed** | The adversary's 5 tests and the fixer's 10 pass. Tab-indented lists, blank line after `do_not:`, a trailing indented sentence, a bad item in the middle, CRLF, fenced blocks and section-level do_not with tabs all keep every rule. Two cases still fail: VWU1-a and VWU1-b below. |

## Findings

### VWU1-a (major, regression from the fix): a stray `key: value` line under do_not drops every rule and becomes the only hard rule
- Location: `src/mvh/stages/meaning/intent.py` `_load_region`, the per-entry branch: `merged[key] = sub if sub else subl`.
- Input: `do_not:` / `  - show the singer's face` / `  - use red light` / `  Also: lots of fog please` (or `  chorus: no close-ups`).
- Result: `do_not == ["Also: lots of fog please"]`; the two typed rules are gone; 0 warnings; `unparsed_keys == []`,
  so meaning.json `intent_unparsed`, the open question and the brief.md line say nothing.
- Before the fix (do_not was not in `_NESTED`) this input was demoted whole to a note WITH a warning. Now it is silent, and a wish is promoted to a hard constraint (inverts UD1).
- The same `sub`/`subl` mix affects the other keys newly added to `_NESTED` (symbolism, themes, notes, references, palette).
- Fix: for a list-valued key (do_not and the other list keys), a dict entry is one list item (`_item_text`), or keep both `subl` and `sub`; never let one discard the other. At least warn and record it in `unparsed_keys`.
- Tests: `test_vwu1a_rules_survive_a_stray_colon_line[wish_with_colon|section_rule_line]`, `test_vwu1a_a_wish_never_becomes_the_only_hard_rule`.

### VWU1-b (major, not fixed): `-<TAB>item` at column 0 is silently a note
- Location: `intent.py` `_scan_unfenced`: a column-0 item continues the region only if it starts with `"- "` (or is `-`).
- Input: `do_not:` / `-<TAB>show the singer's face` / `-<TAB>use red light`.
- Result: the region ends at `do_not:`; both rules become a free-text note; 0 warnings, `unparsed_keys == []`. This is the
  same silent demotion as the adversary's blank-line case. The fixer's claim "tabs between - and the item" holds only for
  an indented list (`  -<TAB>item` works).
- Fix: accept `-` followed by any whitespace (`re.match(r"-[ \t]", t)`) in `_scan_unfenced` (and anywhere else that tests `"- "`).
- Tests: `test_vwu1b_tab_after_dash_at_column_0_keeps_rules`, `test_vwu1b_tab_after_dash_at_column_0_is_at_least_surfaced`.

### Minors (no test)
- m1: meaning and brief keep stage version 1.1.0 although their output changed (meaning.json `intent_unparsed`, new parser
  behaviour, the brief.md line). The cache key holds the intent.md hash but not the code, so an existing song whose intent.md
  is unchanged keeps the old (demoted) parse after the upgrade. The rc.2 -> rc.3 contract bump hides it today. Bump both.
- m2: `tests/unit/meaning/test_intent_w4_do_not.py::test_demotion_reaches_meaning_json_and_the_brief` asserts
  `m["do_not"] == ["use red light"] or [...]`: the `or` makes it true for any non-empty list. Tighten it.
- m3: `do_not:<TAB>text` (tab after the colon) is demoted to a note (warned and surfaced, fine), and a list that mixes a
  2-space item with a tab item merges two rules into one (`"a - b"`, YAML continuation, no warning). Rule text is kept.
- Note: no real song has a true backing span (Jeremy/MEGAFAUNA/Versatile 0 before and after), so the backing gate's
  behaviour on a real, quiet harmony double is tested only on the synth fixture (3 spans, 100 % backed, kept).

## Regression hunt (numbers only)
| song | lead spans | backing spans | two mouths open total / longest | meaning | brief vs ud2-kick |
|---|---|---|---|---|---|
| synth | 9, identical | 3 -> 3 (100 % backed) | 8.44 / 1.11 s -> same (fixture duet) | same (+ `intent_unparsed: []`) | 0 lines changed |
| newton-vs-nye | 54, identical | 1 (22 %) -> 0 | 2.29 / 2.09 s -> 0.20 / 0.13 s | same | 2 rows: C1 lead (was both); S04 singer C3 (was C1+C3) |
| jeremy | 40, identical | 0 -> 0 | 0 | same | 0 |
| versatile | 0 | 0 -> 0 | 0 | same | 0 |

- My re-run vs the fixer's: voices and brief byte-identical; lipsync and meaning differ only in `provenance.key` (the
  driver hashes the output path), so the words stages are deterministic.
- Unit + review: `tests/unit/{voices,meaning,brief,lipsync}`, `tests/review/M5`, `tests/review/M6b`: 1039 passed, 11 skipped. ruff clean on the words paths.
