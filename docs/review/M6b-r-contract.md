# M6b review, R-CONTRACT lens ("the video agent"): minor findings

Reviewer: r-contract-m6b. Scope: meaning, brief, frames, skill/mv-harness. The blocker and the majors have failing tests under
`tests/review/M6b/r-contract/` and are listed in `docs/build/reports/r-contract-m6b.md`. Every item below was checked by running code
(DevRun outputs in `out/_wip/r-contract-m6b/dev/<fixture>/song`, scripts in `out/_wip/r-contract-m6b/*.py`).

Checked and fine (no finding): frames CSV parity with `conventions` (every curve cell, `t`, `cue_id`, `hit`, `section_id`, `count`,
`singer`) at 24, [24000, 1001], 24 with frame0 1, and 30 early, on synth, newton and jeremy, with row counts equal to
`frame_count` (jeremy 7599/7591/9498, the CONTRACT §2 worked example); no NaN anywhere. `singing.json` and `lines.tsv` match the synthetic
truth exactly (C1+C2 on the duet lines, D38). A strict per-block trace (every decimal must be a value of a file named in **its own**
block) finds 0 untraced decimals on synth (user+draft), newton, jeremy and megafauna. brief.md is 557-1220 tokens and the
`--section` zooms are at most 504 tokens (with `--lyrics`). With `lyrics_to_agents=false` no line text appears in interview.md,
request.md, input.json, meaning.md, brief.md or lines.tsv. A draft's `do_not` rules are not applied (they become open questions),
so "Do not (the user's words)" in brief.md is accurate.

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| m1 | src/mvh/stages/meaning (characters `voice_mapping`, decision A4) | `voice_mapping` says `user` for a link the user never made | real-jeremy (no intent.md, voices absent): `characters[0].voice_mapping = {"V1": "user"}` while `provenance = {source: audio, status: draft}`. A4 says the field "shows which voice->character links the user confirmed" | use `default` (or `proposed`) for the fallback single-voice mapping |
| m2 | meaning `characters[].line_ids` | not in sung order | real-jeremy C1 `line_ids` ends `..., "L038", "L040", "L039"` | sort line ids by their number (sung order, CONTRACT §3) |
| m3 | brief/build.py `section_facts` | the vocals cell and the lines cell of a section row use different membership rules, so a row can list a line with no singer or a singer with no line | real-newton: S01 lists `L001` but no character (singing item 13.7-15.26 s is < 50 % inside S01, which ends at 14.0); S09 shows `C2 79%` with lines `-` (L051 119.86-128.16 s is tagged S08 but mostly in S09) | derive the singers of a row from the singing items of the row's lines (or both from the same overlap rule) |
| m4 | brief/build.py, brief/trace.py | some brief numbers are not values of any file, and the gate's trace check skips some that are | the vocals `91%` share is an overlap the brief computes; voice seconds (`V1 20 s`) come from meta/voices.json, which the Meaning block does not name; `trace._STRIP` removes `A0.56 V0.39` (mood cells) as IDs, so mood values are never checked (they are correct today); integers and percentages are never checked | name meta/voices.json in the Meaning block; print the vocal share with its source or drop it; make the ID regex not swallow `A0.56`/`V0.39` (e.g. require a word boundary before a non-digit) |
| m5 | brief/build.py `_section_rows(compact=True)` | the compact layout drops the `instruments` column that CONTRACT §12 lists in the section row | `head` for compact has no instruments cell | keep a 1-instrument cell, or note the omission in the row header |
| m6 | skill/mv-harness/references/RECIPES.md | two field descriptions do not match the data | "`line.singer` lists the characters (`C1+C2`)": `lyricAt` returns an array `['C1','C2']` (the `C1+C2` string is the lines.tsv cell); "the palette words (`meaning.palette_names`)" is empty for drafts (only the user's colour words fill it) | say `line.singer` is an array; fall back to `meaning.palette` hex when `palette_names` is empty |
| m7 | RECIPES.md "Loading" | the generic include list does not cover the helpers the following recipes call (browser mode throws): `meaningAt` needs `events:sections`, `pulse('hit_points')`, `events('holds' / 'grooves' / 'edm_roles' / 'visemes')` | `HELPER_NEEDS` in lib/mvh.js; the "anything else: ensure" comment mitigates it (the Remotion recipe, which has no such comment, is major F1) | recommend `include: ['helper:count', 'helper:singerAt', 'helper:meaningAt', 'events:hit_points', ...]` |
| m8 | skill/mv-harness/references/CONTRACT.md | the generated copy keeps relative links that are dead under skill/ | lines 11-12: `](contract/golden-vectors.json)`, `](contract/golden-spec.md)` | rewrite them in `sync_contract.py` (repo-relative text, or drop the link) |
| m9 | frames/export.py `_is_rational` | a two-element list of rates is read as a rational when the ratio is in [1, 1000] | `parse_rules([60, 30])` -> one `60-30` (2 fps) export; `[24, 30]` -> two exports. Only reachable through `--param frames.fps=...` (the CLI passes dicts) | accept rationals only as strings (`"24000/1001"`) or `{num, den}`, or document the rule |
| m10 | meaning characters `lead_backing` | `both` is printed in brief.md (`(both)`) and written to meaning.json, but the contract only defines `lead`/`backing` (singing.json enum); the decisions file does not list `both` | synth C2 `lead_backing: "both"` | list `both` in docs/contract/decisions/M6b.md (additive value) or map it to `backing` |
| m11 | `mvh meaning` / SKILL.md | after a re-merge (new singer mapping), an existing `frames/<fps>fps.csv` keeps the old `singer` column; `mvh meaning` refreshes meaning, brief and viewer only, and SKILL.md does not tell the agent to re-export | stage list in meaning/cli.py `only = ["meaning", "brief"] (+ viewer)` | re-run `frames` when `frames/` exists (the recorded rules are in `.cache/_run.json`), or add the step to SKILL.md |

## Round 2 (r-contract-m6b-r2)

Re-check of the round-1 fixes plus new findings. The blocker/majors have failing tests under
`tests/review/M6b/r-contract/test_r2_*.py` and are listed in `docs/build/reports/r-contract-m6b-r2.md`. Probes:
`out/_wip/r-contract-m6b-r2/probe*.py`, `run_scen.py` (DevRun of meaning+brief on synth and the four real fixtures),
`recipes_all.mjs` (every RECIPES.md JS recipe in browser/URL mode with the include list it is told to use).

Verified fixed: r-contract F1 (the Remotion recipe now loads `helper:count/singerAt/meaningAt/lyricAt`; runs clean
in URL mode); r-words F2 (voices-stage proposals no longer add to a user-settled character); r-words F5 (stage
warnings carry no cited values; `kind_of` is a full match); r-words F6 (`cut_lyric_runs` walks every draft string,
also with curly vs straight apostrophes; logline capped at 40 words). brief.md on synth (user+draft) and the four real
fixtures: 557-1210 tokens, 0 untraced decimals (`mvh.stages.brief.trace`); zooms label every draft field.
Partially fixed (re-reported as majors): r-contract F3 (R2-2, R2-3 regression), r-contract F2 / r-words F1 (R2-4,
R2-5), r-words F4 (R2-1).

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| r2-m1 | meaning/stage.py characters `voice_ids` vs singing.json | with voices absent and the user writing `C1 The Keeper = voice V1`, meaning.json gives C1 `voice_ids: []`, `voice_mapping: {}`, while singing.json/lines.tsv map every line to V1 -> C1 | probe3.py (synth without voices): `('C1', 'The Keeper', [], {}, 10)`, singing voices `{V1: 10}` | when the default V1 is used, attach it to the user character that names V1 (or to the single user character) |
| r2-m2 | RECIPES.md "Loading" include list (round-1 m7, still open) | the generic list lacks `events:sections`, so `song.meaningAt(t)` in the "Palette and meaning" and "Camera on cues" recipes throws in browser mode; `pulse('hit_points')`, `events('holds'/'grooves'/'edm_roles'/'visemes')` also need `ensure` | recipes_all.mjs: `meaningAt: mvh: 'events:sections' is not loaded` | add `helper:meaningAt` (and `events:hit_points`) to the Loading include list |
| r2-m3 | brief/build.py `render_section` | meaning fields (feel/meaning/movement/camera) and do-not rules are printed in full; `compose(n)` only trims facts, so long user/draft text pushes a zoom over the 1.5k cap | probe8.py: 4 fields of ~234 words in S05 -> 1771 tokens | cut each meaning field to a word budget when over the cap, with a pointer to meaning.md |
| r2-m4 | round-1 minors still open | m1 (`voice_mapping: user` for the fallback V1 link; now also the cause of R2-1), m2 (`line_ids` not in sung order on real-jeremy), m6 (`line.singer` described as `C1+C2`, `palette_names` empty for drafts), m8 (2 dead `](contract/...)` links in the generated CONTRACT.md copy), m10 (`lead_backing: both` not in the decisions file), m11 (frames not refreshed by `mvh meaning`) | probe8.py; grep of RECIPES.md / CONTRACT.md / decisions/M6b.md | as in round 1 |
| r2-m5 | frames after `mvh analyze` (SKILL.md) | `frames` is on-demand: a later `mvh analyze` (after a correction) does not re-run it and does not remove the old `frames/<fps>fps.csv`; the manifest drops it from `files` but the stale CSV stays on disk and SKILL.md never says to re-export | runner/run.py `want` = analyze-trigger stages only; finalize.py skips non-OK on-demand stages; no unpublish | SKILL.md: "after every `mvh analyze`/`mvh meaning`, re-run `mvh frames` for the rates you use"; W3: re-run recorded frame exports, or unpublish stale on-demand outputs (change request) |

Gate (`scripts\gate.ps1 M6b`, log `out/_wip/r-contract-m6b-r2/gate.log`): review/ruff/contract/validate PASS; unit FAIL only on
`tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` (a W1 check that another module's stage is still a
stub; not M6b); the e2e run hits `spectral: failed - TypeError: select_kick_events() got an unexpected keyword argument
'excess_min'` (M1), so `frames` cannot run end to end today.

## Round 3 (r-contract-m6b-r3)

Re-check of the round-2 fixes (R2-1..R2-6, r-words N1..N6) plus new findings. Majors have failing tests under
`tests/review/M6b/r-contract/test_r3_*.py` and are listed in `docs/build/reports/r-contract-m6b-r3.md`. Probes:
`out/_wip/r-contract-m6b-r3/p1-p5.py`; `run_scen.py` (DevRun of meaning+brief on synth with intent+authored and the
four real fixtures: brief.md 882-1770 tokens, well under the 4k cap).

Verified fixed: R2-1 / N1 (template placeholders are empty, the fallback V1 link is `proposed`, untouched template
stays `pending` in both shapes), R2-3 / N4 (a lowercase `palette:` free-text line stays free text; the no-marker
template needs two template keys and no comment-truncated value), R2-4 / N5 (characters carry `field_sources`; brief
row says `(draft name + description)`; the template prefills only the user's own fields), R2-5 / N6 (SKILL §3 and
RECIPES document `field_sources` with an `isDraft` recipe), R2-6 (`mvh frames` checks `rr.status()` after the run and
exits 1 with `not_run` when frames is not done). Partially fixed: R2-2 / N3 (re-reported as R3-2: when the unfenced
template does not parse, its example comments become user claims), N2 (the label fix over-captures: R3-3, R3-4).

| id | location | claim | evidence | suggested fix |
|---|---|---|---|---|
| r3-m1 | meaning/intent.py parse_intent | a fenced template that fails to parse is parsed twice (fence, then the `# mvh-intent` marker region inside the fence), so the same warning is emitted twice | p5.py: `['...does not parse (ParserError); free text used', <same>]` | skip `_template_region` on text inside a fence that was already tried |
| r3-m2 | meaning/intent.py `_template_region` (marker path) | with the `# mvh-intent` marker, a plain value with ` #` is silently cut at the YAML comment (`tone: dark and slow #moody` -> `dark and slow`), no warning; the no-marker path refuses such values instead | p5.py | apply the ` #` check (warn) in the marker path too, or quote such values before loading |
| r3-m3 | skill/mv-harness/references/RECIPES.md `isDraft` | `field_sources` also holds `audio` (`characters_present`, `emotion.audio`); `isDraft = f => (...) !== 'user'` calls those draft | stage.py fsrc values `audio`; RECIPES line 78 | `=== 'draft'` (and say `audio` = measured) |
| r3-m4 | meaning/docs.py meaning_md | meaning.md still prints draft section fields (camera/movement/feel), setting, tone, palette and perspective with no `(draft)` mark under `Status: user` (characters are now marked) | p1.py on synth intent story + authored.json: `**Setting**`, `**Tone**`, `**Perspective**` from the draft, unlabelled | mark fields whose `field_sources` is `draft` as brief.md does |
| r3-m5 | round-2 minors still open | r2-m2 (RECIPES "Loading" include list still lacks `helper:meaningAt`, so the meaning/camera recipes throw in browser mode), r2-m5 (stale on-demand frames after a later `mvh analyze`; SKILL.md does not say to re-export), r2-m1, r2-m3 | RECIPES.md lines 12-13; SKILL.md §5 frames row | as in round 2 |

Note: the parallel r-words round-3 reviewer found overlapping issues (template hex palette, do-not over-capture) and
also that the template drops section `do_not`, `motifs` and `symbolism` on round-trip (tests/review/M6b/r-words/test_rw3_*.py).
