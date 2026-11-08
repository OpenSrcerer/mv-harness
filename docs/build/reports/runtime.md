# runtime (W1b) - report

Agent: runtime · 2026-11-08 · owned paths only (no git, no WSL). Checkpoint log: `docs/build/progress/runtime.md`.

## Result

The W1b runtime is built and the walking skeleton runs end to end: real `ingest` plus the 24 stub stages copying from
`tests/contract/synth/` produce a schema-valid song folder in about 9 s, a second run is all cache hits (0.4 s), and
`--force` reproduces the folder byte for byte (manifest, events, curves, tables, audio; only `run.json` differs).

`scripts/gate.ps1 W1b`: fixture PASS, unit PASS (runner 24, io 16, cli 7, ingest 6, worker 7 + 1 opt-in skip,
contract 90, fixtures 53, lib 22), contract-gen PASS, e2e PASS, node lib tests PASS, determinism PASS. **Two steps fail
on files other agents own** (details under open issues): `ruff check src tests` (pre-existing E501 in `src/mvh/contract/**`,
the stage stubs and `spec.py`; every file I own passes) and `mvh validate tests/contract/synth` (the fixture's manifest
is about 3105 tokens, over the 3k cap).

`mvh doctor` on this machine: every check OK (ffmpeg 9.0.2 with whisper, vulkan, chromaprint, libopus and libsoxr; main,
sep-rocm and sep-cpu locks in sync; ROCm matmul on the RX 9070 under torch 2.11.0+rocm7.13.0; Vulkan whisper models present;
Rhubarb 1.14.0; 81 model files in 28 entries SHA-256-verified; 1.49 TB free; locks free).

## Deliverables

| Path | What |
|---|---|
| `src/mvh/io/atomic.py` | temp file + `os.replace`, retried with backoff on PermissionError; copy, rmtree, unlink with retry |
| `src/mvh/io/wav.py` | float32 WAV writer/reader (stdlib + numpy; also reads 16/24/32-bit PCM and extensible), for our own files only |
| `src/mvh/io/proc.py` | process-wide Windows Job Object with KILL_ON_JOB_CLOSE; `popen`/`run` (argv lists only, never a shell) |
| `src/mvh/io/paths.py` | `home()` (%MVH_HOME% or %LOCALAPPDATA%\mvh), `repo_root()`, `config()` (config.json read with utf-8-sig) |
| `src/mvh/io/ffmpeg.py` | resolver `MVH_FFMPEG` -> config.json -> PATH; `child_env()` puts the ffmpeg bin first on PATH; `info()` (version, buildconf, flags) |
| `src/mvh/io/audio.py` | ffmpeg-only `decode` (`-map 0:a:0`, f32le pipe, native rate, warnings captured, soxr resampling, mono = channel mean), bit-exact `encode_flac` (24-bit) / `encode_opus` / `encode_wav`, `extract_cover`, `probe`, `pcm_sha256` |
| `src/mvh/runner/run.py` | `Runner`: DAG from the StageSpecs, NF2 keys, core-budget scheduler, one spawned process per stage, cache hits, `--only/--force/--from`, publish, validate after every stage, `status()` |
| `src/mvh/runner/child.py` | the stage process: thread hooks before the stage import, `run(ctx)`, required-output check, provenance re-stamp, `_mvh/done.json` |
| `src/mvh/runner/ctx.py` | `StageCtx`, `CacheUpstream`, `StageWriter`: the frozen `Ctx`/`Upstream`/`Writer` protocols plus `ctx.worker` (D29) |
| `src/mvh/runner/threads.py` | thread variables, and post-import hooks for onnxruntime (`SessionOptions` intra = n, inter = 1, also the default for `InferenceSession`), torch (`set_num_threads(n)`, interop 1), ctranslate2 (`intra_threads = n` default) |
| `src/mvh/runner/cache.py` | key canonicalisation, full-sha256 env lock hash, `diff_inputs` (status reasons), cache folders |
| `src/mvh/runner/overrides.py` | overrides.json loading, per-stage subset, validation; the user-input list that is never written |
| `src/mvh/runner/http.py` | cached, rate-limited HTTP (`ctx.http()`): responses under `.cache/_http/<stage>/`, offline serving, Retry-After, response hashes into the effective key |
| `src/mvh/runner/sepworker.py` | sep worker launcher: venv resolution, rocm -> cpu fallback, job.json/result.json, heavy slot + gpu.lock |
| `src/mvh/runner/locks.py` | heavy-slot protocol, file- and JSON-compatible with `scripts/heavy_lock.py` (tested against it) |
| `src/mvh/runner/models.py` | registry over `models.lock.json`: `fetch` (the only downloader; temp file, SHA verify, `os.replace` under a per-file lock, HF-cache hard links, Rhubarb unzip), `verify` (size/mtime SHA cache), `list_models`, `handle` (explicit local paths for `ctx.model`) |
| `src/mvh/runner/finalize.py` | packs `curves/*.f32` (column-major) + `spectrum128.u8` + `curves/index.json`, writes `manifest.json` (compact, cap-aware) and `run.json`, copies `lib/` and `schema/` |
| `src/mvh/runner/validate.py` | `mvh validate`: manifest/run/curves index + byte layout, every listed JSON (events by their schema), tables, overrides.json, authored.json, token caps |
| `src/mvh/runner/doctor.py` | `mvh doctor` checks (ffmpeg flags, env lock sync for main/sep-rocm/sep-cpu, ROCm smoke test, Vulkan whisper, Rhubarb, model SHA-256s, disk, locks) |
| `src/mvh/runner/snapshot.py` | `python -m mvh.runner.snapshot hash|diff` for the determinism gate |
| `src/mvh/runner/__init__.py` | re-exports `spec` (unchanged API) |
| `src/mvh/runner/spec.py` | **additive only**: `Ctx.worker(...)` protocol method (D29) |
| `src/mvh/worker.py` | `python -X utf8 -m mvh.worker <stage> job.json`: stdlib + numpy at module level, built-in `_echo` handler, `result.json` |
| `src/mvh/cli.py` | `mvh analyze/status/validate/doctor/models` + module verbs discovered from `mvh.stages.<name>.cli.register(subparsers)`; UTF-8 stdio |
| `src/mvh/testing.py` | `heavy()`, `apply_threads()`, `tone()`, `instance_of(schema)`, `make_skeleton_fixture()` (a schema-valid stub fixture for any audio length) |
| `src/mvh/stages/ingest/__init__.py` | the real ingest stage (replaces the stub); `mvh.stages` stays a namespace package (CONTRACT §10), so no `stages/__init__.py` |
| `scripts/gate.ps1` | the gate (`W1b`, `M1`..`M6b`, a stage name, or `all`) |
| `scripts/fetch_models.py` | thin wrapper around `mvh models fetch|verify|list` (stdlib only) |
| `tests/conftest.py` | src on sys.path, `MVH_THREADS` (default 3) applied in code, session fixtures `tone48`, `skeleton`, `no_heavy_locks` |
| `tests/unit/{runner,io,cli,ingest,worker}/` | 60 tests + 1 opt-in GPU test (`MVH_TEST_GPU=1`, passed on this machine) |
| `docs/CONTRACT.md` | decisions D29-D36 appended (nothing else edited) |

## How it works (for module builders)

- **Process model.** `mvh analyze` spawns `python -X utf8 -m mvh.runner.child job.json` per stage with
  `OMP/OPENBLAS/MKL/NUMBA/VECLIB/NUMEXPR_NUM_THREADS = n` in the environment, the ffmpeg bin first on PATH, `HF_HUB_OFFLINE=1`,
  `TRANSFORMERS_OFFLINE=1` and the cache directories under `%LOCALAPPDATA%\mvh`. The child installs the import hooks, imports
  `mvh.stages.<name>` and calls `run(ctx)`. Children (and ffmpeg, and the sep worker) live in the kill-on-close Job Object.
- **Threads.** `n` = `--threads` / `MVH_THREADS` (default 3), at most 6 for heavy stages, in the cache key. The scheduler
  runs stages while the sum of their `n` fits `--cores` (default 8): at n = 3 two stages run at a time.
- **Keys (NF2).** sha256 of: stage, version, contract version, resolved params, threads, model file SHA-256s, upstream keys,
  declared overrides that are set, external-input content hashes (the input file's hash and name, `--lyrics`, `meaning/intent.md`,
  `meaning/authored.json`), ffmpeg version + buildconf (`uses_ffmpeg`), full sha256 of `uv.lock` + `models.lock.json`
  (sep: both sep locks + models), device class (`gpu`). Network responses fold in after the run (D30).
- **Writing.** Only through `ctx.writer`; undeclared paths raise `UndeclaredOutput`; JSON is schema-validated; events get the
  envelope and provenance; tables use LF, no BOM, `0/1` booleans, empty = null; `lines.tsv` text has tabs/newlines replaced.
  `writer.audio("stems/x.flac", samples, sr)` encodes 24-bit FLAC and adds `stems/x.wav` when |x| > 1. Curves:
  `writer.curves("core", {id: array}, meta={id: {"norm": {"lo":..,"hi":..}}})`; the length must be
  ceil(n_samples * rate / sample_rate) or the write fails.
- **Reading.** `ctx.audio('mix')` (canonical float32, any stage), `ctx.audio('lead_vocals')`, `ctx.audio('drums_kick')`,
  `ctx.audio('fast:vocals')`, `ctx.audio('preview')`; `ctx.events(name)`, `ctx.curve(id)`, `ctx.upstream(stage).json(...)`;
  undeclared deps raise. `ctx.model(id)` returns local paths (the id must be in `STAGE.models`).
- **Sep worker (M3a).** In `separate_hq.run(ctx)`: `res = ctx.worker({"mix": ctx.audio("mix")}, models=[...])`, then
  `ctx.writer.audio("stems/vocals.flac", res.read("vocals.wav").samples, sr)` etc. Put the inference in
  `src/mvh/stages/separate_hq/worker.py::run_job(job, out_dir)` (job keys: `inputs`, `models`, `params`, `threads`, `device`,
  `variant`, `out_dir`); `envs/sep/tools/separate_song.py` is the reference. Pass model paths from `job["models"]`.
- **Module verbs.** `src/mvh/stages/<name>/cli.py` with `def register(sub): p = sub.add_parser("view"); ...;
  p.set_defaults(func=lambda a: ...)`.
- **Skeleton runs.** `MVH_FIXTURE_DIR` picks the fixture; `MVH_HEAVY_LOCKS=0` (or `--no-heavy-locks`) skips slots; stubs never
  take slots anyway. The skeleton input is the fixture's own song (`tests/contract/synth/_truth/synth-song.flac`), so the
  copied curves have the right length.

## Commands that worked

```powershell
Set-Location C:\Users\OpenSrcerer\Desktop\playground\mv-harness; . .\scripts\mvh-env.ps1 -Offline
uv run --frozen --no-sync mvh analyze tests\contract\synth\_truth\synth-song.flac --out out\_wip\runtime\synth
uv run --frozen --no-sync mvh status out\_wip\runtime\synth
uv run --frozen --no-sync mvh validate out\_wip\runtime\synth
uv run --frozen --no-sync mvh doctor            # --quick: sizes only, no ROCm smoke test
uv run --frozen --no-sync mvh models list       # fetch [--only id,id] [--env main|sep|ffmpeg] / verify [--no-cache]
uv run --frozen --no-sync python -m pytest -q tests/unit/runner tests/unit/io tests/unit/cli tests/unit/ingest tests/unit/worker
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gate.ps1 W1b
```

## Verified behaviour

- Ingest: 48 kHz stays 48 kHz; |x| > 1 gives `audio/mix.wav` and `soundtrack: audio/mix.wav`; mono MP3 (lossless false);
  cover + palette (k-means, deterministic); a truncated FLAC is a warning; **Versatile.flac**: 10,043,392 samples,
  `missing_samples` 2291, 2 decoder warnings, status done; lyric tags never reach `meta/source.json` (synthetic test text).
  On the synth fixture our `pcm_sha256` equals the fixture's; 102 of 105 published files are byte-identical with the fixture
  (the 3 that differ are our own ingest outputs: FLAC/opus encoder settings and the palette algorithm).
- Cache: hits, `--force`, `--from cues` (re-runs cues, meaning, brief, viewer only), `--only` (needs cached deps), a failing stage
  (dependants pending, independent branches finish, `failed.json`, manifest flag `failed:<stage>`), overrides (`rhythm.bpm`
  re-runs rhythm and its dependants only, recorded in provenance `overrides_applied`), `intent.md` change makes voices stale,
  user inputs untouched even with `--force`.
- CLI run on `tëst ♪ 曲.flac` in `out dir with spaces ü/` with PYTHONUTF8 and PYTHONIOENCODING removed: exit 0, one JSON line.
- Worker: in-process, in the real sep-cpu venv (ffmpeg first on PATH, OMP = n), rocm -> cpu fallback (`sep:cpu`), failure
  reporting; ROCm probe in sep-rocm with a heavy slot + gpu.lock (torch 2.11.0+rocm7.13.0, `torch.get_num_threads() == n`).
  `mvh.worker` + `mvh.io.wav` + `mvh.runner.threads` + `mvh.contract` import no jsonschema/httpx/torch/scipy/onnxruntime.
- Threads: in a fresh process `install(2)` gives ORT intra 2 / inter 1, torch 2 / interop 1, ctranslate2 Whisper patched.
- Job Object: a grandchild dies when its parent exits.
- Locks: interoperate with `scripts/heavy_lock.py` in both directions; stale (dead pid, > 3 h) locks are taken over.
- Models: fetch from a 127.0.0.1 server (port 0, stopped after the test), SHA mismatch refused, offline fails fast.

## Deviations from the plan (all recorded as decisions)

1. **D29** `Ctx.worker` added to `spec.py` (additive): every stage's `run` runs in the main env; env='sep' stages call the worker
   through ctx, so the parent encodes and caches (PLAN §3.3) and the sep stubs keep working.
2. **D30** cache dirs hold every output; public ones are hard-linked into the song folder; network stages use an effective key.
3. **D31** fixed `n` + concurrency budget; heavy slots only for non-stub main stages with models (sep: inside `ctx.worker`).
4. **D32** lyric tags are kept out of `meta/source.json` (NF5); new optional `missing_samples`, `embedded_lyrics_tags`; new
   cache-only optional ingest output `embedded_lyrics.json`.
5. **D33-D36** writer re-stamping, manifest assembly and trimming, CLI verb discovery, status semantics.
6. The sep venvs are at `envs/sep/.venv-<variant>` (what W0 built); `envs/sep/<variant>/.venv` is also accepted.
7. `scripts/fetch_models.py` is now a thin wrapper; pinning new entries (the W0 SPEC) is no longer done by a script.
8. `mvh.stages` stays a namespace package (no `stages/__init__.py`), as CONTRACT §10 says.

## Change requests

1. **lyrics needs embedded lyrics.** The cascade's "embedded tags" step has no path: lyrics does not depend on ingest and the
   lyric tag text is (correctly) not in `meta/source.json`. Add `ingest` to lyrics' deps (it can then read the cache-only
   `embedded_lyrics.json`) or let identity pass it through.
2. **models.lock.json vs `mvh/envelope/models_lock`.** The lock has `"schema": 1` (no `schema_version`), env labels `sep-rocm`,
   `sep-cpu`, `ffmpeg-whisper` (schema enum: main, sep) and extra keys (`notes`, `source`, `bundled`, `note`). It does not
   validate; either relax the schema or normalise the lock (the runtime treats `sep-*` as sep and `ffmpeg-*` as ffmpeg).
3. **ruff E501.** About 460 pre-existing ruff errors (mostly E501) in `src/mvh/contract/**`, `tests/unit/contract/**`, `src/mvh/__init__.py`, the stage stubs
   and `spec.py` make `ruff check src tests` fail. Either raise `line-length` in `pyproject.toml` or reformat those files
   (owners: contract code has no active owner; stubs belong to the W2 modules).
4. **mvh-env.ps1 `AUDIO_SEPARATOR_MODEL_DIR`** points at `models\audio-separator`, but the SHA-pinned separator files are in
   `models\separator` (lock paths `separator/...`). The worker job carries explicit model paths; M3a should use them.

## Open issues

- `tests/contract/synth/manifest.json` is about 3105 tokens (> 3000), so `mvh validate tests/contract/synth` fails. The fixtures
  builder can write it with `mvh.runner.finalize.dumps_manifest` (one compact line per `files` entry; ours is 10.8k characters
  for the same song) or `fit_manifest`.
- There is no per-stage timeout: a hung stage hangs the run (children die with the runner).
- `ctx.worker` holds one slot for the whole worker run by default; `separate_song.py` held a slot per model run.
  M3a can pass `hold_slot=False` and lock per model inside `run_job`.
- doctor's Vulkan-whisper check is static (buildconf flags + ggml files present); it does not run a transcription.
- `run.json.device.gpu` is null (no GPU name captured); the ROCm device name is in doctor output.
- The manifest is close to its cap on the synth song (about 2.7k tokens); real stage summaries will be trimmed by
  `fit_manifest` (flag `manifest:stage_summaries_trimmed`), so module builders should keep `StageResult.summary` small.

## Gotchas

- In the Bash tool, heredocs mangle backslashes in Python files: write Python with the Write tool.
- `node --test` treats its arguments as globs: pass relative forward-slash paths (gate.ps1 does).
- `Get-ChildItem -LiteralPath ... -Include` ignores the filter in PowerShell 5.1; filter with `Where-Object`.
- `$input` is an automatic variable in PowerShell; `"$rc: "` is a scope-qualified variable: use `${rc}`.
- Several test folders ship their own `conftest.py`; run them in separate pytest invocations (gate.ps1 does).
- `scripts/heavy_lock.py acquire` exports 6 threads into the calling process; tests restore the variables.
