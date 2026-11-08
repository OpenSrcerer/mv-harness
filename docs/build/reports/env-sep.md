# env-sep report

Status: done. Full write-up with commands, timings and evidence: `docs/spike/sep.md`. Progress log: `docs/build/progress/env-sep.md`.

## Result
- `envs/sep/cpu` (PyPI torch 2.15.0+cpu) and `envs/sep/rocm` (AMD torch 2.11.0+rocm7.13.0 for gfx1201) are two uv projects with their own locks and venvs (`.venv-cpu`, `.venv-rocm`); lock copies `envs/sep/uv.cpu.lock` and `uv.rocm.lock`.
- ROCm worked on the first honest attempt (about 9 min, no driver or security change): `torch.cuda.is_available()` True, all four models ran on `cuda`.
- audio-separator 0.48.0 is configured to not normalise (attribute set after construction, because the constructor rejects 100.0), float WAV out via `use_soundfile=True`.
- Models fetched and SHA-pinned in `envs/sep/models.fragment.json` (4 separator models + 2 ggml whisper models + Silero VAD).
- All 4 songs separated on ROCm into `tests/.cache/real/<slug>/sep/` with `index.json` (about 1.0x real time per song; 182.8 s for newton to 333.5 s for jeremy). Newton also run in full on CPU (2857.7 s) into `sep/cpu_ref/`; CPU and ROCm outputs agree to -110 dB or better.
- Vulkan whisper on jeremy and newton-vs-nye: `tests/.cache/real/<slug>/whisper_vulkan/` (turbo q8_0, large-v3, Silero VAD).

## Key findings
- Stems-sum residual vs mix: newton -36.0, jeremy -30.3, megafauna -23.6 (fails the -30 dB gate), versatile -35.2 dB. This is a BS-RoFormer-SW property, not normalisation (significant stems have LS gain 0.00-0.09 dB, peaks above 1.0 preserved). Re-baseline the gate to -20 dB.
- MEGAFAUNA: Mel-RoFormer `vocals` is -12.8 dB vs the mix while SW's vocals are -47 dB (synth leads heard as vocals). Vocal presence must not rely on stem energy.
- Versatile's corrupt FLAC frame is the last frame (52 ms of tail lost); no timebase shift.
- ffmpeg whisper filter: the Silero VAD option is CPU-bound (about 1 s per audio second) and yields timestamps past the end of the file; without VAD turbo q8_0 on Vulkan is 37-44x real time. Use it as a no-VAD draft path only.

## Change requests (for the orchestrator; none touches root pyproject or envelope schemas)
1. PLAN 3.1: ROCm pin is 2.11.0+rocm7.13.0; two uv projects; set `normalization_threshold` after construction.
2. PLAN 7 / R-ML: stems-sum gate to -20 dB; gain gate 0.1 dB within 6 dB of the mix and 0.5 dB within 20 dB.
3. Runner: ffmpeg bin first on PATH for the worker; `PYTHONPATH=<repo>/src` for mvh in the worker.
4. Merge `envs/sep/models.fragment.json` into `models.lock.json`; separator `revision` is the mutable tag `model-configs`, so SHA-256 is the pin.
5. PLAN 5 lyrics: Vulkan whisper filter only without `vad_model`.
