# env-sep progress
Started 2026-11-08. Resume from the last checked item.
- [ ] 1 envs/sep cpu venv
- [ ] 1b rocm venv (45 min box)
- [ ] 2 models fetched + fragment
- [ ] 3 separation x4
- [ ] 4 vulkan whisper
- [ ] 5 docs/spike/sep.md + report

## 12:50 status
- DONE envs/sep/cpu (pyproject+uv.lock, venv at envs/sep/.venv-cpu): torch 2.15.0+cpu, audio-separator 0.48.0. Needs extra dep `audioread` (librosa 1.0 dropped it).
- DONE envs/sep/rocm (venv envs/sep/.venv-rocm): torch 2.11.0+rocm7.13.0 from AMD index. Needed direct deps rocm[libraries]==7.13.0, rocm-sdk-core, rocm-sdk-libraries-gfx120x-all (uv sources only apply to direct deps), + override-dependencies triton; sys_platform=='never' (win wheel declares linux-only triton). torch.cuda.is_available()=True on gfx1201, matmul OK. (first attempt ~12:41-12:50)
- Commands: cd envs/sep/<variant>; UV_PROJECT_ENVIRONMENT=../.venv-<variant> python -m uv lock|sync --frozen ; UV_CACHE_DIR=%LOCALAPPDATA%\mvh\uvcache
- DONE models fetched via envs/sep/tools/fetch_models.py -> models.fragment.json (4 entries). GitHub 502 once: retry.
- NEXT: ffmpeg decode songs, separation driver (tools/separate.py), small ROCm separation smoke, then 4 songs.
Gotchas: audio-separator reads input with librosa.load(sr=44100) (resamples!). Float WAV out needs use_soundfile=True and FLOAT input subtype. normalise via normalization_threshold=100, amplification_threshold=0.

## 13:05 status
- ROCm separation WORKS end to end (smoke 30 s then full). Driver: envs/sep/tools/separate_song.py; batch: envs/sep/tools/run_all.sh rocm 4 (overlap 4), logs tests/.cache/real/_logs/sep-rocm*.log. Order newton, jeremy, megafauna, versatile. Resumable (skips finished steps via _work/timings.json).
- TRAPS found: (1) Separator() ctor rejects normalization_threshold>1 -> set attribute after construction (done in make_separator). (2) audio-separator shells out to bare `ffmpeg` -> prepend ffmpeg bin to PATH. (3) audioread missing dep. (4) float WAV needs use_soundfile=True + float32 WAV input.
- Models: sw=BS-Roformer-SW.ckpt, mel vocals=vocals_mel_band_roformer.ckpt (Kimberley Jensen, SDR 12.6 top in zoo), karaoke=mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt run on the Mel vocals (vocals=lead, instrumental=backing), DrumSep on SW drums.
- ggml fetch: envs/sep/tools/fetch_ggml.py (background; large-v3 is 3 GB). whisper runner: envs/sep/tools/whisper_vulkan.py (written, untested).
- NEXT: after ROCm 4 songs -> whisper vulkan jeremy/newton; CPU full run of newton into sep/cpu_ref (6 threads, background); docs/spike/sep.md; report.

## 13:25 status
- ROCm separation of all 4 songs DONE (tests/.cache/real/<slug>/sep/index.json, overlap 4). totals SW/mel/karaoke/drumsep per song e.g. newton 71/52/48/11 s. Stems-sum residuals: newton -36.0, jeremy -30.3, megafauna -23.6 (fails -30 gate: model property), versatile -35.2 dB. TODO re-run post step (cheap, resumable) so index uses 20 dB significance floor: run_all.sh again after whisper batch (skips model steps).
- Versatile corrupt FLAC frame is the LAST frame (10043392=2452*4096 decoded vs 10045683 declared): no timebase shift, ~52 ms tail lost.
- Whisper vulkan: works on Vulkan0=RX 9070. TRAP: the Silero VAD (vad_model) step is ~1 s per audio second (CPU) -> turbo-q8 60 s: 2.8 s without VAD, 90 s with. Batch running: envs/sep/tools/run_whisper_all.sh -> tests/.cache/real/_logs/whisper.log (ends with ALLDONE).
- NEXT: after whisper batch: CPU run newton (run_all variant cpu into sep/cpu_ref), docs/spike/sep.md, report, lock copies.

## 13:37 status
- whisper vulkan batch DONE (newton+jeremy; turbo-q8 novad/vad, large-v3 novad, cpu novad newton). summary in whisper_vulkan/summary.json + index.json. VAD path: 258 s newton / 359 s jeremy vs 4.6/7.3 s novad; jeremy VAD timestamps run past file end (last_t 330.7 > 316.6 s) = VAD time-mapping bug => do NOT use vad_model.
- ROCm post step re-run with 20 dB floor (indexes final).
- CPU full run newton started 13:36 -> sep/cpu_ref (log tests/.cache/real/_logs/sep-cpu-newton.log), 6 threads, overlap 4. When done: compare cpu vs rocm stems (max abs diff, dB), record timings.
- TODO: docs/spike/sep.md, report docs/build/reports/env-sep.md, lock copies envs/sep/uv.{cpu,rocm}.lock.

## 14:30 FINAL
All tasks done. CPU newton full run: 2857.7 s, matches ROCm to -110 dB. docs/spike/sep.md complete. Report: docs/build/reports/env-sep.md. Lock copies envs/sep/uv.{cpu,rocm}.lock made.
