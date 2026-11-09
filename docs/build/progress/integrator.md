# integrator (W3 step 1-3) progress

## Status
- 2026-11-09: started fresh (no prior progress file).

## Done

## Next
1. fix unit collection error + GPU determinism
2. apply CRs (W2-change-requests.md)
3. merge decisions -> CONTRACT.md, bump rc.2, gen
4. gate all
5. real runs (draft jeremy, max x5)
6. SEAMS.md + tests/integration
7. report

## Commands that worked

## Gotchas
- [x] unit collection error: renamed tests/unit/lyrics/test_real_songs.py -> test_lyrics_real_songs.py, tests/unit/rhythm/test_real_songs.py -> test_rhythm_real_songs.py
- [x] 302 '# ruff: noqa: E501' headers stripped; pyproject [tool.ruff.lint.per-file-ignores] globs added; ruff clean
- [x] test_stub_files_are_stubs -> test_no_stage_is_still_a_stub (tests/unit/contract 90 passed)
Gotcha: bash heredoc collapses '\' -> use Edit tool for backslashes in Python.
- [x] GPU determinism root cause: MDX23C DrumSep conv kernels on ROCm/MIOpen chosen by free GPU workspace -> 1e-8 diffs under memory pressure (reproduced with an 80% GPU memory hog; cudnn.deterministic and miopen.immediate do NOT help). CPU drumsep bit-identical, 1.45x realtime. Fix: separate_hq param drumsep_device='cpu' (default), hq_worker runs that step on CPU without gpu.lock. Experiment scripts in scratchpad/det.
- [x] CR-M5-1 lyrics deps += ingest (stage, PLAN_DEPS test, CONTRACT row)  -> decision D50
- [x] CR M2-1 events envelope d nullable(D) for events, number for segments (catalog) -> D48
- [x] CR M2-7 CUE_KIND_PRIORITY pinned first (conventions) -> D49 ; drumsep cpu -> D47
- [x] voices reads viewer block + YAML template (src/mvh/stages/voices/intent.py; tests/integration/M5/test_voices_intent_seams.py) -> D51. meaning already parsed the viewer block (M6b); voices.lines override already applied by voices.
- [x] CLI: --intent, --meaning-draft, --no-lyrics-to-agents (-> meaning.lyrics_to_agents=false + viewer.inline_lyrics=false), re-run keeps params_ext lyrics + merges cli_params ('--lyrics -' forgets). tests/integration/RUNTIME/test_cli_agent_flags.py -> D52
- [x] lib: finalize copies mvh.d.ts (+catalog lib/mvh.d.ts) -> D53; meaningAt/meaning_at return field_sources (js, py, d.ts, make_addendum regenerated; lib tests pass) -> D54
- [x] locks POLL_S 15->2 s; pytest markers real/slow/models in pyproject; runner says why a selected stage did not run; run.json lists on-demand stages (pending + how to run)
- [x] contract bumped to 1.0.0-rc.2 (src/mvh/__init__, catalog, lib js/py/d.ts/glsl, viewer data/edit.js, CONTRACT.md); golden regenerated + copied to assets; gen written; gen --check OK
- [~] draft jeremy launched in background: out/_wip/integrator/run_song.ps1 -> out/_wip/integrator/jeremy-draft(.log/.done.json)
Commands: powershell -NoProfile -ExecutionPolicy Bypass -File out/_wip/integrator/run_song.ps1 -Audio <a> -Slug <s> -Profile max -OutName <s>
- [x] CONTRACT.md: D47-D63 appended (W3 integration section). Per-module decision files kept.
- skipped CRs (reasons in report): M1-3 (range headroom unused), M2-2 (stubs gone), M2-3 (needs vendored madmom), M4-2 (stale: no mean_db under chords), catalogue fold-ins (documented via D56-D63 instead; schemas allow additional props)
- [x] draft jeremy: analyze rc 0, validate rc 0, 1145 s (DrumSep on CPU in separate_hq)
- [~] 04:30 launched max runs (detached Start-Process): jeremy megafauna versatile newton-vs-nye synth -> out/_wip/integrator/<slug>(.log, .out.log, .done.json). Re-launching the same command resumes from stage cache.
- unit tests (tests/unit) run: out/_wip/integrator/pytest-unit.log
- [x] unit run 1: 7 fails -> fixed: fixtures regenerated (python -m tests.synth.build; synth audio sha unchanged), skill CONTRACT copy synced, hq_worker uses torch.device('cpu') (fake separator), runner e2e tests use new child seam MVH_STAGE_STUBS=all-but-ingest (+ key gets stub=True). tests/integration/M3a/test_drumsep_device.py added.
- [x] tests/review/w1b: 17 passed 1 skipped. Fixed S02 (manifest key:key: flag, finalize.key_flags + tests/integration/RUNTIME/test_manifest_key_flags.py)
- seams noted from draft: real runs are offline (LRCLIB/MB unavailable -> transcription grade D on jeremy draft); structure S02 starts 1 bar after the +5.9 LU impact/dynamics loud start (19.47 s, bar 9); impact.bar=8 at bar-9 downbeat (rounding)
- [x] 05:1x seeded LRCLIB W0 recordings into out/_wip/integrator/<slug>/.cache/_http/lyrics (out/_wip/integrator/seed_lrclib.py) before lyrics ran: offline runs now serve recorded LRCLIB answers
- [x] synth max: analyze 0, validate 0, 2046 s. truth: beats F1 1.0, downbeats .98, sections .92 (intro split in 2, labelled verse; bridge labelled verse), drums kick 1.0 snare .99 hat .93 tom 1.0 cymbal .80, hits.kick .864 (M1 open), impacts .5 (5 est / 3 truth), stops .67, key A minor ok, edm roles exact. Tools: out/_wip/integrator/summarize.py, truthcmp.py
- [x] 05:08 all 5 max runs done: analyze 0 / validate 0. jeremy 2522 s, megafauna 2520, versatile 2328, newton 2360, synth 2046 (concurrent, 2 heavy slots)
- [~] 05:09 gate all launched detached: out/_wip/integrator/run_gate.ps1 -> gate-all.log / gate-all.done.json
- [x] re-run of all 5 folders: 25/25 cache hits, ~3 s each; manifest key flags fixed after re-finalize
- [x] S08 RUNTIME: run.json wait_s + computed_seconds (latest.json computed) D64; tests/integration/RUNTIME/test_run_json_timings.py
- NOTE original max-run stage seconds were overwritten in run.json by the re-run; values recorded in report from summarize output
- seam candidates: S03 M5 jeremy grade D (G1 0.697<0.70; lrclib text has no lines after 217 s, 79 s of vocal phrases w/o lines), S04 M3b/M3a megafauna vocals present=false but 14 lyric lines/singing, S05 M2 jeremy impact 19.47 (bar 9) vs S02 at bar 10, S06 M1 megafauna hits.kick vs drums kick 23%/42%, S07 M5 versatile instrumental mouth opens 0.55 s, S11 M2 synth intro labelled verse
- [x] tests/integration/{M1,M2,M3b,M5}/test_real_*.py (read out/_wip/integrator/<slug>, skip if absent): 7 fail as intended (S03 x2, S04, S05, S06, S07, S09); RUNTIME/M3a/M5 seam tests pass
- gate run 1 (05:09): unit PASS (376 s) but review/validate/e2e broken by MY concurrent fixture rebuild (truth.json missing mid-rebuild). GOTCHA: never rebuild tests/contract while a gate runs. Log kept as gate-all.run1.log
- [~] 05:4x gate run 2 launched (no more contract/fixture edits during it)
- [x] docs/SEAMS.md written (S01-S12)
- [x] docs/build/reports/integrator.md written (section 8 gate run 2 to fill in)
NEXT: wait gate run 2 (out/_wip/integrator/gate-all.log, .done.json), list review fails vs open findings, update report sec 4/8 + M3a classifier test claim, then StructuredOutput
- gate run 2: unit PASS (646 passed, 98 skipped, 0 failed), review 55 failed / 144 passed / 21 skipped - ALL in open-finding test files (M1 r-dsp kick x11, M2 jitter x3, M3a ride x2, M4 key gating x1, M5 x19, M6a undo x1, M6b x18); ruff PASS; contract PASS; e2e/determinism running
- [x] gate run 2 DONE rc 1: only review fails (55, all open-finding files). e2e PASS, determinism PASS. Report sec 4/8 + SEAMS updated.
- DONE: return StructuredOutput
