# w4fix-platform progress (W4 fixer, platform group M6a/RUNTIME, round 1)

## Findings
- W4D-1 pack_curves deletes curves of stale stages (tests/review/W4/dogfood/test_w4d_stale_folder_keeps_curves.py)
- W4P-1 input relocation / rename (tests/review/W4/platform/test_w4p_input_relocation.py)
- W4P-2 held curve file + concurrent runs (tests/review/W4/platform/test_w4p_finalize_held_and_concurrent.py)
- W4D-2..4 skill docs: skill/mv-harness is M6b-owned (builder-m6b) -> change_requests; RUNS.md + `mvh pack` on my side.

## Plan
- finalize.pack_curves: stale/pending/failed stages contribute their last committed entry (latest.json) when its
  length matches the current timebase; unlink only unproduced files; PermissionError -> warn.
- curvefile.pack() (additive) -> finalize writes via atomic.write_bytes, skip identical bytes, held file keeps old
  file + old index entries.
- locks.song_lock (.cache/song.lock, pid-only staleness, reentrant) taken in run.analyze.
- ingest key: external.input = {"sha256"} only; Runner.resolve reuses latest ingest entry with the same content
  (legacy {sha256,name} key or missing file) -> no cascade; missing input + must run -> clear relink message.

## Done
- (start) read tests, finalize.py, run.py, cache.py, curvefile.py, atomic.py, locks.py, cli.py.
- curvefile.pack/index_bytes + safe _atomic_write; finalize.pack_curves rewritten (kept curves, held files);
  locks.song_lock + run.analyze takes it; run.py CONTENT_ONLY_PARAMS + _content_equivalent + missing-input fail;
  cli SongBusy -> exit 75. NEXT: run the 3 review test files + unit tests.
- All 5 W4 runtime review tests pass; tests/unit/runner/test_w4_platform.py (8 tests) pass; runner/io/cli/ingest/contract
  unit suites 154 passed; ruff clean. Added `mvh pack` verb (cli.py, CORE_VERBS).
- NEXT: RUNS.md docs (serve/ship, relocation, lock), decisions doc W4-platform.md, real-folder regression copies, gates W1b + M6a.
- RUNS.md (§1 pack verb, §5 relocation + lock, §6 rows, §8 serving/shipping), docs/contract/decisions/W4-platform.md written.
- Real check: `mvh meaning` on a stale copy of ud2-kick/newton-vs-nye (out/_wip/w4fix-platform/newton-stale): all curve
  bytes identical, index only schema_version rc.2->rc.3, validate 0 errors. NOTE: every real folder is rc.2 (contract
  bump) so all stages are stale everywhere; full re-run required anyway.
- RUNNING (background): gate W1b -> out/_wip/w4fix-platform/gate-W1b.log; full Newton re-run on the copy ->
  out/_wip/w4fix-platform/newton-full.log (resumable: re-run the same command, cache hits).
- NEXT: after Newton: no-op re-run (all hits), rename test on real audio copy, gate M6a, report.
- gate W1b: unit PASS (191 s); review/analyze/determinism pending. W4 review: platform 4/4 + dogfood stale 1/1 pass;
  skill_docs 3 fail (M6b path, change request; proposed text in docs/build/reports/w4fix-platform.md).
- Report draft at docs/build/reports/w4fix-platform.md (fill Verification at the end).
- gate W1b: all PASS except determinism (28 event files differ, NO curve file differs). Cause: other fixers edited
  dynamics/structure/spectral/drums/rhythm source 17:40-18:17 while the gate ran (between the e2e and the --force run).
  Re-run W1b gate at the end.
- Newton full run on the copy: exit 0, 25 done, ingest key now {sha256}. No-op re-run rc 0 (re-runs only stages other
  fixers changed). Rename run: ingest+separators cache hit, but the slug became newton-renamed -> FIXED: cli keeps the
  recorded folder slug when --out is given without --slug (+ unit test). 16 unit tests pass.
- RUNNING: gate M6a -> out/_wip/w4fix-platform/gate-M6a.log; Newton rename/missing step (task b7p5z5xja).
- DONE: M6a gate (determinism + ruff fail from other fixers' concurrent edits), tone determinism 0/83 differ, Newton
  rename + missing-input runs OK. Report written: docs/build/reports/w4fix-platform.md. Remaining: return summary.
