# Spike: separator worker env (`envs/sep`) and Vulkan whisper

Owner: env-sep · 2026-11-08 · machine: Ryzen 7 9800X3D, RX 9070 16 GB (gfx1201), Windows 11, driver 32.0.32015.7029.
No lyric text appears in this file. All numbers come from `tests/.cache/real/<slug>/sep/index.json` and
`tests/.cache/real/<slug>/whisper_vulkan/index.json` (gitignored).

## 1. Verdicts

| Tool | Verdict | Fallback |
|---|---|---|
| audio-separator 0.48.0 in a worker env (cpu variant, PyPI torch 2.15.0+cpu) | **go** | none needed |
| audio-separator 0.48.0 on AMD ROCm torch 2.11.0+rocm7.13.0 (preview) | **go** (worked on the first honest attempt, about 9 minutes from the first `uv lock` to a passing smoke test; no driver or security change) | the cpu variant (same models, 14-19x slower per model, 47.6 min for a 170 s song) |
| BS-RoFormer-SW 6-stem, Mel-RoFormer vocals, karaoke lead/backing, MDX23C DrumSep | **go** on both variants | `lead_vocals := vocals` if the karaoke model is unavailable |
| No-normalisation configuration (section 4) | **go**, but needs an attribute-after-construct workaround | none |
| ffmpeg 9.0.2 `whisper` filter on Vulkan, **without** `vad_model` | **go as a draft/fallback transcriber** | faster-whisper (PLAN default) |
| the same filter **with** `vad_model` (ggml Silero) | **no-go** (about 1 s of wall time per second of audio, and timestamps drift past the end of the file) | run our own VAD or gate by stem activity, then use the filter without VAD |

## 2. Layout of `envs/sep/`

Two uv projects (not workspace members), one lock each, separate venvs:

```
envs/sep/
  cpu/pyproject.toml   cpu/uv.lock        -> venv envs/sep/.venv-cpu
  rocm/pyproject.toml  rocm/uv.lock       -> venv envs/sep/.venv-rocm
  uv.cpu.lock  uv.rocm.lock               exact copies of the two uv.lock files (the names PLAN section 6 uses)
  models.fragment.json                    sep.* and ggml.* entries, SHA-256 pinned (models.lock.json schema)
  tools/                                  separate_song.py  mvh_locks.py  fetch_models.py  fetch_ggml.py
                                          whisper_vulkan.py  run_all.sh  run_whisper_all.sh
  .gitignore                              .venv-*  *.log
```

Why two projects rather than extras in one: uv cannot express "torch from PyPI" and "torch from the AMD index" as two
resolutions of one lockfile without `conflicts`, and the two variants must be locked and synced independently.

Rebuild (the orchestrator does this; agents use `UV_NO_SYNC=1` afterwards):

```
set UV_CACHE_DIR=%LOCALAPPDATA%\mvh\uvcache
cd envs\sep\cpu  && set UV_PROJECT_ENVIRONMENT=..\.venv-cpu  && <python312> -m uv sync --frozen
cd envs\sep\rocm && set UV_PROJECT_ENVIRONMENT=..\.venv-rocm && <python312> -m uv sync --frozen
```

Installed (cpu): torch 2.15.0+cpu, audio-separator 0.48.0, onnxruntime 1.31.1, numpy 2.5.4, librosa 1.0.0, numba 0.68.1. About 1 GB.
Installed (rocm): torch 2.11.0+rocm7.13.0, rocm / rocm-sdk-core / rocm-sdk-libraries-gfx120x-all 7.13.0, the same other versions. About 5 GB.
`torchaudio` is **not needed** (audio-separator never imports it), so no AMD torchaudio is installed. `torchvision 0.26.0` is pulled
from PyPI as a transitive dependency; it is never imported.

### Resolution traps (rocm lock)

1. `audio-separator>=0.48` requires `torch>=2.13` on macOS arm64 only; AMD's newest torch is 2.11.0. Fix: `[tool.uv] environments = ["sys_platform == 'win32' and platform_machine == 'AMD64'"]`.
2. AMD's torch wheel pins `rocm[libraries]==7.13.0`, which pins `rocm-sdk-core` and `rocm-sdk-libraries-gfx120x-all`. `tool.uv.sources` only applies to **direct**
   dependencies, so `rocm[libraries]`, `rocm-sdk-core` and `rocm-sdk-libraries-gfx120x-all` must be listed as direct dependencies, each with `{ index = "amd" }`.
3. The Windows torch wheel carries an unconditional `triton==3.6.0+rocm7.13.0`, but the AMD index has Linux-only triton wheels. Fix:
   `override-dependencies = ["triton; sys_platform == 'never'"]` (same trick as the plan's tensorflow override).
4. The index `https://repo.amd.com/rocm/whl/gfx120X-all/` is declared `explicit = true`, so **only** torch, rocm, rocm-sdk-core and rocm-sdk-libraries-gfx120x-all come from it (12 lines of `uv.lock` mention it). Locking took about 1 s (uv read wheel metadata by range requests), so the "no PEP 658" worry in the survey did not cost a full download.
5. `audioread` must be a direct dependency in **both** variants: audio-separator imports it and librosa 1.0 no longer installs it.

## 3. ROCm verdict and evidence

- `torch.cuda.is_available() == True`, `torch.version.hip == 7.13.99004`, device `AMD Radeon RX 9070`, `gcnArchName=gfx1201`, 16304 MB, 28 CUs.
- A 4096x4096 float32 matmul on the device ran (0.6 s including first-use initialisation).
- audio-separator picks the device itself ("CUDA is available in Torch, setting Torch device to CUDA"); all four models report `dev=cuda`.
  It also prints "CUDAExecutionProvider not available in ONNXruntime": harmless, because none of the four models uses onnxruntime.
- All four songs were separated end to end on ROCm (section 7). Whisper on Vulkan was run on the same card, separately.
- Cost: first model use took 12 s in the 30 s smoke test (kernel setup); later loads are 0.7-2.5 s.
- Not tested: the 2.9.1+rocm7.2.1 "stable" stream from repo.radeon.com (not needed; the preview worked).
- Caveats: it is a preview stream (rocm7.13). Pin it in the lock (done) and let `mvh doctor` re-run the smoke test (`torch.cuda.is_available()` plus a 256x256 matmul).
- GPU results are not bit-identical to CPU but agree to -110 dB or better on the main stems (section 7): NF1 should compare GPU stages with a tolerance, as planned.

## 4. audio-separator configuration (no normalisation, float WAV)

Implemented in `tools/separate_song.py::make_separator`. Facts verified in the 0.48.0 source:

- `Separator(normalization_threshold=100.0)` **raises** `ValueError` (the constructor accepts 0 < x <= 1). The value is only read at `load_model()`,
  so construct with `1.0` and then set `sep.normalization_threshold = 100.0` and `sep.amplification_threshold = 0.0` before `load_model`.
  `spec_utils.normalize` only scales down when peak > max_peak and only scales up when `0 < peak < min_peak`, so with (100, 0) it is a no-op.
  The mix is also "normalised" inside `MDXCSeparator.separate`, with the same thresholds, so it is a no-op there too.
- Float output needs `use_soundfile=True` **and** a float32 WAV input: the output subtype is copied from the input (`sf.info(input).subtype`, here `FLOAT`).
  With the default pydub writer everything becomes int16 and is clipped.
- The input is read with `librosa.load(path, sr=44100)`. All four songs are 44.1 kHz stereo so there is no resampling; a 48 kHz input would be resampled to 44.1 kHz,
  and the stems would then be 44.1 kHz. The parent must resample them back (or decode to 44.1 kHz and use that as the stem timebase).
- audio-separator shells out to a bare `ffmpeg` at construction (`check_ffmpeg_installed`): the worker must have the ffmpeg 9.0.2 `bin` directory first on PATH.
- Other settings used: `sample_rate=44100`, `output_format="WAV"`, `mdxc_params={"overlap": 4}` (see below), threads capped at 6
  (`OMP/OPENBLAS/MKL/NUMBA_NUM_THREADS=6`, `torch.set_num_threads(6)`, `set_num_interop_threads(1)`).
- Overlap: the SW yaml default is `num_overlap: 2`; we run **4** on both variants (more overlap-add, measurably slower, normally better SDR). DrumSep and the karaoke model have no yaml `num_overlap` and would default to 8; we pass 4 to all four for one consistent setting. Re-tune in W2 if the time is not worth it.
- `index.json` records the settings, so a run can be reproduced.

## 5. Models (SHA-pinned in `envs/sep/models.fragment.json`)

| id | files | size | role |
|---|---|---|---|
| `sep.bs-roformer-sw-6stem` | `BS-Roformer-SW.ckpt` + `.yaml` | 699 MB | 6 stems: bass, drums, other, vocals, guitar, piano |
| `sep.mel-roformer-vocals-kimberley` | `vocals_mel_band_roformer.ckpt` + `.yaml` | 913 MB | the best vocal stem in the UVR zoo list (SDR 12.6, the top "vocals" score of every model in `list_supported_model_files`) |
| `sep.mel-roformer-karaoke-aufr33-viperx` | `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt` + config | 913 MB | lead vs backing, run **on the Mel vocals stem**: `vocals` -> lead, `instrumental` -> backing |
| `sep.mdx23c-drumsep` | `MDX23C-DrumSep-aufr33-jarredou.ckpt` + `config_drumsep_mdx23c.yaml` | 438 MB | kick, snare, toms, hh, ride, crash, run on the SW drums stem |
| `ggml.whisper-large-v3-turbo-q8_0` | `ggml-large-v3-turbo-q8_0.bin` | 874 MB | Vulkan whisper |
| `ggml.whisper-large-v3` | `ggml-large-v3.bin` | 3.1 GB | Vulkan whisper, quality run |
| `ggml.silero-vad-v5.1.2` | `ggml-silero-v5.1.2.bin` | 0.9 MB | VAD (not recommended, section 9) |

- Downloads for the separator models go through audio-separator's own mirror (`github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs/`), which verifies a published checksum; we then computed our own SHA-256.
  **The `revision` is the mutable release tag `model-configs`**, so the SHA-256 is the real pin. Files live in `%LOCALAPPDATA%\mvh\models\separator`.
  Note that audio-separator also drops `download_checks.json` (and may fetch other json files) into that folder; `mvh models fetch` should ignore them.
- ggml files come from Hugging Face at pinned commits (`ggerganov/whisper.cpp@5359861c...`, `ggml-org/whisper-vad@9ffd54a1...`), and each SHA-256 equals the LFS etag. Files live in `%LOCALAPPDATA%\mvh\models\ggml`.
- Licences: BS-Roformer-SW is CC-BY-NC-SA-4.0 per the survey; the others were not verified in W0 (recorded as "not verified", personal use).
- Rejected candidates, from the zoo list: other Mel-RoFormer vocals models (unwa Big Beta 4/5e FT 12.5, unwa FT 12.4; BS-Roformer-Viperx-1296 12.1) are within about 0.1-0.5 dB SDR and some are far larger. Alternative karaoke models in the zoo (Gabox, becruily, anvuew, frazer-becruily) were not benchmarked; none has a published SDR except Gabox's.

## 6. Worker design (how mvh reaches the worker)

- The runner launches `envs/sep/.venv-<variant>/Scripts/python.exe -X utf8 -m mvh.worker <stage> job.json` with **`PYTHONPATH=<repo>/src`**.
  Verified with a stub package in both venvs (`import mvh` resolved from PYTHONPATH, with torch, onnxruntime, numpy, soundfile and librosa importing together in one process, no OpenMP clash).
- Chosen over a `--no-deps` install: there is no root `pyproject.toml` yet, the worker venv never needs rebuilding when mvh changes, and a stale installed copy cannot shadow `src/`.
  The worker stays valid as long as `mvh/__init__`, `worker.py` and `contract/` import only the stdlib and numpy (numpy 2.5.4 is in both venvs).
- The worker only does inference: it reads float32 WAV paths from job.json and writes float32 WAV plus `result.json` to scratch; the parent does the FLAC encoding.
- `tools/separate_song.py` is the reference implementation of the `separate_hq` job (decode, four model runs, post checks); W2's M3a should lift it into `src/mvh/stages/separate_hq/` and `mvh/worker.py`.
  Each model run is a separate **load/separate/free** cycle (the VRAM is released between models). Peak GPU memory was not measured; the 16 GB card was never the limit.
- Heavy slots: each model run takes a `heavy-N.lock` slot, plus `gpu.lock` for rocm (`tools/mvh_locks.py`, exclusive-create, stale if the pid is dead or older than 3 h). The slot is held per model run (not per song), so other agents are never blocked for more than one model.
  If the GPU is wanted while a slot is free, a waiting job releases its slot instead of hogging it (see `Slot.__enter__`).

Pipeline per song (`tools/separate_song.py`):

1. `ffmpeg -map 0:a:0 -ac 2 -ar 44100 -c:a pcm_f32le` -> `sep/mix_f32.wav` (decoder warnings captured into `index.json`).
2. BS-RoFormer-SW on the mix -> `sw_bass, sw_drums, sw_other, sw_vocals, sw_guitar, sw_piano`.
3. Mel-RoFormer vocals on the mix -> `vocals`.
4. Karaoke model on `vocals` -> `lead_vocals`, `backing_vocals`.
5. DrumSep on `sw_drums` -> `drums/{kick,snare,toms,hihat,ride,crash}` (`hh` renamed `hihat`).
6. `instrumental = mix - vocals` (float32, un-normalised). All stems are trimmed or padded to the mix length (they were already exactly equal: `output_lengths_before_align`).

Output (in `tests/.cache/real/<slug>/sep/`): `bass drums other guitar piano vocals_sw vocals lead_vocals backing_vocals instrumental` (+ `drums/*`) as float WAV, `mix_f32.wav`, `index.json`, and `_work/` (raw model outputs; deletable).
`vocals_sw` is SW's own vocals stem, kept so the six-stem sum can be checked; **`vocals` is the Mel-RoFormer stem** and is what `lead_vocals`, `backing_vocals` and `instrumental` derive from.

## 7. Timings (ROCm, overlap 4, nothing else of ours running; seconds)

| song | dur s | SW 6-stem | Mel vocals | karaoke | DrumSep | total separate | real-time factor |
|---|---|---|---|---|---|---|---|
| newton-vs-nye | 170.4 | 71.5 | 52.4 | 48.0 | 10.9 | 182.8 | 1.07 |
| jeremy | 316.6 | 126.3 | 98.1 | 89.8 | 19.3 | 333.5 | 1.05 |
| megafauna | 217.2 | 86.0 | 63.6 | 58.7 | 13.7 | 222.0 | 1.02 |
| versatile | 227.7 | 87.6 | 66.5 | 60.3 | 15.9 | 230.3 | 1.01 |

Model loads are 0.7-2.5 s each. So separate_hq on ROCm costs about **1.0x the song length** (about 5.5 min for Jeremy).

### CPU variant (newton-vs-nye only, 6 threads, overlap 4, full pipeline, seconds)

| step | cpu | rocm | slowdown |
|---|---|---|---|
| SW 6-stem | 1000.0 (another agent's job was running during this step) | 71.5 | 14.0x |
| Mel vocals | 832.3 | 52.4 | 15.9x |
| karaoke | 816.4 | 48.0 | 17.0x |
| DrumSep | 209.0 | 10.9 | 19.2x |
| total | **2857.7 (47.6 min)**, real-time factor 16.8 | 182.8, factor 1.07 | 15.6x |

Extrapolated CPU cost: about 90 min for a 5-minute song (Jeremy), so the cpu variant is a fallback, not a normal path. Outputs: `tests/.cache/real/newton-vs-nye/sep/cpu_ref/` (full set, own `index.json`).

**CPU and ROCm outputs agree**: relative difference per stem (`cpu_ref/compare_vs_rocm.json`, `tools/compare_variants.py`) is -110 to -128 dB for the SW stems, vocals, drums and instrumental (max abs sample difference 1e-5), -102 dB for the weakest drum stems, and -73 dB for `lead_vocals` / -51 dB for `backing_vocals` (the karaoke model amplifies small differences; max abs difference 0.002).
So GPU float noise is far below anything audible or analysable, and NF1's "compare GPU stages with a tolerance" can use a generous one (for example -60 dB relative for stems).


## 8. Invariants (stems-sum and gain)

Definitions (`checks` in each `index.json`):
- `stems_sum_vs_mix.residual_db = 10 log10(|mix - sum(six SW stems)|^2 / |mix|^2)`.
- Gain of a stem relative to the mix = the least-squares weight `w_i` in `mix ~ sum(w_i * stem_i)`, in dB. If a model rescaled a stem, `w_i` would move away from 0 dB.
  Stems more than 20 dB below the mix RMS are excluded (the fit is ill-conditioned: a stem at -100 dBFS gets a "gain" of +30 dB).

| song | sum residual dB (gate -30) | significant stems: LS gain dB |
|---|---|---|
| newton-vs-nye | **-36.0** | bass 0.007, drums 0.000, other 0.088, vocals 0.007 |
| jeremy | **-30.3** | bass 0.013, drums 0.039, vocals 0.022, guitar 0.051 |
| megafauna | **-23.6 (fails)** | bass 0.058, drums 0.091, other 0.172, guitar 0.454 |
| versatile | **-35.2** | bass 0.005, drums 0.009, other 0.088 |

Other checks, all four songs: `instrumental + vocals` equals the mix to -152 dB or better (exact by construction); `lead + backing` equals `vocals` to -151 dB or better (the karaoke model's second output is the difference);
sum of the six DrumSep stems vs the SW drums: -31.4 (newton), -29.0 (jeremy), -23.6 (megafauna), -20.9 (versatile) dB.
Peaks above 1.0 are preserved (Versatile: drums 1.85, bass 1.39; Jeremy: instrumental 1.50), which proves nothing was re-normalised. Stem lengths equal the mix length to the sample.

Conclusions and re-baselines (for the orchestrator):
- **There is no normalisation**: significant stems carry LS gains of 0.00-0.09 dB. The "within 0.1 dB" gate holds for every stem within 6 dB of the mix, and for every stem within 20 dB except on megafauna (other 0.17 dB at 8.5 dB below the mix, guitar 0.45 dB at 13.5 dB below), which is caused by that song's large model residual, not by scaling. `gain_pass` in `index.json` applies 0.1 dB to the whole 20 dB band, so it is False for megafauna. Proposed gate: `|gain| <= 0.1 dB` for stems within 6 dB of the mix and `<= 0.5 dB` within 20 dB (all four songs pass).
- **The -30 dB six-stem sum gate is a model property, not a plumbing property**: BS-RoFormer-SW is not mass-conserving, and an electronic track with dense synths leaks more (megafauna -23.6 dB). Proposed gate: `<= -20 dB` for the SW sum. If an exactly-summing stem set is wanted, add `mix - sum(stems)` to `other` (the residual is then -150 dB by construction). `instrumental` is already exact.
- Content note: on MEGAFAUNA the Mel-RoFormer `vocals` stem is -12.8 dB relative to the mix while SW's `vocals_sw` is -47 dB. The Mel model hears the vocal-like synth leads as vocals. `present` for vocals must therefore not come from stem energy; use the instruments tagger (PLAN stem_activity/instruments) and the lyrics source.
- Versatile's corrupt FLAC frame is the **last** frame (decoded 10,043,392 samples = 2452 x 4096; the header declares 10,045,683): ffmpeg drops the final 2291 samples (52 ms). No timebase shift. ingest should record the missing tail instead of treating it as an error.

## 9. Vulkan whisper (ffmpeg 9.0.2 `whisper` filter)

Run by `tools/whisper_vulkan.py`: cwd = `%LOCALAPPDATA%\mvh\models\ggml`, relative model names, a **relative `destination`** inside that folder (moved afterwards), `max_len=1`, `format=json`, `language=en`, `queue=20`, input = the Mel `vocals.wav` (44.1 kHz float stereo; the filter resamples).
Device: `ggml_vulkan: 0 = AMD Radeon RX 9070`, 874 MB buffer on Vulkan0 (device 1 is the iGPU and is not used). Gpu and heavy locks held during runs.

| song | model | VAD | device | wall s | audio s | RTF | words |
|---|---|---|---|---|---|---|---|
| newton-vs-nye | turbo q8_0 | no | Vulkan | 4.6 | 170.4 | 0.027 | 488 |
| newton-vs-nye | large-v3 | no | Vulkan | 15.6 | 170.4 | 0.092 | 445 |
| newton-vs-nye | turbo q8_0 | no | CPU (`use_gpu=0`) | 65.3 | 170.4 | 0.38 | 477 |
| newton-vs-nye | turbo q8_0 | **yes** | Vulkan | 257.8 (another agent's CPU job was running) | 170.4 | 1.51 | 500 |
| jeremy | turbo q8_0 | no | Vulkan | 7.3 | 316.6 | 0.023 | 210 |
| jeremy | large-v3 | no | Vulkan | 10.3 | 316.6 | 0.033 | 265 |
| jeremy | turbo q8_0 | **yes** | Vulkan | 359.1 | 316.6 | 1.13 | 240 |

Findings (`whisper_vulkan/summary.json` has the per-run statistics):
1. **The ggml Silero VAD step dominates and is CPU-bound**: on a 60 s excerpt, 90 s with VAD vs 2.8 s without (GPU), and 114 s with VAD on CPU. Cost is about one second per second of audio and does not depend on `use_gpu`.
2. **With VAD the timestamps are wrong**: Jeremy's last word ends at 330.7 s in a 316.6 s file (14 s past the end), so VAD-trimmed time is not mapped back correctly. Without VAD the last word is at 300.5 s, 16 s before the end (the outro has no lyrics).
3. The filter has **no word probabilities** and fixed `queue` windows; with `max_len=1` some items are still long (up to 20 s): newton turbo 4 items over 4 s, jeremy 9 (no VAD) and 14 (VAD). A post-filter must split or drop items longer than about 2 s.
4. large-v3 (fp16) emits bracketed non-lyric tags (5 in newton, 34 in jeremy) and non-monotonic start times (both songs); turbo-q8 emitted none. Needs the hallucination filter of PLAN section 5.
5. Speed: turbo q8_0 on Vulkan is 37-44x real time; large-v3 on Vulkan 11-31x; CPU turbo q8_0 2.6x. Raw JSON and normalised `*.words.json` are in `whisper_vulkan/`; contents are lyrics, so they stay in `tests/.cache/`.

**Go/no-go.** Go for a draft transcript and as the fast path behind a flag (turbo q8_0, no VAD, gated to the vocal activity mask). No-go for VAD and for timing authority: word timing still comes from CTC alignment on `lead_vocals`, as planned.
Whisper's accuracy against the LRCLIB text was not scored here (no lyric text may be printed and the LRCLIB cache belongs to another agent); the structural statistics above are all that W0 measured.

## 10. Exact commands

Environment (PowerShell; `<py>` = `C:\Users\OpenSrcerer\AppData\Local\Programs\Python\Python312\python.exe`; ffmpeg bin = the Gyan 9.0.2 `bin` directory):

```
$env:MVH_FFMPEG = "<ffmpeg bin>\ffmpeg.exe"
$env:UV_CACHE_DIR = "$env:LOCALAPPDATA\mvh\uvcache"
# one song, ROCm (use .venv-cpu and --variant cpu for the CPU variant)
envs\sep\.venv-rocm\Scripts\python.exe -X utf8 envs\sep\tools\separate_song.py --variant rocm --slug jeremy `
   --src "songs\Jeremy (Redux Version).flac" --out tests\.cache\real\jeremy\sep --overlap 4
# all four songs (bash)
envs/sep/tools/run_all.sh rocm 4
# models (once; the cpu venv has audio-separator and requests)
envs\sep\.venv-cpu\Scripts\python.exe -X utf8 envs\sep\tools\fetch_models.py
envs\sep\.venv-cpu\Scripts\python.exe -X utf8 envs\sep\tools\fetch_ggml.py
# whisper on Vulkan (draft transcript, no VAD)
envs\sep\.venv-cpu\Scripts\python.exe -X utf8 envs\sep\tools\whisper_vulkan.py --slug jeremy --model ggml-large-v3-turbo-q8_0.bin --no-vad
# the underlying ffmpeg call (cwd = %LOCALAPPDATA%\mvh\models\ggml)
ffmpeg -nostdin -i vocals.wav -af "whisper=model=ggml-large-v3-turbo-q8_0.bin:language=en:queue=20:use_gpu=1:max_len=1:format=json:destination=out.json" -f null -
```

ROCm smoke test for `mvh doctor`: `python -c "import torch; assert torch.cuda.is_available(); a=torch.randn(256,256,device='cuda'); print(float((a@a).sum()), torch.version.hip)"`.

## 11. Change requests and notes for other agents

1. PLAN section 3.1 and section 12: the cpu and rocm variants are two uv projects (`envs/sep/cpu`, `envs/sep/rocm`), with copies named `uv.cpu.lock` and `uv.rocm.lock`. Replace "the spike picks 2.11.0+rocm7.13 or 2.9.1+rocm7.2.1" with **2.11.0+rocm7.13.0**.
2. Section 3.1, "audio-separator is always configured": add that `normalization_threshold=100.0` must be set as an attribute after construction (the constructor rejects values above 1).
3. Section 7 and the R-ML lens: re-baseline the stems-sum gate to -20 dB and the gain gate as in section 8.
4. The runner must put the ffmpeg bin first on PATH for the worker (audio-separator calls a bare `ffmpeg`).
5. `models.lock.json` merge: take every entry of `envs/sep/models.fragment.json` (the `envs` field says `sep-rocm`/`sep-cpu` for separator models and `main`/`ffmpeg-whisper` for ggml files). The separator `revision` is a mutable tag; rely on the SHA-256.
6. Lyrics section 5: replace "the ffmpeg whisper filter on Vulkan is used in `draft` or behind a flag" with "...without `vad_model`".
