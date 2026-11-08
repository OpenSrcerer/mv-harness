# env-main report (W0, MAIN environment)

Status: **done**. Env, locks, models and smoke tests are complete and verified; benchmarking agents can start.
Full dependency rows, recipes, deviations and commands: `docs/spike/main.md`.

## Deliverables
- `pyproject.toml` (project `mvh`, hatchling, `src/mvh`, `mvh = "mvh.cli:main"`, dev group, `anthropic` extra, uv overrides), `uv.lock` (142 packages, win32), `.python-version`, `.venv/` (mvh editable-installed), `vendor/wheels/` (3 wheels).
- `scripts/`: `mvh-env.ps1`, `mvh-env.cmd`, `run.ps1`, `bootstrap.ps1`, `heavy_lock.py`, `fetch_models.py`, `smoke/{imports.py, prewarm_numba.py, make_clips.ps1, smoke_tools.py}`.
- `models.lock.json`: 21 entries, 5.85 GB, SHA-256 + size + (HF commit) revision for every file; models live under `%LOCALAPPDATA%\mvh\models`, HF-cache layout for allin1 and demucs-onnx under `...\mvh\hf\hub`, Rhubarb under `...\mvh\bin\rhubarb`.
- `%LOCALAPPDATA%\mvh\config.json` (ffmpeg, ffprobe, python, models, rhubarb; no BOM), numba cache pre-warmed.
- `docs/spike/main.md`, `docs/build/progress/env-main.md`, this report.

## Verification
- Fresh PowerShell 5.1 shell and cmd twin: tools resolve by absolute path, variables set, `-Offline`/`-Threads` work, `uv run --frozen --no-sync` uses `.venv`.
- Import test of 45 packages; forbidden packages (onnxruntime-directml, tensorflow, skey) absent.
- 28 smoke checks PASS offline (`%LOCALAPPDATA%\mvh\smoke\results.json`), covering every PLAN 5 and 7 tool that belongs to the main env.
- Heavy lock tested: two slots, third waits, dead-pid and >3 h locks taken over, `run` CLI, gpu lock ordering.
- OpenMP: torch + onnxruntime + ctranslate2 + numba + scipy in one process, no clash, no `KMP_DUPLICATE_LIB_OK`.

## Needs the orchestrator / change requests
1. The pinned-commit tarball build of the three vendored wheels was blocked by the permission classifier; PyPI 3.1.0 / 0.2.0 / 4.4.0 wheels are used (deviation 1 in the spike doc). If the commit route is still wanted, the orchestrator should approve building them (SHAs and cached tarballs are listed there).
2. PLAN 12 names `heavy.lock`; the protocol implemented here uses `heavy-0.lock` / `heavy-1.lock` / `gpu.lock`.
3. Lock hashes for the NF2 env-lock key: sha256 of `uv.lock` starts `38ef4ea6`, of `models.lock.json` `fb288804` (compute full values at use time).
4. env-sep's model files should be appended to `models.lock.json` through a change request to this agent (this agent owns the file; the fetcher is data-driven in `scripts/fetch_models.py` `SPEC`).
