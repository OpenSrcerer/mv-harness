# r-platform report: W1b independent review (Windows platform lens)

**Verdict: pass with fixes.** I found 1 blocker, 6 majors and 15 minors. Every blocker and major has a failing pytest, and each one
fails today for the stated reason. The full findings, with location, claim, evidence and suggested fix, are in
[docs/review/w1b-r-platform.md](../../review/w1b-r-platform.md).

## Deliverables (owned paths only)

| Path | What |
|---|---|
| `docs/review/w1b-r-platform.md` | the review: findings table, B1, M1-M6, 15 minors, and what was verified OK |
| `tests/review/w1b/platform/test_platform_separator_dir.py` | B1, fails |
| `tests/review/w1b/platform/test_platform_publish_held.py` | M1, fails |
| `tests/review/w1b/platform/test_platform_status_threads.py` | M2, fails |
| `tests/review/w1b/platform/test_platform_hf_link_refetch.py` | M3, fails (local 127.0.0.1:0 server, stopped in teardown) |
| `tests/review/w1b/platform/test_platform_lyrics_in_errors.py` | M4, 2 tests, fail (synthetic lyric string only) |
| `tests/review/w1b/platform/test_platform_hardlink_cache.py` | M5, fails |
| `tests/review/w1b/platform/test_platform_slug_collision.py` | M6, fails |
| `tests/review/w1b/platform/test_platform_jobobject.py` | a regression test that passes (Job Object kill-on-close, real sep-cpu venv); mutation-checked |
| `out/_wip/r-platform/` | probes and logs: `uni.log`, `ing.log`, `gate1.log`, `probe_concurrent_runs.py`, `inplace.py`, `rocm_echo.py`, `leak_probe.py` |
| `docs/build/progress/r-platform.md` | checkpoint |

All test files pass `ruff check` and `ruff format --check`. The whole folder runs in about 45 s and currently gives 8 failed and 1 passed. Its file names start with
`test_platform_` so they cannot clash with the other reviewers' basenames in the single `tests/review/W1b` pytest run the gate makes.

## Findings in one line each

- **B1** `AUDIO_SEPARATOR_MODEL_DIR` (mvh-env.ps1/.cmd) points at the empty `models\audio-separator`, the runner only setdefaults it,
  and audio-separator 0.48 lets the variable override `model_file_dir`. M3a's separator would therefore download unpinned models outside `mvh models fetch`.
  doctor reports it as OK. The runtime report lists the path mismatch, but its mitigation ("use explicit paths") does not work because of the override.
- **M1** A re-run stage whose published file is held open by a reader makes `mvh analyze` crash (PermissionError from `unpublish`, outside
  the try), skip finalize and leave `.lnk` temp files behind.
- **M2** After `MVH_THREADS` changes, `mvh status` reports every stage `done/cached`, and the next analyze re-runs all 25.
- **M3** `mvh models fetch` repairs a corrupt model but not its HF-cache hard link, which is what allin1 and demucs load, and verify/doctor say OK.
- **M4** jsonschema messages that quote lyric text flow into StageError, failed.json, stderr, run.json and `mvh validate` (NF5).
- **M5** Hard-linked publishing lets an in-place edit in the song folder rewrite the cache. Later cache hits re-publish the edit, and status says done.
- **M6** Every non-Latin title slugifies to `song`, so a second song reuses `out/song/` and inherits the first song's overrides.json and intent.md.

## What was run

- **CLI with PYTHONUTF8 and PYTHONIOENCODING removed** (utf8_mode 0, cp1252), on `out/_wip/r-platform/in dir with spaces/tëst ♪ 曲.flac`: full
  walking-skeleton analyze, then status and validate. All passed.
- **`--only ingest` on 48 kHz FLAC, MP3, mono WAV and `viz/Versatile.flac`:** all correct. Versatile shows `missing_samples` 2291 plus a warning.
- **Determinism:** `--force` into the same folder, and a second folder with `--threads 2`: 0 of 179 files differ.
- **`sepworker.run_worker("_echo")`** in rocm (inside heavy+gpu slots) and in cpu; **`mvh doctor --no-rocm`**; and `scripts/gate.ps1 W1b`, which exits 1 with review,
  ruff and validate failing. ruff and validate fail for known, pre-existing reasons; see minor 14.
- **Heavy work:** none. There was no model inference or separation. The only GPU use was the `_echo` torch probe, run inside heavy-0 plus gpu.lock.

## Commands that worked

```
MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/review/w1b/platform
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/gate.ps1 W1b > out/_wip/r-platform/gate1.log 2>&1
```
For a run without UTF-8 mode: dot-source `mvh-env.ps1 -Offline`, run `Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING`, then `& .\.venv\Scripts\mvh.exe analyze ...`.

## Gotchas

- A scratch script named `concurrent.py` shadows the stdlib `concurrent` package when it is run from its own folder (sys.path[0]); I renamed it.
- `Settings(song_dir=<relative path>)` makes every stage fail, so always pass absolute paths to the runner API (minor 10).
- Python 3.12 `shutil.rmtree` and pytest's `rm_rf` do not follow directory junctions (verified). The Job Object test still removes its junction itself.

## Change requests

None. All fixes fall inside runtime-owned code (`src/mvh/runner/*`, `src/mvh/cli.py`) and the env scripts
(`scripts/mvh-env.ps1`/`.cmd`, owner env-main). The B1 fix to the env scripts is an env-hygiene edit, not a lock change.
