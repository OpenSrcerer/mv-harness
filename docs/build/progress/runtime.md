# runtime (W1b) - checkpoint log

## Status
- [x] io: atomic, wav, proc (Job Object), paths, ffmpeg, audio
- [x] runner: locks, models, cache, overrides, threads, http, sepworker, ctx, child, run (scheduler), validate, finalize, doctor
- [x] worker.py, testing.py, cli.py
- [x] ingest stage (real)
- [x] first e2e walking skeleton with mvh.testing.make_skeleton_fixture: valid, cache hits, --force deterministic
- [x] manifest compaction (files one per line) + fit_manifest trimming
- [x] tests (runner, io, cli, ingest, worker), tests/conftest.py: 59 pass + 1 opt-in GPU test
- [x] sep worker echo test in envs/sep/.venv-cpu (+ ROCm probe passed with MVH_TEST_GPU=1)
- [x] scripts/gate.ps1 (W1b: all PASS except ruff + validate, both other owners), scripts/fetch_models.py wrapper
- [x] spec.py additive Ctx.worker + decisions D29-D36 appended to CONTRACT.md
- [x] final report docs/build/reports/runtime.md (DONE; structured summary returned)
- [x] doctor run (all OK), Versatile ingest test, synth fixture e2e + determinism (gate)

## Design notes (decided)
- Sep venvs on disk are `envs/sep/.venv-<variant>/Scripts/python.exe` (not `envs/sep/<variant>/.venv`); resolver tries both.
- Every stage `run(ctx)` runs in a spawned main-env child (`python -X utf8 -m mvh.runner.child job.json`); env="sep" stages call
  `ctx.worker(...)` (additive Ctx service) which launches the sep venv worker. Stubs for sep stages therefore still work.
- n threads per stage is fixed (MVH_THREADS / --threads), concurrency is limited by the 8-core budget (n stays deterministic).
- Heavy slots: taken by the runner only for non-stub main stages with models; sep stages take it in ctx.worker.
  MVH_HEAVY_LOCKS=0 / --no-heavy-locks disables.
- `mvh.stages` stays a namespace package (CONTRACT §10).
- Network stages: dir key = pre_key; effective key = sha(pre_key + response hashes) (done.json "key").

## Commands that worked
- Bash: `MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python <script>` (scripts in the scratchpad).
- e2e scripts: scratchpad e2e1.py (tone + skeleton fixture + analyze), e2e2.py (validate/status/rerun/--force diff).

## Gotchas
- Bash heredocs mangle backslashes and some quotes: write Python files with the Write tool only.
- lib/mvh_load.py changes between runs while the lib builder works (not a determinism bug).
- Budget 8 cores / 3 threads = 2 concurrent stages.
