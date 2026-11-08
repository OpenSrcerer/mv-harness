# W1b review: R-PLATFORM (Windows platform lens)

Reviewer: `r-platform` (independent; PLAN §11). Date: 2026-11-08. Scope: the W1b foundation (runtime, lib, fixtures), read
against PLAN.md, docs/SPIKE.md, docs/CONTRACT.md §§1-4, §10, §13, §14 (D1-D36) and docs/spike/main.md §1-2. The builders'
reports were read only after the findings below were formed, and only to locate known items.

**Verdict: pass with fixes.** The platform core holds up: Unicode paths without UTF-8 mode, 48 kHz, MP3, mono and the corrupt
Versatile.flac all ingest correctly; runs are byte-deterministic; Job Objects kill the whole process tree; the sep worker env is
clean in both variants; and the locks interoperate with `scripts/heavy_lock.py`. One blocker (it blocks M3a) and six majors
must be fixed. Each has a failing test under `tests/review/w1b/platform/`, and all of them fail today for the stated reason.

| # | Sev | Finding | Failing test |
|---|---|---|---|
| B1 | blocker | `AUDIO_SEPARATOR_MODEL_DIR` points at an empty folder, and audio-separator lets it override `model_file_dir` | `test_platform_separator_dir.py` |
| M1 | major | A held published file crashes `mvh analyze` (PermissionError escapes `unpublish`) and leaves `.lnk` temp files | `test_platform_publish_held.py` |
| M2 | major | `mvh status` says `done` for every stage after `MVH_THREADS` changes, but the next analyze re-runs all 25 | `test_platform_status_threads.py` |
| M3 | major | After `mvh models fetch` repairs a corrupt model, the HF-cache copy the library loads stays corrupt, and verify says OK | `test_platform_hf_link_refetch.py` |
| M4 | major | Runtime error messages quote lyric text (jsonschema messages): StageError, failed.json, stderr, run.json, `mvh validate` (NF5) | `test_platform_lyrics_in_errors.py` (2) |
| M5 | major | Published outputs are hard links into the cache: an in-place edit rewrites the cached result, and later cache hits re-publish it | `test_platform_hardlink_cache.py` |
| M6 | major | Every non-Latin title slugifies to `song`, so the second song reuses `out/song/` and inherits the first song's overrides and intent | `test_platform_slug_collision.py` |

A regression test that **passes** is also kept: `test_platform_jobobject.py`. It kills the parent of a real sep-cpu worker that has
started ffmpeg, then checks that neither process survives. I mutation-checked it: with `proc.assign` disabled, it fails.

Run them with: `powershell -NoProfile -File scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/review/w1b/platform`
(add `MVH_RUN_OFFLINE=1` first). The gate picks them up through `tests/review/W1b`. Today the result is 8 failed and 1 passed, in about 45 s.

---

## Blocker

### B1. The environment points audio-separator at an empty model folder, and the variable overrides the explicit path
- **Location:** `scripts/mvh-env.ps1` line 55 and `scripts/mvh-env.cmd` line 16 (`AUDIO_SEPARATOR_MODEL_DIR=<home>\models\audio-separator`);
  `src/mvh/runner/run.py` `_child_env` (`env.setdefault(... h / "models" / "separator")`); `src/mvh/runner/doctor.py` `_misc`.
- **Claim:** The lock installs every separator model under `<models>\separator\`, which holds 8 files, the SHA-pinned ones.
  The env scripts export `...\models\audio-separator`, which is empty. Because the runner only `setdefault`s the correct value, every
  stage child and the sep worker inherit the empty folder whenever mvh runs under the env script, and that includes every agent, the gate
  and the user's shell. audio-separator 0.48 lets this variable **override** an explicit `Separator(model_file_dir=...)`
  (`envs/sep/.venv-cpu/Lib/site-packages/audio_separator/separator/separator.py` lines 185-194). So the mitigation in the runtime
  report ("M3a should use the explicit paths from job.json") does not work. The separator would look in the empty folder and download
  about 1.5 GB of unpinned files from its own mirrors, which breaks PLAN §3.3 ("`mvh models fetch` is the only downloader"; HF_HUB_OFFLINE does
  not stop those downloads), or it fails offline. `mvh doctor` reports the variable as `OK`.
- **Evidence:** `test_platform_separator_dir.py` dot-sources mvh-env.ps1, feeds its value into `Runner._child_env`, and compares the
  result with the folder of the lock's `separator/` files. It fails: `...\models\audio-separator` != `...\models\separator`.
  `mvh doctor --no-rocm` prints `OK env AUDIO_SEPARATOR_MODEL_DIR: ...\models\audio-separator`.
- **Suggested fix:** In `_child_env` and `run_worker`, **set** (not setdefault) `AUDIO_SEPARATOR_MODEL_DIR` to the directory of the lock's
  `separator/` files (`models.local_path("separator/x").parent`). Fix both env scripts the same way. In doctor, FAIL when that directory does
  not contain the lock's separator files.

## Majors

### M1. A reader holding a published file crashes `mvh analyze`
- **Location:** `src/mvh/runner/run.py` `Runner.publish` (lines 471-498) and `Runner.run` (lines 597-609, `unpublish` outside the try).
- **Claim:** When a stage re-runs and produces new content while a reader holds one of its published files (CPython `open()`, many
  players and editors, a video agent's dev server: none of them grant FILE_SHARE_DELETE), `os.replace` fails. `publish` retries for
  about 13 s and raises. `run` records it as a validation failure and calls `unpublish`, which raises the same PermissionError out of
  `Runner.run`, so `analyze` crashes with a traceback. finalize never runs: manifest.json and run.json are not updated. The `.<name>.<hex>.lnk` temp link stays in the song folder, and
  `failed.json` is written for a key whose cache entry is complete, so status says `done` and failed.json says failed.
- **Evidence:** `test_platform_publish_held.py` raises `PermissionError(13, 'The process cannot access the file because it is being used by another
  process')` and leaves `.mix.flac.<hex>.lnk`. A no-op re-run (all cache hits) with a file held open does **not** crash. The
  link-onto-the-same-file replace succeeds there, so only stages that re-run and produce new content are affected.
- **Suggested fix:** In `publish`, catch the PermissionError for each file. Remove the temp link, keep the cache, and report the stage as done with a
  warning (`published file held open: audio/mix.flac`). Put `unpublish` and the rmtree inside the error handling as well, and never let a
  publish problem delete a finished cache entry.

### M2. `mvh status` does not explain the re-run that `MVH_THREADS` causes
- **Location:** `src/mvh/runner/run.py` `status()` (it uses the threads, profile and cli_params of `.cache/_run.json`); `cmd_analyze` (it uses `--threads` / `MVH_THREADS`).
- **Claim:** NF2 puts n in every key. Analyze takes n from the environment, but status replays the last run's n. After `MVH_THREADS` changes,
  for example in a different shell, through the gate's `-Threads` option, or after `heavy_lock.apply_thread_limits` exports 6, status reports
  every stage `done / cached`, and the next `mvh analyze <folder>` silently re-runs all of them. With real models that means hours of separation.
  D36 requires `stale` with the changed input named.
- **Evidence:** `test_platform_status_threads.py` gives `mvh status said 'done' for 25 stages that the next mvh analyze re-ran`. The status
  reason for ingest is `'cached'`.
- **Suggested fix:** Have status compute the keys the next analyze would use: n from `MVH_THREADS` (with `--threads` on `mvh status`),
  and say `stale (threads changed: 3 -> 4)`. Alternatively, record n as sticky in `_run.json` and make `mvh analyze <folder>` reuse it unless
  `--threads` is given. Either way, status and analyze must agree.

### M3. Re-fetching a corrupt model does not repair its HF-cache hard link
- **Location:** `src/mvh/runner/models.py` `_hf_link` (`if dst.exists(): continue`), `verify`, and `doctor._models`.
- **Claim:** For the `HF_CACHE_IDS` entries (allin1 folds, demucs-onnx), the libraries load through the HF snapshot, which is a hard link to
  the models\ file. In-place corruption hits both names. `fetch` re-downloads and replaces the models\ path with a **new** file, but the
  snapshot keeps the old corrupt data, and `verify`/doctor hash only the models\ path, so both report OK.
- **Evidence:** `test_platform_hf_link_refetch.py` uses a local 127.0.0.1:0 server and a temporary MVH_HOME. Fetch, then corrupt 4 bytes in place: verify
  reports a mismatch. Fetch again and verify reports ok, but the snapshot sha is still the corrupt one.
- **Suggested fix:** In `_hf_link`, re-link whenever `dst` is not the same file as the local path (`os.path.samefile`) or its hash differs.
  Have `verify` check the snapshot link of each HF_CACHE_IDS entry too.

### M4. Runtime error messages carry lyric text (NF5)
- **Location:** `src/mvh/runner/ctx.py` `_validate` (it raises StageError with the raw jsonschema messages); `src/mvh/runner/validate.py`
  (report errors); `mvh.contract.schemas.validate` (`e.message`); the paths these messages then travel: child `error.json`, `failed.json`,
  the stderr progress line, `run.json` warnings, `mvh status`, and `mvh validate` stdout.
- **Claim:** jsonschema messages quote the offending instance (`'<text>' is not of type 'object'`). A single producer bug in
  lyrics or meaning copies lyric text into every place CONTRACT §1 forbids. W2 builders paste exactly these messages into their reports.
- **Evidence:** `test_platform_lyrics_in_errors.py`, using a synthetic lyric string. `StageWriter.json("lyrics/lyrics.json", ...)` raises a StageError that contains it,
  and `validate_folder` returns `lyrics/lyrics.json: lines/0/t: '<string>' is not of type 'number'`.
- **Suggested fix:** Format errors as `path: validator (expected ...)` without `e.instance`: use `e.validator`, `e.validator_value` and the
  path, never `e.message`. Apply this to every file, or at least to lyrics/*, meaning/*, events/singing.json, lipsync/* and lines.tsv.

### M5. Hard-linked publishing lets the song folder rewrite the cache
- **Location:** `src/mvh/runner/run.py` `publish` (`os.link`), and the cache-hit path (no integrity check), D30.
- **Claim:** Editors that save in place (Notepad, VS Code, a script using `"r+"` or `"w"`) and agents that "fix" an output directly modify the
  cache entry itself. The next run is a cache **hit** that re-links the edited bytes. `mvh status` says `done`, nothing is re-validated,
  done.json's sha256 no longer matches, and only `--force` repairs it. That silently breaks NF1 and NF2.
- **Evidence:** `test_platform_hardlink_cache.py` edits `brief.md` in place and runs again. The cache copy's sha differs from done.json, and the
  edited bytes are re-published. A manual probe gave `cache hit: hit | cache copy edited too: True | done.json sha matches: False | status: done`.
- **Suggested fix:** Publish by copy, which costs about 2x disk for stems. Alternatively, set the read-only attribute on cache files and verify size, mtime or sha256
  against done.json on a hit, then re-publish from a clean copy or re-run on a mismatch.

### M6. Non-Latin titles collide in `out/song/` and inherit another song's user inputs
- **Location:** `src/mvh/cli.py` `cmd_analyze` (`slug = slugify(song.stem)`, no check that the folder belongs to this input) and
  `mvh.contract.ids.slugify` (fallback `"song"`).
- **Claim:** CJK, Cyrillic, Greek and Arabic titles all slugify to `song`. The second song is analysed into the first one's folder without a
  warning. It inherits that song's `overrides.json` (`rhythm.bpm`, ...) and `meaning/intent.md`, which are user inputs the runner never deletes.
  Those files enter the new song's keys and provenance, and the first song's results are replaced.
- **Evidence:** `test_platform_slug_collision.py` analyses `曲.flac` and then `песня.flac`. Both go to `out/song/`.
- **Suggested fix:** When the slug degenerates (empty, or ASCII residue below about 3 characters), append a short hash of the stem, or use the
  file's pcm or file sha. Also refuse, or require `--slug`, when the target folder's `_run.json` records a different input sha256.

---

## Minor findings (no tests; for docs/REVIEW-LOG.md)

1. **Stale-lock takeover race** (`runner/locks.py` `_acquire_one` and `scripts/heavy_lock.py` `_acquire_one`, which use identical logic).
   Suppose two acquirers both see the same stale lock. The first unlinks it and creates a fresh one, then the second unlinks that fresh lock and
   creates its own, so both hold heavy-0. PID reuse on Windows can also keep a dead owner "alive" for up to 3 h. Suggested fix: rename the
   stale file to a unique name before deleting it and re-check, or use `msvcrt.locking` / LockFileEx on an open handle, which the OS releases on death.
2. **The env lock hash is too broad and partly stale.** `env_lock_hash` includes `models.lock.json` for every stage, so any model entry edit
   (each W2 module adds models) invalidates all 25 stages, separate_hq included, even though the per-model SHAs are already in the key.
   The sep key hashes the copies `envs/sep/uv.{v}.lock`, not the `envs/sep/{v}/uv.lock` that uv uses (doctor only warns on drift).
   The sep stage key also lacks the main `uv.lock`, although its `run()` and the FLAC encoding run in the main env.
3. **`device_class()`** returns the first variant whose venv exists, not the variant that ran. A rocm-to-cpu fallback is cached under the `rocm`
   key and stays cached after ROCm recovers. Results agree to -110 dB, so this is cosmetic, but the provenance key is misleading.
4. **`threads_for` clamps n to `--cores`,** so `--cores 2` changes every key. A scheduling option leaks into NF2.
5. **The ingest key includes the input file *name*** (`{"sha256", "name"}`), so renaming the song file re-runs all 25 stages through the upstream-key
   cascade. Only `meta/source.json.file_name` needs the name.
6. **doctor's truthfulness.** `models (sha256)` comes from a size+mtime cache, but it prints `hashing <file>` for every file, so bit rot that keeps
   size and mtime passes. "heavy locks" is `OK` even when a lock is STALE. The ROCm smoke matmul runs without `gpu.lock`. `--no-rocm` and `--quick` drop
   the ROCm line instead of printing SKIP.
7. **ffmpeg info lines counted as decoder warnings.** A mono WAV logs `Guessed Channel Layout: mono` at `-v warning`, so ingest reports
   `decoder reported 1 warning(s); the decodable audio was kept` and `decode_warnings: 1`.
8. **No per-song lock.** Two `mvh analyze` runs on one folder race: `StageCache.prune` deletes the other run's `.tmp-*` staging dir, so one
   run fails with `runner error: FileNotFoundError`. The final folder stayed valid in my probe (`out/_wip/r-platform/probe_concurrent_runs.py`).
   This is likely with viewer-triggered re-runs (§9). Suggested fix: a `.cache/song.lock` using the lock helpers, plus pruning only this run's staging.
9. **`mvh status` with a malformed overrides.json** shows a traceback (OverridesError is not caught in `cmd_status`).
10. **A relative `Settings.song_dir`** makes every stage fail, because the child's cwd is the scratch dir and the job paths are relative. The CLI resolves the path, but API callers
    such as tests and the viewer server must pass absolute paths. Resolve the path in `Runner.__init__`.
11. **No network guard for non-network stages.** Only HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE are set. torch.hub, `requests` and `urllib` downloads
    (MMS_FA with a missing `model_dir`, audio-separator mirrors) are not blocked. Suggested fix: for stages with `network=False` and the sep worker, set
    `HTTP_PROXY`/`HTTPS_PROXY` to a closed 127.0.0.1 port (and clear `NO_PROXY`).
12. **Ctrl+C (reasoned from code, not run).** Children start with CREATE_NO_WINDOW, so they have their own hidden console and do not receive the console Ctrl+C. On
    KeyboardInterrupt, the ThreadPoolExecutor waits for the running stages, so Ctrl+C waits until a running separation finishes. There is no per-stage
    timeout either (the builder notes this).
13. **`run_worker` timeout** kills only the worker python. An ffmpeg it started lives on until the stage child exits.
14. **gate.ps1** does fail when a step fails: exit 1 with `GATE FAILED: review, ruff, validate`, and all 8 failing review tests are listed. Today, though, it is
    red regardless of reviewers: ruff reports 463 errors (mostly E501 in `src/mvh/contract`, the stubs and `spec.py`; known) and `mvh validate tests/contract/synth`
    fails (fixture manifest 3105 tokens > 3000; known). A permanently red gate carries no signal. Other gaps:
    - It does not run the PLAN §12 ownership check.
    - Step 1 executes a command parsed out of a markdown report.
    - The determinism step re-runs into the same folder with the same settings, so absolute-path leaks would not show. I checked a second folder by hand: no leaks.
15. **`--force` uses `nargs="?"`,** so `mvh analyze --force song.flac` takes the song path as the stage list.

## Verified OK (by running code)

- **CLI without UTF-8 mode** (`sys.flags.utf8_mode=0`, stdout cp1252, PYTHONUTF8 and PYTHONIOENCODING removed) on
  `in dir with spaces\tëst ♪ 曲.flac`, through `.venv\Scripts\mvh.exe analyze`: exit 0, 25/25 stages done, `mvh status` and `mvh validate` (118 files,
  0 errors) fine. `file_name` is stored as UTF-8 in meta/source.json and in the manifest. No absolute paths appear in any output file.
- **Ingest (`--only ingest`):**
  - 48 kHz: stays 48000 Hz (576000 samples, 12.0 s).
  - MP3: gapless, exactly 529200 samples, `lossless:false`.
  - Mono WAV: 1 channel.
  - Versatile.flac: 10043392 samples, `missing_samples: 2291` with the 52 ms warning, peak 1.0, `soundtrack: audio/mix.flac`.
- **Determinism:**
  - `--force` in the same folder: 0 of 179 files differ.
  - A second folder with `--threads 2`: 0 of 179 differ.
  - The gate's determinism step: PASS.
- **Job Object:** killing the parent mid-job kills the sep worker and its ffmpeg (test above, mutation-checked).
- **Sep worker:**
  - Imports: in both venvs, importing `mvh.worker`, `mvh.runner.threads/locks`, `mvh.io.wav` and `mvh.contract` adds only `mvh` and `numpy`.
  - `_echo` in rocm: torch 2.11.0+rocm7.13.0, `cuda: true`, under heavy+gpu slots.
  - `_echo` in cpu: torch 2.15.0+cpu.
  - In both variants: ffmpeg is first on PATH, OMP=2, torch threads 2, and a Unicode scratch path works.
- **Locks:** same files and JSON as heavy_lock.py, heavy taken before gpu, stale-by-dead-pid takeover. The unit tests cover this and I re-read the code.
- **Models:** `fetch` refuses when offline and a file is missing; a SHA mismatch aborts and is never re-pinned. `scripts/fetch_models.py --list` runs under the
  bare Python 3.12.
