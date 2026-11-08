# W0 spike: MAIN environment (env-main)

Date 2026-11-08 · Machine: Windows 11, Ryzen 7 9800X3D, RX 9070 (no CUDA) · Python 3.12.10 · uv 0.13.7 · ffmpeg/ffprobe 9.0.2 (Gyan full)

Everything below was verified on this machine. Smoke inputs are 5 s clips (25 s for the rap battle) cut from the four songs and two
SAPI TTS voices; **no lyric text was printed or written anywhere**. Raw results: `%LOCALAPPDATA%\mvh\smoke\results.json`
(28 checks, all PASS, offline: `HF_HUB_OFFLINE=1`, total about 75 s at 3 threads). Re-run: see "Commands".

Fingerprints for the cache key (NF2 "env lock hash"): `uv.lock` sha256 `38ef4ea6...` (142 packages, win32 only),
`models.lock.json` sha256 `fb288804...` (21 entries, 5.85 GB), `pyproject.toml` sha256 `6047315d...`.
(Prefixes only; compute the full hash at use time.)

## 1. Commands for later agents

Every shell command starts with the env script, and Python only runs through `uv run --frozen --no-sync`:

```powershell
. scripts\mvh-env.ps1                       # add -Offline for HF_HUB_OFFLINE=1 + MVH_OFFLINE=1 ; -Threads N (default 3)
uv run --frozen --no-sync python scripts\smoke\imports.py
uv run --frozen --no-sync pytest -q tests\unit\<stage>
uv run --frozen --no-sync ruff check src tests
uv run --frozen --no-sync mvh doctor        # once src/mvh/cli.py exists (console script `mvh = mvh.cli:main` is installed, editable)
```

* cmd twin: `call scripts\mvh-env.cmd [-Offline] [-Threads N]` (same variables; tested).
* One-liner for tools that cannot dot-source: `powershell -NoProfile -File scripts\run.ps1 python <script> <args>`
  (add `$env:MVH_RUN_OFFLINE=1` first for offline).
* Heavy work (real inference, 6 threads max inside a slot):
  `uv run --frozen --no-sync python scripts\heavy_lock.py run --owner <name> [--gpu] [--threads 6] -- <command...>` or
  `from heavy_lock import heavy; with heavy("<name>", gpu=False): ...` (path: `scripts/`). `heavy_lock.py status|cleanup` also exist.
* Bash tool: `powershell.exe -NoProfile -File scripts/run.ps1 python ...` works from Git Bash. In PowerShell 5.1 never add `2>&1` to
  native commands (it turns stderr into error records); in the Bash tool it is fine.
* **Never name a script `inspect.py`, `json.py`, `types.py`...** next to the code: the interpreter puts the script directory first on `sys.path`
  and numpy/onnxruntime break (it happened here once).
* Env variables set by `mvh-env.ps1`: `MVH_FFMPEG`, `MVH_FFPROBE`, `MVH_RHUBARB`, `MVH_THREADS` (3), `OMP/OPENBLAS/MKL/NUMBA/VECLIB/NUMEXPR_NUM_THREADS`,
  `TORCH_HOME`, `HF_HOME`, `AUDIO_SEPARATOR_MODEL_DIR`, `NUMBA_CACHE_DIR`, `NLTK_DATA`, `MVH_MODELS_DIR`, `XDG_CACHE_HOME` (madmom-infer weights),
  `UV_PYTHON`, `UV_CACHE_DIR`, `UV_NO_SYNC=1`, `PYTHONUTF8=1`, `PYTHONPATH=<repo>\src`, `HF_HUB_DISABLE_*`, `TOKENIZERS_PARALLELISM=false`.
  `KMP_DUPLICATE_LIB_OK` is deliberately never set (see the OpenMP result).
* Layout: `%LOCALAPPDATA%\mvh\{models, hf, torch, numba, nltk, uvcache, locks, bin, smoke, config.json}`. Models: `models\<dest>` per `models.lock.json`.
* Rebuild from scratch: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 [-SkipModels] [-SkipPrewarm]` (sync, config.json,
  model fetch + SHA verify, numba prewarm; idempotent). Models only: `uv run --frozen --no-sync python scripts\fetch_models.py [--only id,id] [--lock-only]`
  (never re-pins a changed file: a SHA mismatch aborts).

## 2. How each library is fed (verified recipes; local paths, arrays in)

| Tool | Verified call (all offline) |
|---|---|
| beat_this | `Audio2Frames(checkpoint_path=<models>/beat_this/final0.ckpt, device="cpu")(x_mono_f32, sr)` -> (beat, downbeat) logits at 50 fps; `Audio2Beats(..., dbn=False)` for the minimal postprocessor |
| all-in-one-infer 3.1.0 | **There is no `AllInOneSession` in 3.1.0** (survey names it). Use `allin1_infer.analyze(stems_input=StemsInput(bass, drums, other, vocals as float32 WAV paths we wrote), model="harmonix-all", device="cpu", include_activations=True, include_embeddings=True, demix_dir=, spec_dir=, multiprocess=False)`. Folds resolve offline through the HF-cache layout hard-linked under `%LOCALAPPDATA%\mvh\hf\hub` (no patching). Activations at 100 fps (`beat`, `downbeat`, `segment` [T], `label` [10,T]); embeddings `[4,T,24,8]`. `analyze` also accepts a custom `stem_provider` (in-memory route, untested) |
| demucs-onnx 0.3.4 | `separate(path)` goes through libsndfile (fails on Versatile). Use the array path instead: `ort.InferenceSession(<onnx>, SessionOptions(intra=n, inter=1), ["CPUExecutionProvider"])` + `demucs_onnx.inference._chunked_separate_single(sess, MODEL_REGISTRY[model].sources, mix_2xN_44100, progress=False)` (private but stable in 0.3.4). Models: `<models>/demucs-onnx/htdemucs{,-6s}-onnx/*_fp16weights.onnx` (also in the HF cache layout). 5 s of stereo: 1.3 s on 3 threads. Sum of stems vs mix is **not sample exact** (relative RMS 4.4 % htdemucs, 7.4 % 6s): do not assert the -30 dB invariant on `separate_fast` |
| madmom-infer 0.2.0 | `RNNDownBeatProcessor()` + `DBNDownBeatTrackingProcessor(beats_per_bar=[3,4], fps=100)`; weights resolved via `XDG_CACHE_HOME` (sha256-verified by the library) |
| S-KEY (ONNX) | `skey.onnx`: input `audio` `[1, samples]` float32 22.05 kHz mono peak-normalised, output `probs[24]` (softmax); labels in `config.json` `keyMap` |
| lv-chordia 1.1.0 | `chord_recognition(<our float32 wav path>, "submission")` (checkpoints are inside the wheel: `.venv\share\lv-chordia\cache_data`, 5 x 5.7 MB; prints progress to stderr; 3 s for 5 s of audio, mostly start-up) |
| CED-base ONNX | input `waveform [B, samples]` 16 kHz, output `logits [B, 527]`; apply sigmoid; labels `config.json` `id2label` |
| CLAP (Xenova larger_clap_music_and_speech, quantized) | `ClapFeatureExtractor.from_pretrained(<dir>)(audio_48k, sampling_rate=48000)` -> `input_features [1,1,1001,64]`; audio model -> `audio_embeds[1,512]`; `AutoTokenizer.from_pretrained(<dir>)` + text model (input `input_ids` only) -> `text_embeds[B,512]`. Sanity: TTS voice -> "a man speaking" (cos 0.28), Jeremy clip -> "distorted electric guitar rock" (0.32) |
| basic-pitch 0.4.0 | `Model(basic_pitch.ICASSP_2022_MODEL_PATH)` runs on **onnxruntime** (bundled `nmp.onnx`); `predict(<our float32 22.05 kHz wav path>, model)`. Its loader is librosa (reads our wav fine); to feed arrays call the model on `window_audio` output yourself |
| piano_transcription_inference | `PianoTranscription(checkpoint_path=<models>/piano_transcription/note_F1=0.9677_pedal_F1=0.9186.pth, device=torch.device("cpu"))`; `transcribe(audio_16k_mono, midi_path)`; the library's own wget fallback is never reached (file > 160 MB check passes) |
| SwiftF0 / RMVPE | `SwiftF0(threads=n).detect(y16k, 16000, fmin=65, fmax=1400)`; `RMVPE(model_path=<models>/rmvpe/rmvpe.onnx, device="cpu").predict(y, 16000)` (file sha256 equals the library's expected value) |
| Essentia heads | msd-musicnn `melspectrogram [N,187,96]` -> `embeddings`; emomusic/deam heads take `embeddings` (deam input name `model/Placeholder:0`); discogs-effnet `[N,128,96]`; numpy mel port in `docs/research/prototypes/lyrics-meaning/mood_onnx.py` (copied into `scripts/smoke/smoke_tools.py::_mel_port`) |
| faster-whisper 1.2.1 | `WhisperModel(<models>/faster-whisper/large-v3, device="cpu", compute_type="int8", cpu_threads=n).transcribe(array_16k, ...)`; TTS sentence transcribed exactly (min word prob 0.88). A 5 s sung clip with `vad_filter=True` returned 0 words (expected: sparse vocals) |
| stable-ts 2.19.1 | `stable_whisper.load_faster_whisper(<same dir>, device="cpu", compute_type="int8", cpu_threads=n)`; `.transcribe(array)` and `.align(array, text, language="en")` both work (9 words) |
| MMS_FA | `torchaudio.pipelines.MMS_FA.get_model(with_star=False, dl_kwargs={"model_dir": "<models>/mms_fa"})` loads `model.pt` with no download. `torchaudio._extension._IS_ALIGN_AVAILABLE` is **True** (compiled `forced_align` present), so the vendored Viterbi is only a fallback. Aligned a 9-word TTS sentence (0.12-2.53 s in a 3.37 s clip) |
| speaker embeddings | ECAPA: `EncoderClassifier.from_hparams(source=<dir>, savedir=<scratch>, local_strategy=LocalStrategy.COPY, overrides={"pretrained_path": "<dir>"})` then `encode_batch(tensor)` (192-d). WeSpeaker ONNX: `torchaudio.compliance.kaldi.fbank(x*32768, 80 mel, hamming, dither 0)` + mean-subtraction -> `voxceleb_resnet34_LM.onnx` (`feats [B,T,80]` -> `embs [B,256]`). TTS check: ECAPA same-voice cos 0.81 / different voice 0.10; WeSpeaker 0.84 / 0.23. **Pick ECAPA first** (wider margin, same torch env); WeSpeaker is the ONNX fallback |
| Rhubarb 1.14.0 | `rhubarb.exe -f json -o out.json [-d dialog.txt] in16bit.wav` (16 kHz 16-bit PCM). Do **not** use `--machineReadable`/`-q`: stdout then carries no JSON. Output `mouthCues[{start,end,value A-H|X}]`. Ran on TTS (with and without dialog) and on a htdemucs-separated sung vocal (shapes A-G, X) |
| ffmpeg | see row below; always `-map 0:a:0 -vn -f f32le -` and read the pipe into numpy |

## 3. DEPENDENCY ROWS (one per tool named in PLAN 5 and 7)

Columns: tool | package / binary | env | version | lock line | licence | model files (lock id) | smoke result | go / fallback.
"uv.lock" lines are the resolved pins (win32 only, CPU torch). Licence column is code licence; model licences are in `models.lock.json`.

| # | Tool (PLAN stage) | Package / binary | Env | Version | Lock line | Licence | Model files | Smoke | Go / no-go and fallback |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Decode, ebur128, chromaprint, mp3 encode (ingest, loudness, identity) | ffmpeg + ffprobe, Gyan full build | external | 9.0.2 | none (absolute path via `MVH_FFMPEG`) | GPL (full build) | none | PASS: whisper, vulkan, chromaprint, libmp3lame, libopus configured; filters `whisper` and `ebur128` registered; chromaprint muxer; **Versatile.flac decodes with `-map 0:a:0`** (30 s in 0.2 s); ebur128 -8.6 LUFS on a clip | **go** |
| 2 | Whisper on Vulkan (lyrics draft/fallback) | ffmpeg `whisper` filter | external | 9.0.2 | none | GPL | ggml + silero (env-sep) | filter present and Vulkan enabled; model benchmarks are env-sep's | go (flag/draft only); fallback faster-whisper |
| 3 | numerics | numpy | main | 2.5.4 | `numpy==2.5.4` | BSD-3 | none | PASS | **go** |
| 4 | numerics | scipy | main | 1.18.1 | `scipy==1.18.1` | BSD-3 | none | PASS (stft, signal, linalg) | go |
| 5 | DSP, HPSS, CQT, tempogram, PLP (spectral, rhythm, harmony) | librosa | main | 1.0.0 | `librosa==1.0.0` | ISC | none | PASS (mel, hpss, chroma_cqt 36 bpo, PLP, tempo; numba JIT pre-warmed, 12 s cold, 4.5 s warm) | **go** (`librosa.feature.tempo`, not `feature.rhythm.tempo`, in 1.0) |
| 5b | numba | numba / llvmlite | main | 0.68.1 / 0.50.0 | `numba==0.68.1` | BSD | none | PASS (parallel prange with torch+ct2+ort loaded) | go |
| 6 | Loudness (loudness) | pyloudnorm | main | 0.2.0 | `pyloudnorm==0.2.0` | MIT | none | PASS (-25.99 LUFS on a MEGAFAUNA clip; cross-check vs ffmpeg ebur128 is the loudness module's test) | go |
| 7 | Resampling, own WAV I/O | soxr; soundfile | main | 1.1.0; 0.14.0 | `soxr==1.1.0`, `soundfile==0.14.0` | LGPL-2.1+ ; BSD-3 | none | PASS (float WAV round trip exact). soundfile **fails on Versatile.flac** ("flac decoder lost sync"): own WAVs only | go; ffmpeg decodes all user audio |
| 8 | Palette (ingest) | scikit-learn; Pillow | main | 1.9.1; 13.0.0 | `scikit-learn==1.9.1`, `pillow==13.0.0` | BSD-3; MIT-CMU | none | PASS (k-means 5 colours) | go |
| 9 | Stems fast (separate_fast) | demucs-onnx | main | 0.3.4 | `demucs-onnx==0.3.4` | MIT (weights unclear / 6s probably CC-BY-NC) | `demucs_onnx_htdemucs`, `demucs_onnx_htdemucs_6s` (fp16weights) | PASS: htdemucs 4 stems and 6s 6 stems on arrays, 1.3 s per 5 s clip at 3 threads | **go** (array route, see recipes). Fallback: demucs-infer (torch) |
| 10 | Stems fast fallback | demucs-infer (vendored wheel) | main | 4.4.0 | `demucs-infer @ vendor/wheels/demucs_infer-4.4.0-py3-none-any.whl` (sha256 `ba34e159...`) | MIT | `htdemucs` weights not fetched (allin1 gets stems from us) | import PASS | go (unused fallback) |
| 11 | Stems HQ (separate_hq) | audio-separator 0.48, torch ROCm/CPU | sep | n/a | env-sep lock | MIT | env-sep | not mine | see env-sep spike |
| 12 | Beats (rhythm) | beat-this | main | 1.1.0 | `beat-this==1.1.0` | MIT | `beat_this` (final0 78 MB, small0 8 MB) | PASS: logits 251 frames per 5 s at 50 fps; final0 0.23 s, small0 0.07 s | **go** (primary tracker) |
| 13 | Structure + beats (allin1) | all-in-one-infer (vendored wheel) | main | 3.1.0 | `all-in-one-infer @ vendor/wheels/all_in_one_infer-3.1.0-py3-none-any.whl` (sha256 `c41d6203...`) | MIT | `allin1_harmonix` (8 folds, 11 MB) | PASS: harmonix-all, 8 folds, offline, 1.6 s for 5 s; activations and embeddings returned | **go** (stems must be WAV files we write) |
| 14 | DBN fallback (rhythm) | madmom-infer (vendored wheel) | main | 0.2.0 | `madmom-infer @ vendor/wheels/madmom_infer-0.2.0-py3-none-any.whl` (sha256 `f4013a7a...`) | BSD-2 (weights CC-BY-NC-SA) | `madmom_downbeats_blstm` (8 x pkl) | PASS: RNN activations `[500,2]`, DBN beats; numpy-2 behaviour confirmed | go (fallback to beat_this + PLP if it regresses) |
| 15 | Key (harmony) | S-KEY ONNX via onnxruntime | main | HF rev `9d90d2a9` (musetric/skey-onnx) | `onnxruntime==1.31.1` | code MIT; **weights non-commercial research** | `skey_onnx` | PASS: 24-way softmax sums to 1 | go (in-house key estimator stays as cross-check/fallback). The PyPI `skey` package is never installed (verified absent) |
| 16 | Chords (harmony) | lv-chordia | main | 1.1.0 | `lv-chordia==1.1.0` | MIT | `lv_chordia_ismir2019_chordnet` (bundled in wheel) | PASS (5-model ensemble, 3 s for 5 s, needs a path to a float32 wav) | go; fallback template + Viterbi |
| 17 | Mir metrics | mir_eval | dev | 0.8.2 | `mir-eval==0.8.2` (dev group) | MIT | none | PASS | go |
| 18 | Instruments (instruments) | onnxruntime + CED-base ONNX | main | ort 1.31.1 | `onnxruntime==1.31.1` | MIT; model Apache-2.0 | `ced_base_onnx` (87 MB) | PASS: 527 logits per 4 s window; Jeremy clip tags: Music, Grunge, Psychedelic rock | **go** |
| 19 | Zero-shot instruments (instruments) | CLAP ONNX via onnxruntime + transformers (feature extractor, tokenizer only) | main | transformers 5.22.2, tokenizers 0.23.3 | `transformers==5.22.2` | Apache-2.0 | `clap_larger_music_speech_onnx` (quantized audio+text, 208 MB) | PASS with discriminating prompts (see recipes) | **go with caveat**: Xenova exports `larger_clap_music_and_speech`, not `larger_clap_music` |
| 20 | Notes (notes) | basic-pitch (ONNX build, no TensorFlow) | main | 0.4.0 | `basic-pitch==0.4.0` + override `tensorflow; sys_platform=="never"`, `resampy>=0.4.3` | Apache-2.0 | `basic_pitch_nmp_onnx` (bundled) | PASS: backend onnxruntime, 28 note events on a 5 s clip | **go** |
| 21 | Piano notes (notes) | piano_transcription_inference + torchlibrosa + audioread (import-time dependency) | main | 0.0.6; 0.1.0; 3.1.0 | `piano-transcription-inference==0.0.6` | MIT; ckpt CC-BY-4.0 | `piano_transcription_crnn` (172 MB) | PASS: 82 note events, MIDI written, torch 2.15 loads the checkpoint | go (only when a piano stem is present) |
| 22 | Vocal f0 (vocals) | swift-f0 | main | 0.3.0 | `swift-f0==0.3.0` | MIT | `swift_f0_onnx` (bundled) | PASS (312 frames per 5 s at 16 kHz) | **go** |
| 23 | Vocal f0 arbiter (vocals) | rmvpe-onnx | main | 0.2.3 | `rmvpe-onnx==0.2.3` | MIT | `rmvpe_onnx` (362 MB, sha equals library constant) | PASS (501 frames per 5 s) | go |
| 24 | Mood (mood) | onnxruntime + Essentia ONNX heads + numpy mel port | main | ort 1.31.1 | `onnxruntime==1.31.1` | model CC-BY-NC-ND-4.0 | `essentia_msd_musicnn`, `essentia_discogs_effnet` (24 MB) | PASS: emoMusic and DEAM valence/arousal, 56 mood tags | go (valence low confidence) |
| 25 | Transcription (lyrics) | faster-whisper + ctranslate2 | main | 1.2.1 / 4.8.5 | `faster-whisper==1.2.1`, `ctranslate2==4.8.5` | MIT | `faster_whisper_large_v3` (3.09 GB CT2 fp16, run as int8) | PASS: exact on TTS sentence, load 3.3 s; array input (PyAV 19 breaks the library's own decoder, never used) | **go** |
| 26 | Alignment (lyrics) | torch + torchaudio MMS_FA `forced_align` | main | 2.15.0 / 2.11.1 | `torch==2.15.0`, `torchaudio==2.11.1` | BSD; **weights CC-BY-NC** | `mms_fa` (1.26 GB) | PASS: compiled `forced_align` available; 9 words aligned | **go**; vendored `ctc_viterbi.py` stays the fallback (golden-tested by the module owner) |
| 27 | Alignment fallback (lyrics) | stable-ts | main | 2.19.1 | `stable-ts==2.19.1` | MIT | shares the whisper files | PASS (`transcribe` and `align`) | go |
| 28 | Romanise, numbers, fuzzy (lyrics) | uroman; num2words; rapidfuzz | main | 1.3.1.1; 0.5.14; 3.14.6 | `uroman==1.3.1.1`, `num2words==0.5.14`, `rapidfuzz==3.14.6` | uroman custom (non-commercial); LGPL; MIT | none | PASS | go |
| 29 | Voices (voices) | SpeechBrain ECAPA-TDNN | main | 1.1.2 | `speechbrain==1.1.2` | Apache-2.0 | `speechbrain_ecapa_voxceleb` (89 MB) | PASS: same voice 0.81 vs different 0.10 (TTS) | **go (primary)**. Needs `LocalStrategy.COPY` (no symlink privilege on this account) |
| 30 | Voices fallback (voices) | WeSpeaker ResNet34-LM ONNX | main | HF rev `f0c48c29` | `onnxruntime==1.31.1` | CC-BY-4.0 | `wespeaker_resnet34_lm_onnx` (27 MB) | PASS: same 0.84 vs different 0.23; 16 windows of the rap clip embedded (mean pairwise cos 0.22) | go (fallback; torch-free apart from kaldi fbank) |
| 31 | Visemes (lipsync) | Rhubarb Lip Sync | external | 1.14.0 | none; zip sha256 `62fa416a...` (trust on first use, no published digest) | MIT | `rhubarb_lip_sync` (87 MB zip) | PASS on TTS (26 cues, A-H + X) and on a separated sung vocal | **go** (Should) |
| 32 | In-house g2p (lipsync, Could) | g2p-en (+ nltk) | main | 2.1.0 / 3.10.4 | `g2p-en==2.1.0` | Apache-2.0 | `nltk_g2p_data` (NLTK_DATA) | PASS (needs NLTK data: it downloads at import, so it is pre-seeded and pinned) | go (Could) |
| 33 | LRCLIB, MusicBrainz, AcoustID (lyrics, identity) | httpx | main | 0.28.1 | `httpx==0.28.1` | BSD-3 | none | reachability only (lrclib 200, musicbrainz 200, acoustid 404 on bare root); recorded HTTP belongs to the real-song cache agents | go |
| 34 | Hub plumbing | huggingface-hub | main | 2.4.0 | `huggingface-hub==2.4.0` | Apache-2.0 | HF-cache layout hard-linked for allin1 and demucs-onnx | PASS offline | go |
| 35 | Schemas (contract, validate) | jsonschema | main | 4.26.0 | `jsonschema==4.26.0` | MIT | none | PASS (Draft 2020-12) | go |
| 36 | MIDI (notes; synthetic fixtures) | mido; pretty-midi | main | 1.3.3; 0.2.11.post0 | `mido==1.3.3`, `pretty-midi==0.2.11.post0` | MIT | none | PASS (write + read back) | go |
| 37 | Meaning draft (optional) | anthropic | extra `anthropic` | 2.6.0 | `anthropic==2.6.0` (extra) | Apache-2.0 | none | import PASS (no call made; the builder must read the `claude-api` skill before writing that code) | go (optional) |
| 38 | Tests (7) | pytest, pytest-timeout, ruff | dev | 9.2.0, 2.4.0, 0.17.4 | dev group | MIT | none | PASS (`ruff` with preview rule PLW1514 for `open()` encodings) | go |
| 39 | Synthetic vocal (7) | Windows SAPI TTS (David, Zira) | external | Win11 | none | OS | none | PASS: PowerShell `System.Speech` writes WAV, converted with ffmpeg to float32 | go; `scripts/smoke/make_clips.ps1` is the recipe |
| 40 | JS parity (7, lib) | node | external | 26.13.0 | none | MIT | none | PASS (ESM import works) | go |
| 41 | Torch + CT2 + ORT in one process (3.3) | torch 2.15 CPU, ctranslate2, onnxruntime, numba, scipy-openblas | main | | | | | **PASS, no clash**: see section 4 | go |
| 42 | Process hygiene | torchcodec (absent) / torchaudio.load | main | | | | | `torchaudio.load` fails as documented ("TorchCodec is required"): never call it | rule stays |

## 4. Process-level results

* **OpenMP coexistence: no clash.** One process imported torch, onnxruntime, ctranslate2 (real faster-whisper large-v3 int8 transcription),
  numba (parallel `prange`), scipy and librosa and ran real work in each. Loaded runtimes: `libiomp5md.dll`, `libiompstubs5md.dll`,
  `vcomp140.dll`, plus two scipy-openblas DLLs. Only one Intel OpenMP copy is loaded (the error "OMP: Error #15" needs two), so
  `KMP_DUPLICATE_LIB_OK` is **not** needed and must not be set. Thread caps (`OMP_NUM_THREADS` etc. plus `torch.set_num_threads`,
  ORT `intra_op_num_threads`, ct2 `cpu_threads`) were exercised at 3 threads.
* **onnxruntime providers**: `CPUExecutionProvider` and `AzureExecutionProvider` only (no DirectML). `onnxruntime-directml`, `tensorflow` and `skey` are absent.
* **Symlinks**: this account has no symlink privilege (`WinError 1314`); libraries that symlink need a copy strategy (SpeechBrain does). HF cache layout was built with hard links.
* **Sizes**: `.venv` 1.3 GB; models 5.85 GB pinned by this agent (`%LOCALAPPDATA%\mvh\models` also holds env-sep's files).

## 5. Deviations from the plan

1. **Vendored wheels come from PyPI, not commit tarballs.** `all-in-one-infer` 3.1.0, `madmom-infer` 0.2.0, `demucs-infer` 4.4.0 are still on PyPI (the plan assumed they were not).
   Building the downloaded GitHub tarballs was refused by the permission classifier ("code from external"), so the pinned-commit route was not completed. The
   wheels were downloaded, sha256-verified against PyPI's digests and stored in `vendor/wheels/`; `[tool.uv.sources]` points `path` at them, so uv never needs
   PyPI for these three. For the orchestrator, should the commit route still be wanted: the upstream-tested commits are `all-in-one-infer` 566f96c3f007c783ab5eb6db0123bf3335af8f31
   (its `pyproject.toml` has two `git+https` dependencies that must be rewritten to plain names), `madmom-infer` a9ed04ec942dd6ec5309df7ce7f3783d1bb42575 (0.3.0) and
   `demucs-infer` ffe0080ef96336a34e3f0ee8ba22ceaa0623a36c; tarballs are cached (untouched, not built) in `%LOCALAPPDATA%\mvh\dl`. HEAD of `madmom-infer` is a different, newer
   revision (bffead9b), so the PyPI 0.2.0 wheel is the combination the survey locked and tested.
2. **CLAP model**: Xenova has no `larger_clap_music` ONNX; `Xenova/larger_clap_music_and_speech` (the survey's choice) is used.
3. **S-KEY**: pinned HF revision of the community export (`musetric/skey-onnx` @ `9d90d2a9...`) instead of exporting from Deezer's checkpoint. Licence caveat recorded in the lock.
4. **Heavy-lock names**: implemented as given in this task (`heavy-0.lock`, `heavy-1.lock`, `gpu.lock`, with `heavy_lock.py`); PLAN 12 still says `heavy.lock`.
5. **uv environments**: `[tool.uv] environments = ["sys_platform == 'win32'"]` is required; without it `basic-pitch`'s `tensorflow-macos` pin makes the universal lock unsolvable.
   The plan's override list was extended with `onnxruntime==1.31.1` (CPU only). `docs/research/locks/sources-overrides.txt` was not used.
6. **Extra dependencies** that the plan did not list: `audioread` (imported by `piano_transcription_inference`), `scikit-learn` and `pillow` (palette), `huggingface-hub` (explicit),
   `transformers` + `tokenizers` (CLAP feature extractor and tokenizer only), `speechbrain` (ECAPA), `g2p-en` (+ `nltk`). `numpy>=2.5,<2.6`, `scipy>=1.18,<1.19`, `librosa>=1.0,<1.1` are ranges (exact pins in `uv.lock`).
7. **Package-install mode**: `mvh` is installed editable by `uv sync` (hatchling, `src/mvh`); `PYTHONPATH=<repo>\src` is also set by `mvh-env`, so imports work before and after any re-sync.
8. **Ruff** `PLW1514` (encoding on `open()`) is a preview rule: `preview = true` with `explicit-preview-rules = true`; scripts/ ignore style rules only.
9. **Rhubarb** has no published digest; the SHA-256 is trust-on-first-use. Unzipped to `bin\rhubarb\Rhubarb-Lip-Sync-1.14.0-Windows\rhubarb.exe` (`MVH_RHUBARB`, `config.json` key `rhubarb`).
10. **config.json** is written without a BOM (PowerShell 5.1 `Set-Content -Encoding UTF8` adds one and breaks a plain `json.load`); readers should still open it with `utf-8-sig`.
11. **demucs-onnx**: its public `separate()` takes a path (libsndfile); the verified route calls the private chunked function with our own ORT session. fp16-weight files only (the library documents max abs diff vs fp32 of about 6e-5); fp32 not fetched.

## 6. Open points and things the benchmark / builder agents must know

* `allin1_infer` needs 4 stem **files** (float32 WAV that we write). The cost is small; a `stem_provider` hook exists if an in-memory route is wanted later.
* Whisper on a sung 5 s clip with VAD gave no words, as expected; real-song transcription behaviour is for the lyrics benchmark.
* `lv-chordia` and `basic-pitch` read from a path (our float32 WAV); both worked, and neither touches the user's original file.
* NLTK data (`averaged_perceptron_tagger`, `_eng`, `cmudict`) lives in `NLTK_DATA`; without that variable `g2p-en` tries the network at import.
* Python scripts run from a scratch directory must not shadow stdlib names (see Commands).
* Not covered here (owned by env-sep): audio-separator and its ROCm/CPU torch, the Vulkan whisper benchmark, ggml/silero models, ROCm.
* Not benchmarked here: throughput on full-length songs (benchmark agents do that under the heavy lock). Observed on 5 s clips at 3 threads: demucs 1.3 s, allin1 1.6 s, beat_this 0.23 s, faster-whisper load 3.3 s.
