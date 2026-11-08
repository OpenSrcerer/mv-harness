# env-main progress (resume file)
Started 2026-11-08. Owner paths per task. Agent: env-main.

## Status
- [ ] 0 recon (PLAN read, survey dumped to scratchpad survey.txt)
- [ ] 1 pyproject + vendor wheels + lock + sync
- [ ] 2 scripts (mvh-env.ps1/.cmd, bootstrap.ps1, heavy_lock.py)
- [ ] 3 models.lock.json + fetch
- [ ] 4 smoke tests
- [ ] 5 docs/spike/main.md + report

## Notes / gotchas
- Network: HF 200 (beat_this repo is NOT on HF: 401), GitHub archive slow (30s+), api.github.com works slowly.
- Research caches (Essentia onnx, ggml) exist in the old scratchpad: .../scratchpad/research/identity-lyrics-meaning/{ess,models}

## Milestone 1 (done): env lock+sync
- Tarball wheel build was DENIED by the permission classifier (building external code). Fell back to PyPI wheels (all-in-one-infer 3.1.0, madmom-infer 0.2.0, demucs-infer 4.4.0), copied sha-verified into vendor/wheels/, sourced via [tool.uv.sources] path.
  Upstream-pinned commits that I identified (tarballs in %LOCALAPPDATA%\mvh\dl, NOT built): all-in-one-infer 566f96c3, madmom-infer a9ed04ec (0.3.0), demucs-infer ffe0080e.
- uv lock: `environments=["sys_platform == 'win32'"]` needed (tensorflow-macos otherwise blocks). Sync with --no-install-project (src/mvh not there yet).
- scripts/mvh-env.ps1 .cmd, scripts/run.ps1, scripts/smoke/imports.py written. Added audioread dep (piano_transcription_inference).
- Cmd: powershell.exe -NoProfile -File scripts/run.ps1 python scripts/smoke/imports.py

## Milestone 2 (done): scripts
- scripts/{mvh-env.ps1,mvh-env.cmd,run.ps1,bootstrap.ps1,heavy_lock.py,fetch_models.py,smoke/{imports,prewarm_numba}.py}. heavy_lock tested (2 slots, stale pid, >3h, CLI run).
- Models: fetch_models.py (stdlib) is data-driven (SPEC list), writes models.lock.json; log at %LOCALAPPDATA%\mvh\fetch.log. Re-run is idempotent: `powershell -NoProfile -File scripts/run.ps1 python scripts/fetch_models.py`
- Model sources found: beat_this cloud.cp.jku.at; allin1 HF taejunkim/allinone; demucs-onnx HF StemSplitio/htdemucs{,-6s}-onnx (fp16weights); MMS_FA dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt; essentia.upf.edu/models/*/*.onnx; piano zenodo 4034264; madmom raw.githubusercontent CPJKU/madmom_models; CLAP = Xenova/larger_clap_music_and_speech (no Xenova larger_clap_music exists).
- lv-chordia weights are inside the wheel (.venv/share/lv-chordia/cache_data) -> recorded as bundled.
## Next: check fetch.log finished + rhubarb unzipped, then smoke tests (scripts/smoke/*.py), spike doc, report.
- smoke so far PASS: ffmpeg ffprobe node dsp_core midi_json_eval ruff_pytest httpx text_tools demucs_onnx beat_this swift_f0 rmvpe skey ced allin1(offline hf-cache) madmom. Run: MVH_RUN_OFFLINE=1 powershell -NoProfile -File scripts/run.ps1 python scripts/smoke/smoke_tools.py --only X

## Milestone 3 (done): models + smoke
- models.lock.json: 21 entries (18 downloaded + 3 bundled-in-wheel), 5.85 GB, all sha256-pinned; hf revisions resolved; `fetch_models.py` re-run verifies hashes.
- HF-cache layout hard-linked at %LOCALAPPDATA%\mvh\hf\hub for allin1 + demucs-onnx; madmom weights under models\xdg\madmom_infer (XDG_CACHE_HOME set in env scripts); Rhubarb at bin\rhubarb\Rhubarb-Lip-Sync-1.14.0-Windows\rhubarb.exe (MVH_RHUBARB).
- Smoke: scripts/smoke/smoke_tools.py - all PASS offline (results %LOCALAPPDATA%\mvh\smoke\results.json). Gotchas: speechbrain symlink WinError1314 -> LocalStrategy.COPY + overrides pretrained_path; rhubarb: use `-f json -o file` (not --machineReadable); allin1 has no AllInOneSession in 3.1.0 -> analyze(stems_input=StemsInput(paths)) ; PS Set-Content -Encoding UTF8 writes BOM (read utf-8-sig); never name a script inspect.py.
- mvh editable-installed (uv sync --frozen --extra anthropic) since src/mvh/__init__.py exists.
## Next: final full smoke run, SPIKE doc docs/spike/main.md, report docs/build/reports/env-main.md, structured output.
## DONE 13:10: spike doc + report written; all smoke PASS. Only the structured summary remains.
