# r-contract-m6b-r2: round-2 review of M6b (meaning, brief, frames, skill/mv-harness), R-CONTRACT lens

Verdict: **fail** (6 majors, no blocker). Four of the nine round-1 findings are fixed; five are fixed only in part,
and the F3 fix brought in one regression. Every major has a failing test under `tests/review/M6b/r-contract/`. Each
test was run and fails for the reason given (11 failed). The round-1 tests still pass (6 passed). Minors are in the
"Round 2" section of `docs/review/M6b-r-contract.md`. Probes and DevRun outputs are in `out/_wip/r-contract-m6b-r2/`.

## Round-1 findings

| finding | state | notes |
|---|---|---|
| r-contract F3 (template copied unfenced) | partial | Fixed when the file holds only the template. If the template comes after a story, lacks its closing fence or has prose after it, the user's answers are still lost (R2-2). The fix also brought in a regression (R2-3). |
| r-contract F1 (Remotion include list) | fixed | `recipes_all.mjs` runs the Remotion recipe cleanly in URL mode. The generic Loading list still lacks `events:sections` for `meaningAt` (minor). |
| r-contract F2 (mixed sections in the zoom) | partial | brief.md and the zoom now label draft fields, but the skill still tells code-path agents to use `provenance.status` (R2-5). |
| r-words F1 (brief draft labels) | partial | The logline, palette and feel are labelled. Character names and descriptions written by the draft are not (R2-4). |
| r-words F2 (voice proposals vs user mapping) | fixed | The `settled` set in `build_characters` blocks the voices stage's proposals. |
| r-words F3 (do-not bullets as feels) | fixed | Fixed for do-not blocks under `#` headings. r-words-r2 reports the bold-label variant. |
| r-words F4 (untouched template = user) | partial | Still fails when voices are absent or the song has no characters (R2-1). |
| r-words F5 (text in warnings) | fixed | Warnings no longer include the cited text. |
| r-words F6 (lyric runs in drafts) | fixed | `cut_lyric_runs` covers every string in the draft, and the logline is capped at 40 words. |

## Majors

- **R2-1** Pasting the untouched template still makes the status `user`.
  - When voices are absent, `vhow.get(v, "user")` stamps the fallback V1 link as `user`. The template then writes `voices: [V1]`.
  - On instrumental songs, the placeholder line is `lead_backing: lead`.
  - In both cases the status becomes `user` and a user character "Character C1" is created.
  - Test: `test_r2_untouched_template.py`.
- **R2-2** Free text around the template still breaks it, in three variants:
  - a story heading before the template;
  - only the opening fence;
  - prose after the template.

  In each one, `do_not` is lost, C1 is named `{name`, and S05's feel becomes the YAML comment, all at user precedence. Test: `test_r2_template_in_context.py`.
- **R2-3** Regression from the F3 fix. A free-text answer that starts with `palette: night blue, #f2a541, rust red` is read as YAML. Two of the three colours are lost, the `chorus:` note is dropped, and no warning is given. Test: `test_r2_template_in_context.py::test_lowercase_palette_line_is_not_taken_for_the_template`.
- **R2-4** Character names and descriptions written by the draft are presented as the user's.
  - meaning.json has `provenance user/user` with no `field_sources`.
  - brief.md's character table has no `(draft)` label.
  - The template prefills the draft name as the user's answer.
  - Test: `test_r2_draft_characters_and_recipes.py`.
- **R2-5** In sections S01, S02, S04 and S05, `provenance.status` is `user` but some fields come from the draft. `field_sources` is not mentioned in SKILL.md or RECIPES.md, and `meaningAt()` does not return it. Test: `test_r2_draft_characters_and_recipes.py`.
- **R2-6** `mvh frames` exits 0 and lists only the old CSV when the stage did not run. This happens because the CLI checks the reason only when `frames/` is empty. The test replaces the runner with a stand-in that matches its code path. Test: `test_r2_frames_cli_not_run.py`.

The r-words-m6b-r2 reviewer found R2-1 (the instrumental case), R2-2, R2-3, R2-4 and R2-5 independently. R2-6 and the
voices-absent case of R2-1 are found only here.

## Gate

`scripts\gate.ps1 M6b` (log `out/_wip/r-contract-m6b-r2/gate.log`):
- **review, ruff, contract and validate pass.** The review step ran before the round-2 tests were added.
- **unit fails** only on `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs`, which is an M2 rhythm stub check, not M6b.
- **e2e:** M1 spectral fails (`select_kick_events() ... 'excess_min'`), so `frames` cannot run end to end today.

## Commands that worked

- `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python out/_wip/r-contract-m6b-r2/run_scen.py <fixture> <name> [intent.md|-] [authored.json|-]`
- `node out/_wip/r-contract-m6b-r2/recipes_all.mjs skill/mv-harness/references/RECIPES.md tests/contract/synth src/mvh/assets/mvh.js`
- `uv run --frozen --no-sync python -m pytest -q tests/review/M6b/r-contract`
