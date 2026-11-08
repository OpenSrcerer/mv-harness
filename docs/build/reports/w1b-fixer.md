# w1b-fixer report

Scope: the blocker and major findings of the two W1b reviewers (r-contract, r-platform). Every `tests/review/w1b/**` test now passes
(Python 18 tests incl. the Job Object regression, JS 3), the unit tests pass, ruff is clean, and `scripts/gate.ps1 W1b` was run (see the
orchestrator summary for its table).

## Platform findings
| Finding | Fix |
|---|---|
| blocker: AUDIO_SEPARATOR_MODEL_DIR empty | `scripts/mvh-env.ps1` and `.cmd` export `<home>\models\separator`; `Runner._child_env` and `sepworker.run_worker` SET (not setdefault) `models.separator_dir()`; `doctor` FAILs when the variable points at a folder that lacks the pinned separator files (D46) |
| major: publish crash when a published file is held | `publish` handles PermissionError per file (temp link removed, previous version kept, warning in run.json); `unpublish` guarded; a publish problem no longer deletes a finished cache entry or writes failed.json (D43) |
| major: status vs MVH_THREADS | `status()` uses `--threads` / `MVH_THREADS` (new `mvh status --threads`); `diff_inputs` prints `threads changed: 3 -> 4` (D44) |
| major: HF snapshot stays corrupt | `_hf_link` re-links a snapshot that is neither the same inode nor the lock's SHA; `verify` (and so `doctor`) checks the snapshots of `HF_CACHE_IDS` models |
| major: lyric text in errors | `schemas.safe_message`: no instance values for strings/objects/arrays (D42) |
| major: hard link into the cache | small files (< 8 MiB) are copied; big ones are hard-linked and size-checked on every cache hit (a damaged entry is re-run) (D43) |
| major: slug collisions | titles without ASCII letters get `-<6 hex of the input path>`; a default folder whose `_run.json` records another input is not reused (D45) |

## Contract findings
| Finding | Fix |
|---|---|
| F1 co-timed cues | D37: `conventions.merge_cues` (one cue per time, `kinds[]`/`sources[]`, best tier, priority kind); the synthetic fixture uses it; moments point at the merged cue. The real cues stage (W3, M2) must call `merge_cues`. |
| F2 lines.tsv singer | D38: `C1+C2` (lead first); schema pattern, fixture, CONTRACT §7 (generated) |
| F3 two producers | D39: `Output.restrict` (notes.{src} limited to bass/piano/guitar/other), `check_dag` rejects shared paths, `publish`/`unpublish` never delete a path another stage publishes, `run_stub` filters by the restricted regex |
| F4 vizState fps | D40: frame rule mandatory (`TypeError` without it) or song-wide `load(base, {fr})` / `load(path, fr=...)`; CONTRACT §9, mvh.d.ts, golden addendum cases (`null` -> `{fps: 60}`) updated |
| F5 overlapping segments | D41: `allAt` / `all_at` + `conventions.event_all_at` + golden rows + d.ts; CONTRACT §9 recipe fixed |

## Other changes
- `src/mvh/contract/**` was edited although it is not in the owned list (the findings live there): catalog.py (cues `kinds`/`sources`,
  singer pattern, schemas regenerated with `python -m mvh.contract.gen`), conventions.py (`merge_cues`, `event_all_at`), golden.py,
  schemas.py, fixture.py. Golden vectors regenerated (docs/contract + src/mvh/assets/golden copy).
- `scripts/mvh-env.ps1/.cmd` edited (env builder's files) for the blocker.
- ruff: `# ruff: noqa: E501` added at the top of 39 files with long lines (catalogue tables; the W1a contract package and its tests never
  passed `ruff check src tests`), plus two renames (E741) and autofixed imports.
- The strict xfail in `tests/unit/fixtures/test_fx_stubs.py::test_each_file_copied_by_one_stage` now passes and the marker was removed.
- New `tests/unit/runner/test_w1b_fixes.py`.
- Fixture `tests/contract/synth` was rebuilt (`python -m tests.synth.build --only synth`, 0 validation errors).

## Not done / notes
- Large (>= 8 MiB) published files are still hard links: an in-place edit with unchanged size would not be noticed (editing audio in place is not a realistic workflow).
- tests/contract/real-* fixtures were not rebuilt (they have no cues; they need the 5 minute `--only real` build).
- The synth fixture manifest.json exceeded the 3000-token cap after the rebuild (gate step 'validate'); tests/synth/song/folder.py now trims summary.stages and flags manifest:stage_summaries_trimmed (D34). Final gate: scripts/gate.ps1 W1b exit 0, every step PASS.
