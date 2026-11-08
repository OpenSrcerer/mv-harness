# builder-m5 progress (M5 Words: identity, lyrics, voices, lipsync)

## Status
- [x] identity, lyrics, voices, lipsync implemented (src/mvh/stages/<stage>/)
- [x] harness tests/synth/m5/harness.py (stub_deps, slot() with 2 s poll), fakehttp.py, make_http_fixtures.py,
      pytest_markers.py; tests/fixtures/http/{musicbrainz_versioned,lrclib_synth}.json (synthetic)
- [x] unit tests: identity (8), lyrics fast (21), voices logic (6), lipsync (5 incl. Rhubarb), voices synth models (3)
- [ ] lyrics synth model tests (tests/unit/lyrics/test_lyrics_synth_models.py) not yet run
- [x] real songs run once (jeremy B/1 voice, newton B/3 voices/offset -1.32, versatile instrumental)
- [ ] rerun after: vocals-stem fallback (MEGAFAUNA lead_vocals silent), ASR-only line rule, repair bounds
- [ ] gate scripts\gate.ps1 M5, report docs/build/reports/builder-m5.md, decisions doc final pass

## Decisions (full list: docs/contract/decisions/M5.md)
- lyrics dep on ingest NOT added (contract test pins deps); D8 path; CR-M5-1.
- whisper: temperature 0 + DEFAULT VAD params (custom VAD params lost half the newton words).
- voices: estimate + merge_minor (Jeremy 2->1, MEGAFAUNA 4->1); newton 3 voices = W0 blocks.
- lipsync: last-word hold stops at the next line start.

## Commands that work
- Git Bash: `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python <abs script>` (online: drop MVH_RUN_OFFLINE)
- real chain: scratchpad/real_run.py <slug> [--offline] -> out/_wip/builder-m5/h-<slug>/, real_summary_<slug>.json
- tests: `... scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/unit/<stage>`

## Gotchas
- tests/contract/real-* have no stem_activity: harness synthesises stem.*.active.
- heavy slots: mvh.testing.heavy polls every 15 s and starves; use tests.synth.m5.harness.slot (2 s poll).
- Writing Python with escapes through bash heredocs mangles \r \b: use the Write tool.

## Resume 2026-11-08 21:00 (session 2)
- fast unit tests: 36 passed, 14 skipped (models skipped); ruff src tests clean.
- newton real run at 17:52 is on current code (lyrics B, offset -1.32, 3 voices, lipsync ok).
- chain started: scratchpad/m5chain.sh megafauna jeremy versatile synth -> scratchpad/real_<slug>.log
- next: lyrics synth model tests, gate M5, report.
- lyrics synth model tests: 3 passed (median onset error 20 ms on txt / lrclib / asr paths; threshold 80 ms).
  measure script: scratchpad/m5_synth_acc.py <pytest tmp dir>
- MEGAFAUNA found: VAD kills the processed voice (2 words). Added M5-D19 VAD retry (no-VAD 75 words, F1 0.53),
  M5-D20 G1 applicability, M5-D21 voices small_n eigengap bound, M5-D22 review flags on grade D. Unit tests added.
- chain2 queued: megafauna newton-vs-nye (scratchpad/m5chain2.log). Then: voices/lipsync synth model tests, gate M5.
- 21:45 all four real songs + synth rerun on current code (logs scratchpad/real_<slug>.log, summaries
  out/_wip/builder-m5/real_summary_<slug>.json). newton now 52 lines (announcer intro asr_only) and 4 voices
  (V1 announcer, V2/V3 alternate, V4 late rapper = W0 partition). MEGAFAUNA D (honest: G1 0.54 weak ASR, G2 0.68,
  G3 0.22), 1 voice, all spans review. versatile instrumental. jeremy B unchanged.
- real tests strengthened (newton intro voice, megafauna D19/D21/D22). gate M5 running -> scratchpad/m5_gate.log
- next: real tests (MVH_REAL_TESTS=1 tests/unit/lyrics/test_real_songs.py), report.
- real tests: 4 passed (742 s). gate M5 running: unit FAIL only on tests/unit/contract::test_stub_files_are_stubs
  (asserts rhythm is still a stub; M2 replaced it, not M5's file) -> CR-M5-3. ruff/contract/validate PASS; e2e running.
- report written: docs/build/reports/builder-m5.md (gate placeholder to fill).
- 22:3x gate e2e PASS (2107 s, full pipeline), lib-node PASS; determinism step running.
- 22:49 gate M5 exit 1: unit FAIL only contract (CR-M5-3), determinism FAIL upstream (drums stems, stems.f32,
  sections) CR-M5-4; everything else PASS (ruff, contract, validate, e2e 2107 s, lib-node).
- M5 determinism with fixed upstream: 0 files differ (scratchpad/m5_det.py, out/_wip/builder-m5/det).
- report final: docs/build/reports/builder-m5.md. DONE unless W3 asks for more.
