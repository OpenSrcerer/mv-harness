# builder-m6b report: M6b Agent delivery (meaning, brief, frames, skill/mv-harness)

Status: **done** for the module's code, tests and skill; the module gate fails only on files other agents own (CR-1),
the reviewers' failing tests (fix round) and upstream determinism (CR-7); see "Gate". Contract decisions: `docs/contract/decisions/M6b.md`. Progress log: `docs/build/progress/builder-m6b.md`.

## What each stage does

### meaning (`src/mvh/stages/meaning/`, version 1.0.0)
- **Inputs never written**: `meaning/intent.md` (user) and `meaning/authored.json` (agent/LLM draft) are read through
  `ctx.external`; the writer refuses them (tested), their hashes are unchanged after a run (tested).
- **intent.md parser** (`intent.py`): free text (characters `C1 Name = voice V1`, `L005: C1+C2` line singers, `## Never
  show` bullets verbatim, `Palette:` hex/colour words -> hex via `colors.py`, `Intro: ... Verse: ...` / `S03:` /
  `chorus#2:` / `Drop:` section notes, story -> summary + logline), the YAML template (fenced, prefilled in
  interview.md with ids and t0/t1), and the **M6a viewer-managed block** (`<!-- mvh-viewer:begin v1 -->`; round-trip
  tested against M6a's writer). Precedence viewer block > YAML > free text. `parse_intent(text)["n_characters"]` is the
  character count the voices stage can use.
- **Characters and singing** (`singing.py`): voice -> character = user > draft > `proposed_character_id` > harness
  proposal (open question). Lead/backing per line from overlapping voice spans (explicit lead character, then span
  conf, length, voice number); non-overlapping spans each lead; lyric `backing` lines are backing. Lines the voices
  stage missed take the nearest span (flagged `review`). Writes `events/singing.json` (+ additive `conf`, `source`,
  `review`) and `lyrics/lines.tsv` with `singer` = `C1+C2` lead first (D38).
- **Merge** (`stage.py`): per field user > draft > harness audio facts (`emotion.audio` from mood, `characters_present`
  from singing). Status user/draft/pending. Global `do_not` = the user's words only; every section's `do_not` includes
  them. Draft do-not suggestions and draft questions become `open_questions`. `field_sources` records per-field
  provenance. Citations checked (`cites.py`): unknown ids dropped, quotes cut to 10 words, untyped -> speculative, a
  draft cannot type `user`; problems never quote text.
- **Re-anchoring** (`anchor.py`): time-anchored claims follow sections by overlap (split -> both halves, merge -> the
  holder, else orphan -> `meaning/orphans.json` + warning in brief.md); label/occurrence/ordinal/EDM-role notes resolve
  against current sections (`drop` via `events/edm_roles.json`).
- **Drafting bundle**: `request.md` (rules + gaps), `input.json` (facts: sections with moods/roles/lines/singers,
  voices, characters, hooks, cues tier 1, top moments, vocal range, instruments, `gaps`; no lyric text),
  `schema.json` (mvh/files/meaning with every `$ref` inlined), `interview.md` (questions generated from the facts +
  the YAML template), `meaning.md`.
- **`mvh meaning <folder> [--draft anthropic]`** (`cli.py`, `llm_draft.py`): re-merges and refreshes meaning, brief and
  viewer (`--only`); with `--draft anthropic` it first drafts `authored.json` via claude-opus-5-5 (streaming, effort
  high, adaptive thinking, server-side refusal fallbacks `fallbacks="default"`, schema + citation check, one repair
  round). Opt-in only; never overwrites an existing draft without `--overwrite-draft`. **Not exercised against the
  live API** (offline build, no key).
- Params: `draft` (agent|anthropic|off), `lyrics_to_agents` (false -> blank lines.tsv text, `lines_file: null`).

### brief (`src/mvh/stages/brief/`, version 1.0.0)
- CONTRACT §12 order: status line (meaning, lyrics grade, stems, visemes, flags = the runner's manifest flags rebuilt
  from upstream done records + `meaning:orphans`, `singers:review`, low vocal-range conf, lyrics C/D), header table,
  meaning (logline, characters table, do-not verbatim, palette; pending -> the interview line), section cue sheet
  (id, t s + m:ss.s, bars, label + EDM role, repeat group, energy level + LUFS, instruments, vocals = singers + share +
  range, top hit points, line ids, mood, feel), choreography (counts, partials, counts per section, top grooves, top hit
  points, holds), top 15 moments, footer line.
- Overflow: collapse repeats by repeat group -> compact columns -> omit trailing rows with a pointer; never > 4k tokens.
- Every block names its files; `trace.py` checks every decimal against the folder's values (tests assert 0 untraceable).
- `mvh brief <folder> [--section S05] [--lyrics]` (`cli.py`): <= 1.5k-token zoom (row facts, dynamics, instruments,
  vocals, mood, chords, full meaning entry, lines with singers [quotes <= 10 words only with --lyrics and only if lyrics
  are allowed for the song], counts/grooves, hits/holds, cues tiers 1-3).
- Missing upstream inputs degrade (status `degraded`, fallback `brief:missing_inputs`) instead of failing.

### frames (`src/mvh/stages/frames/`, version 1.0.0, on demand)
- Vectorised `curve_frame` (linear/hold/mean/max, NaN-aware pitch channels, fps > rate fallback) parity-tested
  against `conventions.curve_frame`; never NaN (raises if one would reach the CSV).
- Rules: number, `[num, den]`, `"24000/1001"`, `{fps, frame0, early}`, or a list (several exports per run). Naming per
  CONTRACT §7 (`24fps.csv`, `24000-1001_f1fps.csv`, `30_earlyfps.csv`).
- Columns: frame, t, curves (default video set of ~24 channels; `["*"]` all; patterns; `spectrum128` -> 128 columns),
  then event columns (section_id, beat, downbeat, bar, beat_phase, count, sub, eight_id, line_id, singer, cue_tier,
  cue_id, hit) using the helper membership rules. Optional `format: deforum` -> `frames/<fps>fps.deforum.json`.
- `mvh frames <folder> --fps 24 [--fps ...] [--frame0 1] [--early] [--curves ...] [--events ...] [--format deforum]`
  adds to the exports already recorded for the folder (`--replace` to start over) and runs `--only frames`.

### skill (`skill/mv-harness/`)
- `SKILL.md` (~1.5k tokens): run, read order (brief -> section zoom -> lines.tsv -> CONTRACT §§2-4, §9 only), never cat
  data, the meaning rule (interview first, draft only gaps into authored.json, do-not rules are hard constraints),
  time/frame/ID rules, a what-to-use table, viewer check and flags.
- `references/RECIPES.md`: loading (JS/Python), dancing on counts and hits, lip sync per singer, camera on cues,
  palette and meaning per section, Remotion (calculateMetadata + delayRender), three.js (DataTexture + mvh.glsl, audio
  clock), Blender (frame0 = 1), ComfyUI/Deforum/ffmpeg, viz scenes via vizState.
- `references/CONTRACT.md`: generated copy (`skill/mv-harness/scripts/sync_contract.py [--check]`); a unit test fails
  when stale. Tests also check that every helper, events name and channel the skill/recipes mention exists.

## Measured accuracy vs thresholds (synthetic ground truth, tests assert them)

| Check | Threshold | Measured |
|---|---|---|
| Line -> lead voice / backing voices / singer string vs truth (words, backing_words) | >= 0.90 (PLAN §7 rap gate) | **1.00** (10/10 lines; with user intent and with harness proposals only) |
| `lines.tsv singer` for duet lines | `C1+C2` (D38) | exact |
| frames vs `conventions.curve_frame` (8 rates incl. 23.976, 29.97, [24000,1001], 120; frame0 0/1; early; 4 policies; NaN channels; 100 Hz and 1 Hz) | <= 1e-6 | max diff <= 1e-6 in all 32 combinations x 16 cases |
| Kick flash lands on its event's frame (synthetic kick hits, 24 fps) | >= 0.95 (PLAN §7 kick events) | >= 0.95 (asserted; passes) |
| frames `beat` column vs truth beats (frame_of) | exact | exact |
| brief tokens (synth) | <= 4000, target 2500 | 1185 |
| section zoom tokens (synth, max) | <= 1500 | 457 |
| untraceable decimals in brief / zooms | 0 | 0 |
| lyric text in brief, input.json, request.md, meaning.md, meaning.json | none (interview <= 8 words) | none |
| Determinism (meaning re-run) | byte-identical | identical |

## Real songs (upstream from tests/contract/real-<slug>; DevRun harness = runner child entry point)

| Song | meaning | brief tokens | zoom max | untraceable | lines / chars / voices | singer source | flags |
|---|---|---|---|---|---|---|---|
| synth | ok, 0.74 s | 1185 | 457 | 0 | 10 / 2 / 2 (4 duet lines) | spans 10 | - |
| megafauna | degraded, 0.14 s | 557 | 92 | 0 | 0 / 0 / 0 | - | lyrics:absent, voices:absent (fixture) |
| versatile | degraded, 0.16 s | 637 | 83 | 0 | 0 / 0 / 0 | - | lyrics:absent, voices:absent (fixture) |
| jeremy | degraded, 0.22 s | 741 | 147 | 0 | 40 / 1 / 0 | default 40 | voices:absent (fixture) |
| newton-vs-nye | ok, 0.22 s | 677 | 199 | 0 | 51 / 2 / 2 | spans 49, nearest 2 | 51 lines review (W0 spans all review) |

brief stage 0.3-0.9 s per song; frames 24 fps (default set) 0.2-0.6 s; frames 24 + 30000/1001 + 60 fps with all
channels 2.4-4.7 s per song. Briefs are small because the real fixtures lack mood, cues, choreo, instruments, dynamics
(brief `degraded`, `missing_inputs` 11-13); with every upstream present a 15-section song stays well under 4k
(overflow path tested to 300 sections).

Observations: Jeremy's vocal phrases show 69-90 % voiced activity in S12-S15 (the instrumental outro after ~217 s):
the brief reports what vocals wrote (W0 RMVPE adapter), flagged for M3b/W3. Newton's W0 voice clustering gives 2
voices with all spans `review`; two lines had no span and were given the nearest voice (flagged). No lyric text was
printed anywhere in this work.

## Tests

- `tests/unit/meaning` 30 passed + 4 real (opt-in) passed; `tests/unit/brief` 12 + 4 real; `tests/unit/frames` 42 + 4 real (all passing; 94/94 with `MVH_REAL_TESTS=1`).
- Commands: `uv run --frozen --no-sync python -m pytest -q tests/unit/{meaning,brief,frames}`; real: `MVH_REAL_TESTS=1` (or `-m real`).
- Real-song tests are marked `real` and run with `-m real` or `MVH_REAL_TESTS=1` (each folder's conftest registers it).

## Gate

Latest full run (resume 2, `out/_wip/builder-m6b/gate4.log`, `scripts\gate.ps1 M6b -KeepTemp`):

| step | result | note |
|---|---|---|
| fixture | PASS | |
| unit | FAIL | only `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` (CR-1, not mine); meaning 30, brief 12, frames 42 passed |
| review | FAIL | the 15 reviewer tests in `tests/review/M6b/{r-contract,r-words}` (R-CONTRACT F1-F3, R-WORDS F1-F6): owned by the fix round that follows this build step |
| ruff | PASS | (`skill/` is outside the gate's scope; fixed its one E501 anyway) |
| contract | PASS | |
| validate | PASS | |
| e2e | **PASS** (3205 s, mostly waiting for shared heavy slots) | meaning 0.5 s, brief 0.3 s in the full pipeline |
| lib-node | PASS | |
| determinism | FAIL (not M6b) | 44/179 files differ; the chain starts at `stems/drums/*.flac` (separate_hq drumsep on ROCm) and runs through drum_hits, sections, lyrics, singing ... meaning, brief, viewer -> CR-7 |

M6b on the e2e folder (synth song, every upstream stage real): brief 1297 tokens (<= 4000), `mvh brief --section S03`
441 tokens (<= 1500), 0 untraceable decimals in either; meaning/brief/frames re-run in-process on that folder
(`out/_wip/builder-m6b/e2e_frames.py`): ok; frames 24 fps frame0 1 (1356 rows), 24000/1001 frame0 1 (1355 rows),
60 fps early (3390 rows), all 124 columns with `curves: ["*"]`, 0 NaN/inf, singer values C1 / C2 / C1+C2, 14 hit frames.

Found and fixed while exercising the CLIs on the runner-made folder: `mvh frames` and `mvh meaning` run `analyze --only`;
when another module changed its params meanwhile (structure, then spectral, edited live by M1/M2 during this run),
their upstream was `stale`, the stage was silently not run, and the CLI exited 0 with an empty result. Both verbs now
report `not_run` with the stale upstream list on stderr and in the JSON and exit 1
(`tests/unit/frames/test_frames_cli.py`). A clean `mvh frames` end to end on a current folder could not be completed:
the folder went stale twice during re-analysis because other agents keep changing stage params (expected during W2).

Earlier runs: gate1.log (e2e blocked by an M1 dynamics failure), gate2.log/gate3.log (-SkipE2E).

## Change requests (W3 integrator)

1. **CR-1** `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` must stop assuming rhythm is a stub
   (check a stage that is still a stub, or only the version pattern); it fails every module gate now.
2. **CR-2** CLI flags of PLAN §10 not in `mvh analyze`: `--intent f` (copy-free external input for intent), `--meaning-draft
   agent|anthropic|off` (= `--param meaning.draft=...`) and `--no-lyrics-to-agents` (= `--param
   meaning.lyrics_to_agents=false`); today use `--param` or `mvh meaning`. Also: a plain `mvh analyze` re-run replaces
   `cli_params` in `.cache/_run.json`, so those meaning params are forgotten; runtime should merge them.
3. **CR-3** Fold the additive outputs/fields into catalog.py (W3): singing `conf/source/review`; meaning `palette_names,
   field_sources, intent_form, draft_used`, section `label/field_sources`, character `voice_mapping`, motif `note`;
   optional output `frames/{fps}fps.deforum.json`; frames event columns.
4. **CR-4** PyYAML is used by the intent parser (`yaml.safe_load`) but is only a transitive dependency in uv.lock; make it a
   direct dependency in pyproject.toml.
5. **CR-5** M5 voices may import `mvh.stages.meaning.intent.parse_intent` for the user's character count (and the
   viewer block's voice mapping) so both stages read intent.md identically.
6. **CR-6** `mvh frames` / `mvh meaning` run `analyze --only ...`; the manifest is rebuilt each time. Confirm finalize keeps
   on-demand outputs of earlier runs listed (frames files appear only when frames ran in this invocation, per D34).

7. **CR-7** (M3a / W3) determinism: two `mvh analyze --force` runs of the synth song give different drum sub-stems
   (`stems/drums/{kick,snare,toms,hihat,ride,crash}.flac`, separate_hq drumsep on ROCm); 44 downstream files differ.
   Needs deterministic GPU settings or a fixed seed in the sep worker; M6b's own stages are byte-identical for identical
   inputs (unit-tested).
8. **CR-8** (runtime) on-demand stages are left out of `run.json` when they do not run, and `--only` drops a stage with
   stale upstream without a line on stdout: `mvh analyze --only X` should print `X: not run (upstream stale: ...)`. The
   M6b verbs work around it via `mvh.runner.run.status`.

## Open issues

- `--draft anthropic` untested against the live API (no key, offline build); the code follows the claude-api skill
  (claude-opus-5-5, streaming, `fallbacks="default"` + `server-side-fallback-2026-07-01`).
- Real-song coverage of meaning/brief is limited by the fixtures (no mood, cues, choreo, instruments, dynamics; voices
  only for newton); the W3 full run is the real check of brief size and content.
- Lead/backing on real duets relies on voice-span confidence when the user has not marked a lead character; the rap
  battle attribution gate (>= 90 % after mapping) needs the user's mapping (PLAN §14.1).
- Free-text intent parsing is heuristic (lead/backing words, colour names); the YAML template and the viewer block are
  the exact paths, and unparsed palette words become open questions.
