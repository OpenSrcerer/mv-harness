# r-contract-m6b: R-CONTRACT review of M6b (meaning, brief, frames, skill/mv-harness)

Lens: a Remotion / three.js / Blender / ComfyUI agent building a choreographed, character-driven video from one song folder plus
`skill/mv-harness/SKILL.md`. Findings were formed from the code, the spec and runs before reading the builder's report.

## How it was checked
- M6b stages run in-process through `mvh.stages.meaning.devrun.DevRun` (the runner's child entry point) on `tests/contract/synth` and the
  four `tests/contract/real-*` fixtures: `out/_wip/r-contract-m6b/devrun_all.py` -> `out/_wip/r-contract-m6b/dev/<fixture>/song`.
- Synth with the user's intent.md, the draft authored.json, and both (`devrun_user.py`); a draft carrying do-not rules
  (`devrun_dodraft.py`); the interview's YAML template copied into intent.md fenced and unfenced (`devrun_yaml.py`);
  `lyrics_to_agents=false` leakage scan (`devrun_nolyr.py`).
- frames: every CSV cell compared with `mvh.contract.conventions` (curves with their policies and NaN rule, `t`, cue/hit membership by
  `frame_of`, section/count/singer at the sampling instant) for 24, [24000, 1001], 24 frame0 1 and 30 early (`parity_frames.py`).
- brief: strict per-block trace (each decimal must be a value of a file named in its own block, `trace_strict.py`), token sizes of the
  brief and every `--section` zoom with and without `--lyrics` (`zoom_sizes.py`).
- skill: the Remotion recipe executed in browser mode (URL base + fetch, no fs) against the synthetic fixture
  (`tests/review/M6b/r-contract/remotion_recipe.mjs`).
- A full `mvh analyze` of the synthetic song was started in the background (`out/_wip/r-contract-m6b-synth.err`) but the shared
  heavy slots kept the upstream stages waiting for the whole review window, so the end-to-end `mvh frames` / `mvh meaning` CLI runs
  and `mvh validate` of a complete folder were not done here (DevRun exercises the same stage code and Writer/schema checks).

## What works (verified)
- frames: 0 mismatches against the reference on all four frame rules and three fixtures; row counts equal `frame_count`
  (jeremy 7599 / 7591 / 9498, the CONTRACT §2 worked example); never NaN; file tags `24fps`, `24000-1001fps`, `24_f1fps`,
  `30_earlyfps` match RECIPES.
- singing.json and lines.tsv equal the synthetic truth (singer `C1+C2` on duet lines, D38); additive `conf/source/review` documented.
- brief.md: 557-1220 tokens (cap 4000, target 2500); zooms <= 504 tokens; status line, header, meaning, cue sheet, choreography,
  moments and footer in the CONTRACT §12 order; 0 untraced decimals under the strict per-block rule; no lyric text.
- A draft's `do_not` is never applied (it becomes an open question), so "Do not (the user's words)" is accurate.
- `lyrics_to_agents=false`: no line text in interview.md, request.md, input.json, meaning.md, brief.md or lines.tsv.

## Findings (blocker / major, each with a failing test)
| id | sev | location | claim | test |
|---|---|---|---|---|
| F3 | blocker | src/mvh/stages/meaning/intent.py `parse_intent` (+ interview.md template) | Copying the interview's YAML template into intent.md without the markdown fence (its first line literally says "copy this block into meaning/intent.md") is parsed as free text: the user's do_not rule is silently dropped, YAML syntax becomes user claims (C1 name `{name`, S05 feel `# chorus#2 0:34.5-0:50.5`), status stays `user`, no warning | tests/review/M6b/r-contract/test_intent_template_copy.py |
| F1 | major | skill/mv-harness/references/RECIPES.md, Remotion recipe | The recipe's `include` list (`curves:core, events:counts, events:singing, events:cues, lyrics, meaning`) misses `events:beats` and `curves:vocal`, so `song.count(t)` and `song.singerAt(t)`, which the recipe says to use, throw on the first frame in Remotion (browser mode) | tests/review/M6b/r-contract/test_recipes_runnable.py (+ remotion_recipe.mjs) |
| F2 | major | src/mvh/stages/brief/build.py `render_section` / `_feel`; meaning section `provenance` | A section that mixes user and draft fields gets `provenance.status = user`; the zoom prints every field under `## Meaning (user, ...)` with no per-field label, so the draft's movement/camera/emotion/palette are presented as the user's (S01, S02, S04, S05 on synth). RECIPES tells agents only `provenance.status === 'draft'` marks agent text; `field_sources` (A3) is never surfaced | tests/review/M6b/r-contract/test_draft_fields_labelled.py |

All three test files fail now for the stated reason (`uv run --frozen --no-sync python -m pytest -q -p no:cacheprovider
tests/review/M6b/r-contract`: 5 failed, 1 passed, the passing one being the F2 precondition).

Suggested fixes: F3 treat a file whose first non-comment line is a template key (or that starts with `# mvh-intent`) as YAML, and warn
whenever an unfenced `key:`-shaped file falls back to free text; also put the fence instruction in the template's first line.
F1 add `events:beats` and `curves:vocal` (better: `helper:count`, `helper:singerAt`, `helper:meaningAt`) to the recipe and add a
test that executes every recipe's include list in URL mode. F2 tag each draft-sourced field `(draft)` in the zoom and in the brief's
feel cell (from `field_sources`), and tell agents in RECIPES/SKILL to read `field_sources` (or give sections a `mixed` status).

## Minor findings
11 minors in docs/review/M6b-r-contract.md (voice_mapping mislabels a default as `user`; unsorted `line_ids`; row singer vs line
membership; brief numbers not traceable to a named file and gaps in `trace.py`; compact rows drop instruments; two RECIPES field
descriptions; generic include list; dead links in the CONTRACT copy; `[60, 30]` read as a rational fps; undocumented `both`;
frames export not refreshed by `mvh meaning`).

## Change requests
None. All fixes are inside M6b's owned paths.
