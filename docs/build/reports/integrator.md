# integrator (W3 steps 1-3) report

Contract bumped to **1.0.0-rc.2**. W2 change requests applied or triaged, module decisions merged as D47-D66, five real
runs done (draft Jeremy plus max on four real songs and the synthetic song; all analyze 0 / validate 0), and 12 seams
recorded in `docs/SEAMS.md` (6 RUNTIME/cross-module ones fixed, 6 routed to module fixers, each with a failing test).
No lyric text appears in this report.

## 1. Gate blockers from W2 (fixed first)
- **Unit collection error.** `tests/unit/{lyrics,rhythm}/test_real_songs.py` shared a basename in rootdir import mode.
  Renamed to `test_lyrics_real_songs.py` and `test_rhythm_real_songs.py`.
- **GPU determinism (S01, D47).** Root cause: MIOpen chooses DrumSep's convolution kernels from the free GPU
  workspace. Reproduced with a process holding 80 % of GPU memory: every sub-stem differs by up to 4.5e-8.
  `cudnn.deterministic` and `miopen.immediate` do not help; the CPU path is bit-identical.
  `separate_hq.drumsep_device="cpu"` is now the default (`"auto"` = old GPU path). The RoFormer models stay on the
  GPU (identical under pressure). Experiment scripts: scratchpad `det/`.

## 2. Change requests (docs/build/W2-change-requests.md)
| CR | Result |
|---|---|
| move `# ruff: noqa: E501` headers to pyproject | done: 302 headers stripped; `[tool.ruff.lint.per-file-ignores]` globs for src/mvh/{stages,contract,sep,assets}, 5 runner files, tests/{review,synth,unit,integration}; E501 still enforced for src/mvh/io, the rest of the runner and the CLI |
| test_stub_files_are_stubs (M1, M2-5, M3a, M3b, M4-3, M5-3, M6a, M6b CR-1, ...) | replaced by `test_no_stage_is_still_a_stub`; the stub copier stays covered by test_schemas_io |
| CR-M5-1 lyrics deps += ingest | done (stage, PLAN_DEPS, CONTRACT §11 row) - D50 |
| CR M6a-1 / M6b CR-5 / fixer-m6b: voices + meaning read the managed intent block, `voices.lines` | meaning already did; voices now reads the viewer block (wins, voice-count floor) and the YAML template through meaning's parser; `voices.lines` already applied - D51, S10 |
| M6a CR-2 / M6b CR-2 `--no-lyrics-to-agents`, `--intent`, `--meaning-draft`, merge cli_params on re-run | done; `--no-lyrics-to-agents` also sets `viewer.inline_lyrics=false`; re-runs keep `--lyrics` (`-` forgets) and merge params - D52, S11 |
| CR M2-1 moments.d nullable | done in the events envelope (null allowed for kind event, number for segment) - D48 |
| lib -> finalize copy of mvh.d.ts | done + catalogue entry - D53 |
| M6b r2: meaningAt returns field_sources | done in mvh.js, mvh_load.py, mvh.d.ts; golden addendum regenerated - D54 |
| CR M2-7 pinned first in CUE_KIND_PRIORITY | done (amends D37) - D49 |
| M3a: heavy-slot waiters starve (15 s poll) | POLL_S 2 s - D55 |
| M3a: register the pytest `real` marker | done (`real`, `slow`, `models` in pyproject) |
| M6b CR-8: `--only` drops stages silently; on-demand stages missing in run.json | done - D55 |
| M6b CR-6: finalize keeps on-demand frames outputs | already true: pending on-demand stages are resolved after the run and published records stay in the manifest (no change) |
| M4: SPIKE/bench-music still call S-KEY flat | amended in place with a W3 note |
| CR-M4-2 mean_db under chords | stale: the generated chords table has no mean_db (it belongs to stem_activity and vocal_phrases) |
| CR-M1-3 hits.* range 0..1.5 -> 0..1 | not applied: unused headroom, nothing depends on it (documented in D56) |
| CR M2-2 stub matrices | stale: no stage is a stub; the test stub seam (D65) is only used by runtime tests that do not read matrices |
| catalogue fold-ins (CR-M1-2, CR-M3b-4, CR-M5-2, M6b CR-3) | documented in CONTRACT D56-D63 instead of field-by-field catalogue entries; the schemas allow additional properties, so validation is unaffected. Folding each optional field into catalog.py stays open (W4 or a contract pass) |
| CR-M1-1 allin1 -> dynamics deps; CR-M3b-1 vocals <- lyrics; CR-M3b-2 notes <- instruments; M1: spectral <- drums kick fusion | not applied (DAG changes with module work behind them); routed through S04/S06 and listed under change_requests |
| CR-M3b-3, CR-M4-1 overrides.json sections | not applied (contract + module work); stage params remain the hooks (D59, D60) |
| CR M2-6 cues.major.json | not applied (new optional output, M2's call); cues.json is 63-118 KB |
| M6b CR-4 PyYAML direct dep; CR M2-3 madmom numpy patch | pyproject/lock changes: orchestrator (change_requests) |
| M3a r2: decide the drum classifier-path test | tests/review/M3a/r-ml/test_drums_classifier_path.py passes in gate run 2; no decision needed |
| determinism CRs (M1, M2, M3a, M5-4, M6a, M6b CR-7) | covered by D47; re-checked by the gate (section 4) |

## 3. Contract
- CONTRACT.md: W3 section with **D47-D66** (W3 decisions D47-D55 and D64-D66; module merges D56 M1, D57 M2, D58 M3a,
  D59 M3b, D60 M4, D61 M5, D62 M6a, D63 M6b). The per-module decision files are kept as history.
- Version 1.0.0-rc.2 in mvh/__init__, catalog, mvh.js/mvh_load.py/mvh.d.ts/mvh.glsl, viewer; golden vectors
  regenerated (docs + assets copy); `python -m mvh.contract.gen` written and `--check` passes; fixtures rebuilt with
  `python -m tests.synth.build` (synthetic audio unchanged: same sha256); skill CONTRACT copy synced.
- Additive run.json fields `wait_s`, `computed_seconds` (D64).

## 4. Gate (`scripts\gate.ps1 all`, run 2, 1871 s, log out/_wip/integrator/gate-all.log)
| Step | Result |
|---|---|
| fixture | PASS |
| unit | **PASS**: 646 passed, 98 skipped, 0 failed (the first real unit result since W2) |
| review | FAIL: 55 failed / 144 passed / 21 skipped. **Every failure is in an open-finding test file** (docs/build/W2-open-findings.md): M1 test_rdsp_kick_events (1), test_rdsp_r2_kicks (1), test_rdsp_r3_kicks (9); M2 test_structure_rhythm_jitter (3); M3a test_r3_drums_ride_eighths (2); M4 test_key_gating_band_noise (1); M5 test_rw5_r3_battle_label_formats (2), test_rw5_r3_hallucination_nospeech (6), test_rw5_r3_speaker_labels (6), test_rw5_r3_unbracketed_headers (5); M6a test_r3_platform::test_a_failed_undo_keeps_the_state_it_was_restoring (1); M6b test_r3_intent_parsing (8), test_r3_perspective_source (1), test_rw3_do_not_overcapture (2), test_rw3_template_hex (5), test_rw3_template_roundtrip (2). M2 test_structure_drop_extent_real is real-marked and skipped in the gate (the regression it guards is visible in the real MEGAFAUNA run: the drop ends at 176.1 s). No other review test fails; the M3a classifier-path test passes. |
| ruff | PASS |
| contract (gen --check) | PASS |
| validate (fixture) | PASS |
| e2e (synthetic song, real stages) | PASS, 245 s |
| lib-node | PASS |
| determinism | **PASS** (was FAIL after W2): analyze --force twice, every file except run.json/.cache identical |

Run 1 (log gate-all.run1.log) had the same unit result; its review/validate/e2e steps broke because I rebuilt the
fixtures while it ran.

## 5. Real runs (out/_wip/integrator/<slug>)
All runs offline (MVH_OFFLINE=1). LRCLIB was replayed from the W0 recordings by seeding the lyrics HTTP cache
(`seed_lrclib.py`). MusicBrainz was unavailable (identity: tags only). Five max runs ran concurrently on two heavy
slots, so stage seconds below include queueing (the new `wait_s` separates the runner-level part from now on).

| Song | Profile | Wall s | analyze / validate | Degraded / fallbacks | Lyrics | Voices | Manifest tok | Brief tok | Folder (stems) |
|---|---|---|---|---|---|---|---|---|---|
| jeremy-draft | draft | 1145 | 0 / 0 | lrclib_offline + transcribed (not seeded), lipsync ungated_wordless | D (transcribed) | 1 | 2876 | 2089 | 1.5 GB (1.41 GB stems) |
| jeremy | max | 2522 | 0 / 0 | identity:offline, lipsync:ungated_wordless | D (lrclib, G1 0.697) | 1 | 2876 | 1876 | 1.5 GB (1.41) |
| megafauna | max | 2520 | 0 / 0 | voices **degraded** (vocals_stem), lyrics vocals_stem + asr_no_vad, lipsync vocals_stem | D (embedded) | 1 | 2890 | 1660 | 0.45 GB (0.39) |
| versatile | max | 2328 | 0 / 0 | voices skipped (instrumental), lipsync ungated_wordless | none (instrumental) | 0 | 2892 | 1594 | 1.27 GB (1.21) |
| newton-vs-nye | max | 2360 | 0 / 0 | lipsync ungated_wordless | B (lrclib) | 4 | 2898 | 1636 | 0.71 GB (0.67) |
| synth | max | 2046 | 0 / 0 | notes **degraded** (piano:basic_pitch), lyrics transcribed (no file given) | B | 2 | 2873 | 1331 | 0.09 GB |

Caps: manifest <= 3000 tokens (every real song trims its stage summaries, flag `manifest:stage_summaries_trimmed`);
brief <= 4000 (target 2500). viewer.html 8.7-15.9 MB (cap 28 MB). Loud masters write float WAV twins of stems
(|x| > 1), which is why Jeremy and Versatile carry 1.2-1.4 GB of stems; the cache shares them by hard link (Jeremy
2.2 GB on disk in total).

Per-stage seconds (max runs; include slot queueing):

| Stage | jeremy | megafauna | versatile | newton | synth |
|---|---|---|---|---|---|
| separate_fast | 170 | 55 | 1847 | 1308 | 21 |
| separate_hq | 1777 | 1099 | 2082 | 553 | 856 |
| allin1 | 61 | 42 | 50 | 43 | 17 |
| rhythm | 727 | 506 | 72 | 46 | 947 |
| harmony | 285 | 1614 | 170 | 380 | 921 |
| instruments | 383 | 86 | 209 | 804 | 250 |
| notes | 243 | 11 | 8 | 383 | 8 |
| lyrics | 408 | 229 | 60 | 157 | 99 |
| mood | 112 | 264 | 3 | 2 | 59 |
| lipsync | 41 | 25 | 1 | 45 | 17 |
| all others | < 35 each | < 21 | < 19 | < 15 | < 7 |

QA flags of note: MEGAFAUNA `tempo_trackers_disagree`, `feel_changes`, key `models_disagree`/`skey_differs`/
`modulation`; Versatile and Newton `downbeat_phase_off:madmom:-1`; Jeremy key `modulation` + `parallel_ambiguity`
(A major 0-122 s, then A minor). Re-running analyze on every folder: 25/25 cache hits, about 3 s each.

## 6. Seams
See `docs/SEAMS.md`. Fixed now: S01 (determinism), S02 (manifest key flags), S08 (timings), S10 (voices intent),
S11 (CLI agent flags and re-run parameters), S12 (runtime test seam). Open for module fixers: S03 M5, S04 M3b, S05 M2,
S06 M1 (major); S07 M5, S09 M2 (minor). Each has a failing test in tests/integration/<module>/test_real_*.py.

## 7. Gotchas for the next agents
- After any CONTRACT.md or schema change: `python -m mvh.contract.gen`, `python -m tests.synth.build` (the fixtures
  carry the version and schema copies), and `python skill/mv-harness/scripts/sync_contract.py`. Never rebuild the
  fixtures while a gate runs.
- The stage cache key does not include code: use `--force <stage>` after editing a stage.
- Bash heredocs in this harness mangle `\\` and some quote patterns: write files with the Write tool.
- `tests/integration/*/test_real_*` need the integrator's folders in out/_wip/integrator.

## 8. Gate run 2 result
See section 4: everything passes except the review tests of the still-open W2 findings.
