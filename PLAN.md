# mv-harness — build plan

Status: **v1 plan, reviewed (round 1)** · 2026-11-08 · research in [docs/research/](docs/research/) · review dispositions in
[docs/REVIEW-LOG.md](docs/REVIEW-LOG.md)

> **Amended by [docs/SPIKE.md](docs/SPIKE.md) (W0 gate) and [docs/CONTRACT.md](docs/CONTRACT.md) decisions D1–D28 (W1a).**
> Where either disagrees with this plan (env pins, tool recipes, thresholds, file and field names), they win.

mv-harness turns one song into a complete, timestamped description of what is in it: rhythm, sound, instruments, notes,
voice, words and meaning. One or more AI agents then use that description to build a music video that responds to the music, in
any technology they choose (WebGL, Remotion, Blender, ComfyUI, ffmpeg and so on). **It does not make videos.** It is the shared
ground truth that every video agent reads from.

---

## 1. Goals and decisions

### Goals
1. **Rich, trustworthy song metadata.** Everything time-based is in seconds on one clock. Every estimate carries a confidence and its provenance.
2. **Agent-friendly.** A small manifest and a `brief.md` of at most 4k tokens give an LLM the whole song, and `mvh brief --section` zooms in on one section.
   The dense data lives in compact binary and JSON files and is read through small JS and Python loaders, so it never has to be pasted into an agent's context.
3. **Technology-neutral.** Only JSON, raw little-endian float32/uint8, CSV/TSV, MIDI, LRC/WebVTT/ASS and FLAC/WAV.
4. **Human-verifiable and correctable.** A viewer shows every lane in sync with the audio and lets the user fix beats, sections, lyric timing and singers.
   The corrections flow back into the analysis.
5. **Built for art pieces.** Choreography, characters, lip-sync and the user's meaning are first-class outputs.

### Decisions already made (user, 2026-11-08)
| Topic | Decision | Consequence |
|---|---|---|
| Purpose | Personal art-piece music videos, **one track at a time**; quality over speed | The default profile is `max`: the best models, ensembles and cross-checks. There is no runtime budget; timings are reported. |
| Licences | Personal use; **non-commercial (CC-BY-NC) models are allowed** as defaults | Every model's licence is recorded in `run.json` and in each provenance block. |
| True meaning | **Authored by the user** | The harness interviews the user. A draft from an agent or LLM fills only the gaps, is labelled as a draft, and never overwrites the user (§8). |
| GPU | CPU baseline plus a **best-effort** ROCm profile (RX 9070, gfx1201). **If ROCm does not work out of the box, everything stays on CPU** | The heavy separators run in a worker env with ROCm and CPU variants (§3.1). W0 tries ROCm once, within a time box, and does no extended troubleshooting. |
| Test songs | `viz/MEGAFAUNA.flac`, `viz/Versatile.flac` (electronic, near-instrumental, not on LRCLIB), `songs/Jeremy (Redux Version).flac` (Pearl Jam, grunge, 5:17), `songs/Sir Isaac Newton vs Bill Nye.flac` (Epic Rap Battles of History, three rappers, 2:50) | Jeremy tests distorted guitars, a wide baritone range, a prominent bass line and a long outro with no lyrics. The rap battle tests dense rap alignment and **attributing lines to three different voices**. Both have synced lyrics on LRCLIB (checked 2026-11-08). |
| Platform | Native Windows 11. **WSL is used only for git** (the orchestrator commits through it) | Python 3.12.10, uv 0.13.7 and ffmpeg 9.0.2 (Gyan full build, with whisper, Vulkan and chromaprint) are installed natively but **not on agents' PATH**. Always use absolute paths via `scripts/mvh-env.ps1` (§3.4). |

### Non-goals (v1)
- Rendering video.
- Batch processing of albums or DJ mixes.
- Commercially licence-clean output.
- An MCP server (phase 2).
- Real-time analysis (`viz/` already does that, and `vizState()` lets its scenes run from offline data).

---

## 2. Requirements

**Must** = v1. **Should** = v1 unless the W0 spike shows it is not feasible. **Could** = stretch goal.

| ID | Requirement | Priority |
|---|---|---|
| R1 | **Tempo & beats**: global BPM with alternatives (×2, ×½, 4:3, 3:2) and a feel label; a tempo curve; beat times refined below one frame; downbeats, bars, meter and meter changes; pulse regions (where a beat is actually present); confidence and QA flags | Must |
| R2 | **Structure**: sections with functional labels and their probabilities; repetition groups; 4/8/16-bar phrases; EDM roles (build, drop, breakdown) as a separate field, with one canonical definition (§5 structure) | Must |
| R3 | **Spectral bands**: the viz band rule (bass 32–150 Hz, mid 150–2200 Hz, high 2.2–16 kHz), 7 finer bands, a 128-band log spectrum, the viz kick envelope, mid and high hit envelopes, and per-band onsets; every band also as absolute dB | Must |
| R4 | **Loud & quiet parts**: momentary and short-term LUFS, integrated loudness, LRA, true peak, RMS and crest; dynamics segments (silence, quiet, soft, medium, loud, peak); impact, stop and silence events; an intensity curve | Must |
| R5 | **Stems**: vocals, **lead_vocals** (always present, see §5), backing_vocals, drums, bass, guitar, piano, other, instrumental; drum sub-stems (kick, snare, toms, hihat, ride, crash); per-stem activity | Must (drum sub-stems: Should) |
| R6 | **Instruments**: a timeline (1 Hz curves plus segments) built by fusing the stems with an audio tagger; an open-vocabulary pass for synth sub-types and the user's own terms; a summary | Must |
| R7 | **Notes**: note events per pitched stem (bass, piano, guitar, other, vocals) as JSON and MIDI (with a tempo map); note density and range per stem | Must |
| R8 | **Drum hits**: classified hits (kick, snare, hat, tom, cymbal, perc) with velocity, plus 100 Hz envelopes | Must |
| R9 | **Vocal range**: lead-vocal f0 (NaN where unvoiced), `pitch01` relative to the singer's own range, a voiced flag, the lowest and highest sustained notes with times, the p2–p98 range, the p10–p90 tessitura, register, phrases, vocal notes, and style (singing, speech, rap) | Must |
| R10 | **Harmony**: chroma, global key and key changes (with ensemble confidence), and a chord timeline snapped to beats | Must |
| R11 | **Lyrics**: sources tried in order: user file, embedded tags, LRCLIB, transcription. **Word timing** from forced alignment on lead_vocals. Per-word and per-line confidence, an A–D grade per song, repeat groups, `lines.tsv` (safe to put in an agent's context), and exports (LRC with word tags, VTT, SRT, ASS karaoke) | Must |
| R12 | **Identity**: tags; chromaprint, AcoustID and MusicBrainz when tags are missing; credits; cover art and palette | Must (AcoustID: Should, because it needs a free key) |
| R13 | **Mood**: audio valence and arousal curves and mood/theme tags, aggregated per section | Must |
| R14 | **True meaning**: user intent first; an agent or LLM draft only for gaps. Logline, themes, narrative and perspective, characters, setting, motifs and where they occur, symbolism, a per-section meaning with feel, palette, movement and camera hints, and do-not rules. Every claim is typed and cited. Authored files are never overwritten | Must |
| R15 | **Choreography data**: eight-counts anchored to phrases (six-counts in 3/4) with accents and sub-counts (1 & e a); per-bar 16-step groove matrices with swing, syncopation and groove IDs; hit points; holds; a movement-density curve | Must |
| R16 | **Characters & lip-sync**: a 100 Hz `vocal.mouth_open` channel **per voice** (the vocal envelope gated by that voice's aligned words); **automatic voice identification**, where speaker embeddings per line are clustered into voices `V1…Vn` and propose a singer for every line, and the user maps voices to characters; a `singer` (character ID) on every lyric line; `events/singing.json` joining lines, voices, characters and lead/backing. Rhubarb visemes are Should; in-house g2p visemes are Could | Must (visemes: Should) |
| R17 | **Cue sheet & moments**: one tiered cue list (§5 cues) with lead-in times and source references; the top moments | Must |
| R18 | **Viewing**: a viewer with synchronised lanes for meaning, lyrics and singers, beats and counts, hits, bands, loudness, instruments, a notes piano roll, vocal range, chords and key, cues | Must |
| R19 | **Corrections**: viewer edits are saved to `overrides.json`; only the affected stages re-run; authored meaning is re-anchored to the edited sections | Must (the override round trip is a W3 acceptance test) |
| R20 | **Agent integration**: the `mvh` CLI, the Agent Skill, JS/Python loaders with the same semantics, a GLSL sampler, `mvh frames`, and `mvh brief --section` | Must |

Non-functional requirements:
- **NF1 Determinism.** With the same env lock, device class and thread counts, a re-run is byte-identical for `manifest.json`, the events and the
  curves. Volatile data (timings, host, device details) goes only to `run.json`. Stages that ran on the GPU record the device in provenance and are compared with a tolerance.
- **NF2 Caching.** Stage key = sha256 of all of the following:
  - the stage version and params (including fixed thread counts) and the model SHA-256s;
  - the upstream keys and the subset of overrides the stage reads;
  - **content hashes of every external file the stage reads** (lyrics file, intent.md, authored meaning.json, vocabulary) and hashes of the cached network responses it used;
  - the ffmpeg version and buildconf (for ingest, loudness, identity and lyrics), the env lock hash, and the device class for stages that can use the GPU.
- **NF3 Robustness.** Only ffmpeg decodes audio (Versatile.flac has a corrupt frame that libsndfile rejects). Non-ASCII paths and paths with spaces must work
  (Windows rules in §3.4). Lossy inputs get a lossless reference decode that becomes the timebase.
- **NF4 Offline-capable.** The network is used only by `mvh models fetch`, identity, LRCLIB and the optional LLM call. Every response is cached, and
  `--no-network` and `HF_HUB_OFFLINE` are honoured.
- **NF5 Lyrics and copyright.** Lyrics stay in the local output folder. They never appear in logs, reports, `run.json`, or `brief.md` beyond quotes of
  at most 10 words. The user's own agent sessions (the meaning drafter and the video agents) may read `lines.tsv` and `lyrics.json`; `--no-lyrics-to-agents`
  turns that off. The `--meaning-draft anthropic` call sends lyrics to the API only when the user enables it.

---

## 3. Architecture

### 3.1 Environments
| Env | Contents | Used for |
|---|---|---|
| **main** (`pyproject.toml`, `uv.lock`, Python 3.12) | numpy 2.5, scipy 1.18, librosa 1.0.x, pyloudnorm, soundfile (our own WAVs only), soxr; torch 2.15 CPU and torchaudio 2.11.1 (PyPI); onnxruntime 1.31.1 (CPU); beat-this 1.1.0; all-in-one-infer + madmom-infer + demucs-infer (from **pinned commit tarballs** over HTTPS, built into `vendor/wheels/`; PyPI 3.1.0 as fallback); demucs-onnx 0.3.4; basic-pitch 0.4.0; swift-f0; rmvpe-onnx; piano_transcription_inference + torchlibrosa; CED and CLAP ONNX runtimes; lv-chordia 1.1.0; faster-whisper 1.2.1 / ctranslate2 4.8.5; stable-ts 2.19.1; uroman; num2words; rapidfuzz; httpx; mido / pretty-midi; jsonschema; a g2p package (Could); pytest, pytest-timeout and mir_eval (dev); anthropic (optional extra) | Every stage except the high-quality separators |
| **sep** worker (`envs/sep/`, two locks: `rocm` and `cpu`) | audio-separator 0.48 (BS-RoFormer-SW 6-stem, Mel-RoFormer vocals, karaoke lead/backing, MDX23C DrumSep). `rocm`: AMD torch for gfx120X (the spike picks 2.11.0+rocm7.13 preview or 2.9.1+rocm7.2.1 stable). `cpu`: torch 2.15 CPU from PyPI | `separate_hq`. The order of attempts is the rocm variant, then the cpu variant (same models, slower), then htdemucs equivalents flagged `degraded` |
| **external** | ffmpeg / ffprobe 9.0.2 (decode, `ebur128`, `-f chromaprint`, `whisper` on Vulkan); Rhubarb Lip Sync CLI (pinned release + SHA-256, Should) | ingest, loudness, identity, lyrics fallback, lipsync |

Known install traps:
- **basic-pitch** needs the overrides `tensorflow; sys_platform=="never"` and `resampy>=0.4.3`. **Do not copy** `docs/research/locks/sources-overrides.txt`
  as is: it is the DirectML variant and removes `onnxruntime`. v1 uses only the CPU build, pinned at `onnxruntime==1.31.1`, and `onnxruntime-directml` is never installed.
- **Never hand a file path to a model library.** Pass numpy arrays or tensors at the model's sample rate (beat_this `Audio2Frames`, demucs-onnx,
  basic-pitch, faster-whisper, stable-ts), or a float32 WAV that we wrote ourselves (lv-chordia, audio-separator). Never call `torchaudio.load`
  or `torchaudio.save`: they go through torchcodec, which needs shared FFmpeg DLLs, and the Gyan build is static. PyAV 19 breaks faster-whisper's own decoder.
- **Forced alignment:** `torchaudio.functional.forced_align` is a compiled op. Use it when `torchaudio._extension._IS_ALIGN_AVAILABLE`; otherwise use the
  vendored `stages/lyrics/ctc_viterbi.py` (golden-tested against torchaudio).
- **Rejected after research:** madmom (official), essentia, BeatNet, MSAF, WhisperX, torch-directml and `skey` on PyPI (an unrelated package). The survey has the details.
- **ROCm is best-effort.** As of 2026-11-08, Smart App Control is already off on this machine (`VerifiedAndReputablePolicyState=0`) and the driver is recent
  (32.0.32015.7029, dated 2026-10-18). W0 installs the AMD wheels and runs one smoke test, within a time box. If either fails, ROCm is dropped and `separate_hq`
  uses the sep-cpu variant. Agents never change drivers or security settings.
- **audio-separator is always configured** with:
  - `normalization_threshold=100.0` and `amplification_threshold=0.0`, so the mix and the stems are not re-levelled (Versatile measures +4.1 dBTP);
  - `model_file_dir` set to the shared cache;
  - float WAV output.

  Invariant test: the stems sum to the mix within −30 dB, and each stem's gain relative to the mix is 1.0 within 0.1 dB.

### 3.2 Stages
Each stage is a package `src/mvh/stages/<name>/` that declares `STAGE = StageSpec(name, deps, env, version, override_keys, outputs)`.
The runner builds the DAG from these declarations (an acyclicity test is included). A stage may read only the artifacts of the stages it declares.

| Stage | Env | Consumes | Produces (main) |
|---|---|---|---|
| ingest | main | input file | canonical float32 WAV (hashed) in `.cache/ingest`, `audio/mix.flac` (24-bit export; `mix.wav` float when \|x\|>1), `preview.opus`, cover, palette |
| identity | main | ingest | identity, credits (cached network responses) |
| separate_fast | main | ingest | htdemucs 4-stem (demucs-onnx); htdemucs_6s in `draft` |
| separate_hq | sep | ingest | 6 stems, vocals, lead/backing vocals, drum sub-stems, instrumental (from un-normalised stems) |
| allin1 | main | separate_fast | intermediate: beats and downbeats, segments, label_probs and boundary activations at 100 Hz, embeddings |
| spectral | main | ingest | bands, spectrum128, hit envelopes, onsets, timbre, stereo |
| loudness | main | ingest | LUFS curves, integrated loudness, LRA, true peak, RMS, crest |
| rhythm | main | ingest, allin1, spectral | tempo and alternatives, tempo curve, beats, downbeats, bars, meter, pulse regions, QA |
| harmony | main | ingest, rhythm | chroma12, key and key changes, chords snapped to beats |
| dynamics | main | loudness, spectral, rhythm | dynamics segments, impacts, stops, silences, intensity |
| structure | main | allin1, rhythm, harmony, dynamics | sections (canonical), repetition, phrases, EDM roles (drops and builds, defined here) |
| stem_activity | main | ingest, separate_fast, separate_hq | per-stem RMS and activity curves and segments |
| drums | main | separate_hq, stem_activity | drum hits and envelopes |
| instruments | main | ingest, separate_*, stem_activity | instrument curves, segments, summary, vocal style |
| notes | main | separate_hq, stem_activity, rhythm | notes JSON and MIDI per source |
| vocals | main | separate_hq, stem_activity, instruments, rhythm | f0, pitch01, voiced, range, phrases, vocal notes |
| mood | main | ingest, structure | valence/arousal curves, mood tags per section |
| lyrics | main | identity, separate_hq, stem_activity, structure | lyrics.json, lines.tsv, exports |
| voices | main | lyrics, separate_hq, stem_activity | voice clusters `V1…`, a proposed voice per line and word span with confidence, per-voice activity segments |
| lipsync | main + Rhubarb | lyrics, voices, separate_hq | `vocal.mouth_open.<voice>`, phonemes and visemes tagged with the voice |
| choreo | main | rhythm, structure, drums, spectral, vocals, harmony, dynamics | counts, grooves, hit points, holds, movement density |
| cues | main | choreo, structure, dynamics, rhythm, drums | tiered cues.json, moments |
| meaning | main | identity, lyrics, voices, structure, mood, vocals, instruments, cues, **intent.md**, **authored meaning.json** | interview.md, request bundle, merged meaning.json, singing.json, orphans.json |
| brief / viewer | main | all | brief.md, viewer.html |
| frames | main | on demand | `frames/<fps>fps.csv` |

### 3.3 Runner
- **Process model.** Each stage runs in its own spawned process. Thread counts are set before anything is imported: `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`
  and `NUMBA_NUM_THREADS` = n. Inside the stage, mvh patches the default onnxruntime `SessionOptions` (intra = n, inter = 1) before wrappers are imported, and sets
  ctranslate2 `cpu_threads=n`, `torch.set_num_threads(n)` and `set_num_interop_threads(1)`. The scheduler shares 8 physical cores across the stages that are running,
  and n is part of the cache key. W0 checks that torch, ctranslate2 and onnxruntime can be imported into one process without an OpenMP runtime clash.
- **Worker protocol.** For `env="sep"` the runner launches `envs/sep/.venv-<variant>/Scripts/python.exe -X utf8 -m mvh.worker <stage> job.json`.
  - mvh's core (`mvh/__init__`, `worker.py`, `contract/`) imports only the stdlib and numpy. The worker env installs mvh with `--no-deps`, or `PYTHONPATH=<repo>/src` is set.
  - `envs/sep` is not a uv workspace member. Its rocm lock declares `[[tool.uv.index]] name="amd" url="https://repo.amd.com/rocm/whl/gfx120X-all/" explicit=true`,
    with only the torch and ROCm SDK packages sourced from that index.
  - The worker only runs inference: it reads float32 WAVs listed in job.json and writes float32 WAVs and `result.json` to scratch. The parent does the FLAC encoding,
    validation, provenance and caching. Workers and ffmpeg run in a Job Object with KILL_ON_JOB_CLOSE.
- **Cache.** `out/<slug>/.cache/<stage>/<key>/`, keyed as in NF2. `mvh status` reports each stage as done, stale or pending, with the reason. Writes are atomic: a temp file, then `os.replace`,
  retried with backoff on `PermissionError` (Defender and indexer locks).
- **Models.** `mvh models fetch` is **the only downloader**. Each entry in the single root `models.lock.json` is `{id, envs[], files[{path, url, revision, sha256, size}], licence, used_by[]}`.
  - The runner sets `TORCH_HOME`, `HF_HOME`, `AUDIO_SEPARATOR_MODEL_DIR`, `NUMBA_CACHE_DIR` and `NLTK_DATA` under `%LOCALAPPDATA%\mvh\`, and during analysis also `HF_HUB_OFFLINE=1`.
  - Libraries get explicit checkpoint paths: beat_this, allin1 folds, MMS_FA, madmom-infer weights, piano transcription, the ggml whisper and Silero models, Essentia ONNX, S-KEY, CED, CLAP and the separator models.
  - Downloads go to a temp file, are verified, then moved into place with `os.replace` under a per-file lock. `doctor` verifies every SHA-256 offline.
- **Overrides.** `overrides.json` (written by the viewer or by hand) feeds into the keys of the stages that declare those override keys. Each stage applies them at a defined
  point (for example rhythm applies them after tracking and before fusion) and records every applied override in provenance.
- **Authored inputs.** `meaning/intent.md` and any `meaning.json` written by an agent or LLM are **inputs, not cache outputs**. `mvh analyze` never deletes or overwrites them (§8).
- **`mvh doctor`** reports:
  - which ffmpeg it resolved and its buildconf flags (whisper, vulkan, chromaprint);
  - the envs and whether their locks are in sync;
  - ROCm health (`torch.cuda.is_available()` on HIP in the sep-rocm env);
  - Vulkan whisper and Rhubarb;
  - the models' SHA-256 values;
  - free disk space.

### 3.4 Windows rules
- **Tools.** Never rely on PATH. `scripts/mvh-env.ps1` (and a `.cmd` twin) puts Python 3.12, uv and ffmpeg on PATH **by absolute path** and sets `MVH_FFMPEG`, the
  thread variables, the cache directories and the offline flags. `io/ffmpeg.py` resolves ffmpeg in this order: `MVH_FFMPEG`, then `%LOCALAPPDATA%\mvh\config.json`, then PATH. The runner puts that
  bin directory first on PATH for every child, so ffmpeg spawned by a library (pydub and others) is the same 9.0.2 build.
- **Encoding.**
  - Every Python child runs with `-X utf8` and `PYTHONUTF8=1`. The CLI reconfigures stdout to UTF-8. Every `open()` passes `encoding="utf-8"` (enforced by ruff).
  - JSON is written with `ensure_ascii=False`. ffmpeg subprocess calls use `encoding="utf-8", errors="replace"`.
  - The lyrics reader detects a BOM or UTF-16 and falls back to cp1252 with a warning.
- **Paths.** Use pathlib everywhere and never build shell strings. The ffmpeg whisper filter runs with `cwd` set to the model folder and uses relative names (no drive-letter
  colons in the filtergraph). Long paths are already enabled (`LongPathsEnabled=1`).
- **Servers.** `mvh view` binds 127.0.0.1 on port 0 with an idle timeout.
- **Files.** `.gitattributes` sets `* text=auto eol=lf` and `binary` for `*.f32 *.u8 *.flac *.wav *.opus *.mid`, and contract writers use `newline="\n"`.
- **Defender.** Excluding `%LOCALAPPDATA%\mvh` and `out/` speeds up I/O. This is an optional **manual step for the user**; agents never change it.

---

## 4. Output contract (v1)

### 4.1 Layout
Everything for a song goes into one self-contained folder `out/<slug>/`:
```
manifest.json      index only: schema_version, source, timebase, status, summary scalars, files[]; no arrays; ≤ 3k tokens
brief.md           the LLM entry point; ≤ 4k tokens (target 2.5k); `mvh brief --section S05` gives ≤ 1.5k-token zooms
viewer.html        `mvh view` (local server, edit mode) or file:// (read-only, preview data inlined)
run.json           volatile: timings, host, device, versions, licences, fallbacks used
overrides.json     user corrections
audio/mix.flac     **every time refers to this file**; preview.opus for the viewer
stems/*.flac       sample-aligned with mix and the same length (24-bit; float WAV if |x|>1): vocals, lead_vocals, backing_vocals,
                   drums, bass, guitar, piano, other, instrumental, drums/{kick,snare,toms,hihat,ride,crash}
curves/index.json  registry: id, unit, range, norm {method, lo, hi}, resample policy, special values, description, file, byte offset
curves/core.f32    100 Hz, float32 LE, **column-major** (one contiguous block per channel → `new Float32Array(buf, off, n)`)
curves/spectrum128.u8   [frames x 128] row-major, quantised dB (scale and offset in the registry)
curves/{chroma12,stems,vocal}.f32, curves/{instruments,mood}_1hz.f32
events/*.json      envelope {schema, name, kind: event|segment, fields{unit}, provenance, items:[{id?, t, d?, ...}]}
tables/{beats,bars,sections}.csv   derived from the canonical events, carrying the same IDs
notes/notes.mid (one track per source; tempo map from the beat grid), notes/<src>.mid, notes/notes.json
lyrics/lyrics.json (canonical), lines.tsv (id, t, d, section_id, singer, repeat_group, grade, text), .lrc (A2), .vtt, .srt, .ass
lipsync/visemes.json, phonemes.json
meaning/interview.md, intent.md (user), request.md, input.json, schema.json, meaning.json, meaning.md, orphans.json
artwork/cover.jpg (palette in the manifest)
frames/<fps>fps.csv   on demand
lib/mvh.js, lib/mvh_load.py, lib/mvh.glsl, schema/*.schema.json   copied in, so the folder works without mvh installed
```
`docs/CONTRACT.md` (generated into `skill/.../references/CONTRACT.md`) lists every file and events name with its kind, fields, units and producing stage, plus a
**Consumed-by matrix** (stage → files and fields it reads).

### 4.2 Time and frames
- Times are in seconds from the first sample of `audio/mix.flac`. Video agents use `mix.flac` or the stems as the soundtrack, **never the original file**.
- Curve frame *i* is centred at *i*/100 s.
- Video frame *n* at *F* fps stands for *t_n* = (*n* − frame0)/*F*, with the **centred** window [*t_n* − ½*F*⁻¹, *t_n* + ½*F*⁻¹).
- `linear` and `hold` sample at *t_n*. `mean` and `max` aggregate over the window. An event belongs to the frame whose window contains it, so a curve flash and its event always land on the **same** frame.
- The `early` option shifts all three rules together to [*t_n*, *t_n* + *F*⁻¹).
- Frame helpers take `{fps, frame0 = 0, early = false}`. `fps` may be a rational number such as `[24000, 1001]`. Blender uses `frame0 = 1`.

### 4.3 IDs and links
| Entity | ID | Required links and fields |
|---|---|---|
| Section | `S01…` | label, occurrence (e.g. chorus#2), repeat_group; **canonical in `events/sections.json`** |
| Phrase | `P01…` | start_bar, n_bars, section_id |
| Bar / beat | bar is 1-based; beat_in_bar is 1..N; beat_index is 0-based | bars carry section_id, phrase_id, groove_id |
| Eight-count | `E001…` | phrase_id, len (8, or 4/6 if partial) |
| Groove | `G01…` | per-bar pattern cluster |
| Lyric line | `L001…` in sung order | section_id, **singer** (character ID), voice, text_group (identical text), repeat_group |
| Word | `L001.03` | line_id, conf |
| Voice | `V1…` | a cluster of one singing or rapping voice; character_id (mapped by the user, proposed by the harness) |
| Character | `C1…` | from intent.md or meaning; voice_ids; lead/backing; lines |
| Motif | `M1…` | occurrences (line IDs and times) |
| Cue | `Q0001…` | tier, source `{file, id}` |

### 4.4 Values
- **Absolute twins.** Every 0..1 curve derived from a physical quantity has an absolute twin (dB, LUFS, Hz or MIDI). Its normalisation is per song (p02–p99.5), and the parameters are recorded in the registry.
  Composites (intensity, movement density, accents, hit envelopes, mood) are documented as unitless.
- **Resample policy.** Each curve has one: `max` for hit envelopes and flux (no hit falls between 24 fps frames), `mean` for levels and spectra, `linear` for smooth controls, and `hold` for steps.
- **Unvoiced f0.** In the files, `vocal.f0_hz` and `vocal.midi` are **NaN where unvoiced**. Pitch channels resample only within voiced spans. The helpers and the frames export
  never return NaN: `vocalAt` holds the last voiced value. `vocal.pitch01` = (midi − p2)/(p98 − p2), held through gaps with a 150 ms ease. `vocal.voiced` is 0 or 1 with policy `max`.
- **Off-grid rhythm.** In no-pulse regions, the beat and count helpers continue on a virtual grid at the neighbouring tempo and return `in_pulse: false`.

### 4.5 Helpers (`lib/mvh.js` ES module with no dependencies, `lib/mvh_load.py` with numpy only)

The two implementations behave identically: Python uses snake_case, mapped 1:1 from the JS names. Every helper is a pure function of t or of the frame number, and shared golden vectors cover every row.

| JS | Returns |
|---|---|
| `await load(base, {fetch?, include?})` · `loadSync(path)` (Node) · `await song.ensure(id)` | Song. `base` is a URL (browser) or a path (Node); anything not in `include` is loaded lazily; after loading, everything is synchronous (safe for Remotion) |
| `song.curve(id).at(t)` · `.frame(n, fr)` | number (never NaN) |
| `song.events(name).at(t)` | `{item, progress, t_in, t_left}` or null (for segments) |
| `.next(t, {minTier})` · `.prev(t)` · `.between(t0, t1)` · `.inFrame(n, fr)` | items |
| `frameOf(t, fr)` · `timeOf(n, fr)` · `frameCount(fr)` | frame conversions (`fr` = `{fps, frame0, early}`) |
| `pulse(src, t, {attack, decay, unit: 's'\|'beats', shape})` · `osc(t, {shape, periodBeats, phase})` | flash and beat-locked oscillators |
| `beatPos(t)` · `beatPhase(t)` · `barPhase(t)` | `{value, in_pulse}` |
| `count(t)` | `{eight_id, count 1..8, sub 0..3, phase, accent, partial, in_pulse}` |
| `lyricAt(t)` · `vocalAt(t)` · `singerAt(t)` | line, word and progress · `{voiced, midi, hz, conf, pitch01, phrase_id, note}` · `[{character_id, voice_id, lead_backing, line_id, mouth_open}]` |
| `meaningAt(t)` | `{section_id, meaning, feel, emotion, palette_hint, movement_hint, camera_hint, characters_present, do_not, provenance}` |
| `spectrumAt(t)` · `spectrumWindow(t, s)` | `Uint8Array(128)` (same layout as viz `bandBytes`) · a history matrix |
| `textureData(ids, {layout: 'wrap', width: 1024, format})` + `lib/mvh.glsl` `mvhCurve(sampler2D, t)` | engine-neutral texture data (whole-song curves wrapped into rows, so no MAX_TEXTURE_SIZE limit) and a GLSL sampler that interpolates manually for r32f |
| `vizState(t)` | the field names and shapes of `viz/js/audio.js` (bass, mid, high, level, kick, kickRaw, midHit, highHit, beat, beatPulse, onset, …, bandBytes), so the `viz/` scenes can run offline unchanged |

Notes, visemes and sections need no helpers of their own: use `events('notes.bass').at(t)`, `events('visemes').at(t)` and `events('sections').at(t)`.

### 4.6 Schemas
JSON Schema 2020-12 with semver. **Frozen after W1:** the envelope schemas (manifest, curves index, event-file envelope, provenance), the time and unit
conventions, the IDs, and every field listed in the Consumed-by matrix. Modules may add fields to their own outputs (a minor version bump, noted in their report).
`mvh validate` runs after every stage, and again after any authored `meaning.json`.

### 4.7 brief.md
1. A status line: meaning user, draft or pending; lyrics grade; stems and visemes present; low-confidence flags.
2. A header table: title, artist, duration, BPM and feel, meter, key, LUFS, LRA, vocal range, instrumentation.
3. Meaning: logline; a characters table (ID, description, voice, sections); the do-not rules verbatim (the user's words); palette.
4. The section cue sheet: section IDs, times in s and m:ss.s, bars, label, repeat group, energy and loudness class, instruments, vocal activity and range,
   notable hits, lyric line IDs, mood, feel and meaning. Repeats collapse into one row per repeat group when the brief would overflow.
5. Choreography: counts per section, the dominant grooves, the strongest hit points, holds.
6. The top 15 moments, with cue IDs.
7. A single line pointing to `SKILL.md` and `CONTRACT.md` for the loaders and the file catalogue.

Every number can be traced to a file.

---

## 5. Stage specs

Tool choices come from the survey ([docs/research/2026-11-08-tool-survey.json](docs/research/2026-11-08-tool-survey.json)).
Prototypes are in [docs/research/prototypes/](docs/research/prototypes/) and lock files in [docs/research/locks/](docs/research/locks/).

**ingest.** Decodes with ffmpeg: `-map 0:a:0` (which skips the cover-art stream), float32 at the native sample rate, decoder warnings captured. The canonical float32 WAV is hashed. From it, ingest exports
`mix.flac` and `preview.opus`, extracts the cover art and computes a k-means palette.

**identity.** Reads the ffprobe tags and normalises them. When tags are missing, or with `--verify-identity`, it fingerprints with ffmpeg chromaprint and looks the result up:
- AcoustID with the `ACOUSTID_API_KEY` env var, as a gzip POST, at most 3 req/s;
- MusicBrainz WS/2 at 1 req/s with an identifying User-Agent, accepting a match only with score ≥ 90 and length within ±3 s.

**separate_fast / separate_hq.** See §3.1–3.2.
- `separate_hq` models are pinned by revision and SHA-256.
- If the karaoke model is unavailable, `lead_vocals := vocals` and `lead_backing_split=false` is recorded, so `lead_vocals` exists in every profile.
- `instrumental` is the mix minus the un-normalised vocals.

**stem_activity.** RMS dBFS per stem at 100 Hz and the level relative to the mix. A stem is active above −45 dBFS and within 18 dB of the mix, with 300/500 ms hysteresis.
It also reports a `present` flag per stem.

**spectral.** An offline, non-causal port of `viz/js/audio.js`:
- an STFT compatible with the Web Audio API (Blackman window, |X|/N, centred frames, mid and side channels);
- 128 log bands with identical edges, the 2.6 dB/oct tilt and the soft knee, with a per-song gain in place of the AGC;
- power-domain dB for the viz, fine and kick bands;
- `_hitEnvelope` for kick, mid and high, with a centred ±8 s median reference, a relative gate `max(−46, p95 − 30 dB)`, raw and released curves, and events refined on a 2.5 ms zero-phase envelope;
- per-band flux onsets with a centred threshold;
- timbre and stereo features.

A parity test checks the band edges against a Node run of the viz band map.

**loudness.** Momentary and short-term LUFS curves from pyloudnorm K-weighting, centred (the offset from spec meters is documented); integrated loudness and LRA. ffmpeg `ebur128` serves as a cross-check
and gives the true peak, with a warning if the two differ by more than 0.5 LU. Also RMS, peak and crest curves.

**allin1.** all-in-one-infer `harmonix-all` (8 folds) on `separate_fast`, given arrays, not paths. Publishes schema'd intermediate files for rhythm and structure.

**rhythm.** Fuses beat_this `final0` (keeping its 50 fps logits; `infer_beat_numbers`), the allin1 beats and a librosa tempogram/PLP + ACF port, through these steps:
1. Tempo arbitration over the ratios 1, 2, ½, 3/2, 2/3, 4/3 and 3/4. MEGAFAUNA already disagrees: 105 vs 140 BPM.
2. Parabolic sub-frame refinement, then a snap to a transient within ±25 ms.
3. A piecewise tempo grid.
4. Meter, irregular bars and pickups, with a madmom-infer DBN fallback.
5. Pulse regions.
6. Agreement F-measures between the trackers, reported as confidence.

**harmony.** HPSS, then CQT chroma.
- Key: S-KEY ONNX (global and 30 s windows) plus a profile/chord-histogram ensemble with a sticky Viterbi; disagreements are flagged.
- Chords: lv-chordia (`weights_only`, local checkpoint), falling back to template + Viterbi, snapped to beats.

**dynamics.** Foote novelty on a 10 Hz multi-feature matrix (LUFS, band dB, kick rate, centroid, width, onset density). Boundaries snap to downbeats. Level classes are relative to the integrated loudness.
It also detects impacts, stops, silences and decay tails, and builds the intensity composite. Bass, kick density and spectral slope are used together with LUFS, because limited masters flatten it.

**structure.** Labels, probabilities and boundaries come from allin1. Boundaries snap to downbeats and segments shorter than 2 bars are merged. Repetition groups use chroma, MFCC and embeddings.
Phrases use the 4/8/16-bar offset that best matches the boundaries. **Drops and builds are defined only here**, as EDM-role segments snapped to downbeats; the dynamics detectors are their evidence.

**drums.** Hits come from the DrumSep sub-stems when they exist; otherwise from a classifier on the drum stem (viz kick logic, plus snare, hat/cymbal and tom detectors).
Outputs are velocities and 100 Hz envelopes, with the DrumSep path and the classifier path tested separately.

**instruments.** CED-base ONNX in 4 s windows with a 1 s hop, on the mix and on each stem, mapped to about 25 instruments. CLAP zero-shot covers synth sub-types and the user's vocabulary. The result is fused with stem activity,
and the evidence is recorded. Vocal style (singing, speech, rap) comes from CED on lead_vocals.

**notes.** basic-pitch ONNX per active stem, with presets. piano_transcription_inference runs on the piano stem when piano is present. Notes are masked by activity, and MIDI is written with a tempo map.

**vocals.** SwiftF0 on lead_vocals, with RMVPE arbitrating octave errors or low confidence. Range statistics use only gated frames. `present=false` when there are fewer than about 8 voiced seconds.
Outputs per §4.4: phrases, vocal notes and MIDI.

**mood.** Essentia models run as ONNX: msd-musicnn with the emoMusic and DEAM heads, and discogs-effnet with the MTG-Jamendo mood/theme head. They need a numpy mel front-end port. Results are aggregated per section.
Arousal is reported with more confidence than valence.

**lyrics.**
1. **Source cascade:**
   1. user `--lyrics` (.lrc with A2 word tags, .srt, .vtt, .txt, Lyricsfile);
   2. embedded tags;
   3. **LRCLIB**:
      - query `/api/get` with track, artist, album and **duration** (then without the album), **and always `/api/search` too**. `/api/get` can return a
        near miss while an exact match exists: for Jeremy it returned a 319 s entry, while search had one at 316.587 s, matching the file;
      - rank all candidates with rapidfuzz (title ≥ 90, artist ≥ 85), then by the **smallest |Δdur|** (≤ 2 s, or ≤ 5 s with a flag). Ties go to the
        candidate with the best alignment coverage;
      - parse speaker labels (`[Name:]`, `Name:` prefixes) from any source as singer hints. The rap battle's LRCLIB lyrics have none;
      - prefer `lines[].words` from the Lyricsfile when `hasWordSync`;
      - make requests sequentially, 200–500 ms apart, with an identifying User-Agent, honouring Retry-After on 429/503, and never call `/api/get-cached`;
   4. transcription. The **default is faster-whisper large-v3 int8 on CPU**, because its word probabilities feed the confidence score. It runs on lead_vocals with VAD,
      `condition_on_previous_text=False` and a hallucination filter. The ffmpeg whisper filter on Vulkan is used in `draft` or behind a flag.
2. **Word alignment**, always run. MMS_FA (torchaudio op or vendored Viterbi) on lead_vocals at 16 kHz:
   - 30 s windows with 2 s of context, and line-window constraints;
   - uroman and num2words;
   - repeated-section expansion, by matching a quick ASR pass to the lines;
   - global offset detection;
   - stable-ts as a fallback when coverage is below 0.6.
3. **Confidence** per word, line and song, an A–D grade, and `lyrics_match_score`.
4. **Exports**: lyrics.json, lines.tsv, LRC, VTT, SRT and ASS.

**voices.** Proposes who sings each line:
- Speaker embeddings on the vocal stem for every aligned line, and for words in long lines, using a pretrained speaker-verification model. W0 picks between
  SpeechBrain ECAPA-TDNN (torch, already in the env) and a WeSpeaker ONNX model, and checks it on the rap battle.
- Agglomerative clustering into voices `V1…Vn`. n comes from the user's character count in `intent.md` when given, otherwise from an eigengap or silhouette estimate.
  Short or low-energy spans inherit the voice of their neighbours.
- Speaker labels from the lyrics source act as hints that override the clusters.
- Output: a voice per line and word span with a confidence value, plus per-voice activity.
- The interview asks the user to map each voice to a character, and the viewer offers a play button per voice for that. Lines with low confidence are flagged for review.
- Rap battles usually open with a spoken announcer intro, which becomes its own voice.

**lipsync.**
- **Must:** `vocal.mouth_open.<voice>` (vocal-stem envelope, about 10 ms attack and 60 ms release, gated by that voice's aligned word spans, policy `max`).
  With one voice it is simply `vocal.mouth_open`.
- **Should:** Rhubarb CLI visemes (`-d` with the aligned lyrics, A–H/X, with a Preston Blair mapping table in CONTRACT.md) and phonemes.
- **Could:** in-house g2p + MMS character spans.
- The spike checks Rhubarb on sung vocals.

**choreo.** Eight-counts **restart at every phrase start and section start**; count 1 is the phrase's first downbeat.
- A remainder of 1–3 bars becomes a short count (length 4 or 6) flagged `partial`. Pickup beats get count null, and a 5-6-7-8 lead-in is synthesised.
- Each count carries an accent (drum hits, onsets and vocal onsets) and a sub-count (1 & e a).
- Per bar: a 16-step groove matrix (kick, snare, hat, perc), swing ratio, syncopation index and a groove ID.
- Hit points: coinciding accents, impacts and stops, ranked.
- Holds: sustained vocal notes, held chords, decay tails and silences.
- A movement-density curve.

**cues.** `cues.json` is **the list agents cut from**. Each cue is `{id, t, kind, tier, strength, lead_in_s, next_major_in_s, source{file, id}}`.
- Tiers:
  - 1 = section start, drop, build start;
  - 2 = phrase, impact, stop;
  - 3 = hit point, downbeat;
  - 4 = beat.
- `lead_in_s` is the recommended anticipation window: the build length for a drop, one bar for a section.
- Beats appear only as tier-4 references to `events/beats.json`, not as copies. Dynamics events carry a `cue_id`.
- The stage also picks the top moments.

**meaning, brief, viewer, frames.** See §§ 4.7, 8 and 9.

---

## 6. Repository layout
```
mv-harness/
  PLAN.md README.md pyproject.toml uv.lock models.lock.json .gitignore .gitattributes
  envs/sep/{pyproject.toml, uv.rocm.lock, uv.cpu.lock}
  vendor/wheels/                       wheels built from pinned commit tarballs
  scripts/{bootstrap.ps1, mvh-env.ps1, mvh-env.cmd, gate.ps1}
  src/mvh/
    cli.py worker.py
    runner/   dag.py cache.py overrides.py provenance.py models.py doctor.py locks.py
    contract/ writer.py resample.py ids.py schema/ (envelope schemas)
    io/       ffmpeg.py audio.py
    stages/<name>/  __init__.py (StageSpec), stage.py, schema/, models.json, optional cli.py, README.md
    assets/   mvh.js mvh_load.py mvh.glsl golden/ viewer/
  skill/mv-harness/  SKILL.md  references/{CONTRACT.md (generated), RECIPES.md}
  tests/  unit/<stage>/  synth/ (shared primitives; per-module generators in synth/<module>/)
          contract/synth/ (generated multitrack fixture)  contract/real-<song>/ (gitignored)
          review/<module>/ (reviewer-written failing tests)  real/ (opt-in)  .cache/real/ (W0, gitignored)
  docs/   research/ CONTRACT.md SPIKE.md REVIEW-LOG.md RUNS.md SEAMS.md
  songs/ out/          gitignored: copyrighted audio, lyrics and outputs never enter git
```

---

## 7. Test and validation strategy

1. **Synthetic ground truth.**
   - **The synthetic song** (W1). A 45–60 s multitrack whose generator ground truth *is* the contract fixture. It contains:
     - a drum loop with programmed swing and syncopation;
     - bass, a chord pad and a TTS vocal line (Windows SAPI);
     - a build into a drop, a silence, one 3/4 bar and a pickup;
     - two singers (a duet and a call-and-response).

     Its stems are the generator tracks.
   - **Per-module generators**: click tracks (tempo ramp, swing), EBU loudness signals, sweeps, rendered MIDI, vibrato "sung" sines, and edge cases (mono, 48 kHz,
     MP3 with encoder delay, a corrupt FLAC, 10 s and 10 min files).
2. **Acceptance thresholds.** These are the initial values. W0 may re-baseline the ones marked *, with the reason recorded in SPIKE.md.

   | Area | Measure | Threshold |
   |---|---|---|
   | Beats on clicks | F1 at ±70 ms | ≥ 0.98 |
   | Tempo | error | ≤ 0.5 BPM |
   | Kick events | F1 at ±10 ms; event time = the one-shot's sample onset | ≥ 0.95 |
   | Drums, kick/snare/hat | F1 | ≥ 0.9 |
   | Drums, tom/cymbal | F1 | ≥ 0.7 |
   | Loudness, EBU signals | error | ±0.1 LU |
   | Loudness vs ffmpeg | difference | ±0.5 LU |
   | Bass notes, monophonic | note F1 | ≥ 0.8* |
   | Vocal range | error | ±1 semitone |
   | Word alignment on TTS | median onset error | < 80 ms |
   | Word alignment on user songs | words within 300 ms (manual spot check of ≥ 100 words) | reported; gate set by W0 from a measured baseline, initially ≥ 75 %*; songs below it get a C/D grade |
   | Helper parity | JS vs Python | within 1e-6 at 23.976, 24, 25, 29.97, 30 and 60 fps, frame0 ∈ {0, 1}, all four policies |
   | Helper golden vectors | cases covered | across a voiced/unvoiced boundary, a pickup bar, an odd-length section, and wrapped-texture sampling (equal to `curve.at`) |
3. **Real songs.** Snapshots of the key scalars and event counts, compared with tolerances. Cross-tool agreement is reported, not asserted. Click previews and the viewer metronome
   support listening checks. Song-specific checks:
   - **Rap battle:** line-to-voice attribution, checked against a hand-labelled key the user confirms once in the viewer (gate: ≥ 90 % of lines correct after the
     user maps voices to characters); word alignment on dense rap, reported; three distinct mouth_open channels.
   - **Jeremy:** LRCLIB picks the 316.587 s entry; the vocal range is plausible for a baritone (reported); no lyric words are placed in the instrumental outro after
     the last synced line (about 217 s).
4. **Contract and platform.**
   - Everything is schema-valid and the brief token caps are enforced.
   - Determinism: run twice with `--force` on CPU and diff.
   - The separator stems sum back to the mix (−30 dB).
   - A real CLI run with `PYTHONUTF8` and `PYTHONIOENCODING` removed, on `tëst ♪ 曲.flac` in a folder whose name contains spaces.
   - The **override round trip**: edit in the viewer, the affected stages re-run, and the change appears in the output, with the meaning re-anchored.
5. **Dogfood.** In W4, R-DOGFOOD builds a sketch from the output that responds to the music.

---

## 8. Meaning and creative intent

The user is the authority on what the song means.
1. `mvh analyze` writes `meaning/interview.md`. Its questions are generated from the facts found in the song: sections, hooks, repeated lines, credits, the mood arc and the
   detected voices. They ask who sings to whom, what the song means to the user, the world and its setting, the characters (and which voice each one is),
   visual references, the palette, how each section should feel and move, camera ideas, and what must never appear on screen.
2. The user answers in `meaning/intent.md` (free text or the YAML template). Answers can also be edited in the viewer, for example the singer of each line.
3. A **draft** fills the gaps:
   - The default is the calling agent. The harness writes `request.md`, `input.json` and `schema.json`.
   - `--meaning-draft anthropic` uses `claude-opus-5-5` with structured output. The build must read the `claude-api` skill before writing that code.
   - **Agent rule (SKILL.md):** if the meaning is pending and `intent.md` is empty, the agent shows the user the interview questions and waits. Only then does it draft the gaps, with
     `status: draft` set and without ever overwriting user claims.
4. **Merge**, with provenance on every claim: user > lyric > audio > external > speculative. Conflicts with the user's intent become questions for the user. `mvh validate`
   checks that the cited IDs and time ranges exist, that quotes are 10 words or fewer, and that every claim is typed.
5. **Lifecycle.** `intent.md` and the authored `meaning.json` are never overwritten by `mvh analyze`.
   - Every per-section claim stores `section_id`, `t_range` and the occurrence.
   - When sections change, `mvh meaning` re-anchors the claims by time overlap and writes `orphans.json` plus a warning in the brief.
   - An LLM re-draft runs only with `--force meaning`.
6. **Join.** The meaning stage writes `events/singing.json` `{t, d, character_id, voice, line_id}` from each line's singer, lead/backing activity and the characters.

`meaning.json` contains:
- logline, summary, themes, perspective (narrator and addressee);
- characters `{id, name, description, voice, lines}`; setting and world;
- motifs `{id, occurrences}`, symbolism;
- `sections[] {section_id, t0, t1, feel, meaning, emotion (lyric vs audio, with an agreement flag), palette_hint[hex], movement_hint, camera_hint,
  characters_present[], do_not[]}`;
- global palette and tone, do-not rules, open questions, and status (user, draft or pending).

Instrumental songs use the same structure, built from the user's intent, the title, the tags and the audio mood, and flagged as lower confidence.

---

## 9. Viewer and corrections

`viewer.html` uses vanilla JS and Canvas2D with no CDN (the same style as the user's `viz/`). All lanes share one zoomable time axis and a playhead synced to the audio, and a
"values at this frame" panel uses the same helper rules at a chosen fps and frame0.

| Lane | Shows |
|---|---|
| Overview | mix waveform tinted by bass/mid/high; section blocks with IDs |
| Meaning | per-section feel and meaning chips; characters; do-not rules |
| Lyrics & singers | line blocks coloured by singer; word ticks; karaoke readout; confidence shading |
| Beats & counts | beats and downbeats, bar numbers, eight-counts (partial and in-pulse flags), tempo curve, metronome click |
| Hits | kick, snare, hat and tom rows by velocity; onsets; hit points; holds |
| Bands | bass, mid and high plus the kick envelope; optional spectrogram |
| Loud & quiet | LUFS with shaded dynamics segments; impact and silence markers |
| Instruments | one strip per instrument or stem; solo and mute stems |
| Notes | piano roll per source; key and chord labels |
| Vocal range | f0 on a note axis; tessitura band; lowest and highest markers (click to jump); mouth_open; visemes |
| Cues | tiered cue list with lead-in shading |

**Edit mode** (only under `mvh view`) supports:
- beat offset, BPM override and downbeat phase;
- dragging section boundaries and relabelling sections;
- nudging lyric lines and words;
- assigning a singer per line;
- pinning moments.

A POST saves the edits to `overrides.json` (and singers to `intent.md`), and `mvh analyze` re-runs only the affected stages.

---

## 10. Agent integration
- **CLI.**
  - `mvh analyze <song> [--out] [--profile max|draft] [--lyrics f] [--intent f] [--only/--skip/--force stages] [--no-network] [--meaning-draft agent|anthropic|off] [--no-lyrics-to-agents]`.
    stderr shows progress. stdout gets a single JSON line `{manifest, brief, viewer, warnings, pending}`.
  - The other verbs are `status`, `validate`, `view`, `brief [--section S05]`, `meaning`, `frames --fps N [--frame0] [--curves] [--format csv|json|deforum]`, `models` and `doctor`.
    Stages may contribute verbs through their own `cli.py`.
- **Agent Skill** (`skill/mv-harness/SKILL.md`):
  - run the CLI;
  - **read brief.md first**, then `lines.tsv` if the video uses words;
  - **never cat curves or events into context**; use `lib/`;
  - follow the meaning rule in §8;
  - check the result in the viewer.

  `references/RECIPES.md` covers:
  - Remotion: `staticFile` with `delayRender`/`calculateMetadata`;
  - three.js: `THREE.DataTexture` with `mvh.glsl`, and a clock from `AudioContext.getOutputTimestamp()`/`outputLatency`;
  - Blender: `frame0 = 1`;
  - ComfyUI and ffmpeg;
  - the viz scenes via `vizState`.
- **Phase 2:** an MCP server (`mcp>=2.3,<3`) with summary-then-zoom tools.

---

## 11. Reviewers

Reviewers are independent agents. Each gets the code or artefacts and the spec, **but not the builder's conclusions**.

**Findings.** A finding is `{severity: blocker|major|minor, location, claim, evidence, suggested_fix}`. For every blocker or major, the reviewer writes the evidence as a
**failing test under `tests/review/<module>/`** (a path the reviewer owns). The fix is done when those tests pass under `scripts/gate.ps1`, so no separate re-check agent is needed. Minor findings go to `docs/REVIEW-LOG.md`.

| Reviewer | Lens | Reviews |
|---|---|---|
| **R-CONTRACT ("the video agent")** | Acts as a Remotion, three.js, Blender or ComfyUI agent building a choreographed, character-driven video. Checks that what it needs is present, unambiguous, cheap to load and safe for context, including the choreo and cue semantics | plan ✔, W1, M6b, W3 critic |
| **R-DSP** | Signal and rhythm correctness: units, time alignment, frame rules, viz-port fidelity, beat_this/allin1 pre-processing, fusion, synthetic-truth tests | M1, M2 |
| **R-ML** | Model use: pre- and post-processing that matches how each model was trained, ensemble arbitration, licences and SHA pins, CPU vs ROCm behaviour, the separator gain invariant | M3a, M3b, M4 |
| **R-WORDS** | Lyrics and meaning: the source cascade, LRCLIB etiquette, alignment, hallucination filtering, citation validation, the meaning lifecycle, lyrics privacy | M5, M6b (meaning) |
| **R-PLATFORM** | Windows: paths and Unicode, subprocesses, the ffmpeg resolver, env and lock hygiene, the worker, locks, determinism, cache keys, supply chain; checks the viewer through the browser preview tools | plan ✔, W1, M6a, W4 |
| **R-ADVERSARY** | Tries to refute "it works": independent ground truth, perturbed inputs (gain, 48 kHz, MP3, mono), cross-tool disagreement, tracing brief numbers back to their sources | W4 |
| **R-DOGFOOD** | With only `SKILL.md` and one output folder, builds a 20 s responsive sketch (three.js or Remotion) using counts, hits, lyrics, singers and meaning, and reports every point of friction | W4 |

✔ marks reviews already done: round 1 of the plan review used R-CONTRACT, a combined R-PLATFORM/feasibility lens and an orchestration lens. See docs/REVIEW-LOG.md.

---

## 12. Build pass (High effort + Ultracode)

### Rules for every build agent
- **Environment.** Start every shell command with `. scripts\mvh-env.ps1;`. Run Python only through `uv run --frozen --no-sync` (`UV_NO_SYNC=1`). Never use bare `python` or `pip`.
  Only the orchestrator syncs envs.
- **No git, no WSL.** The orchestrator commits through WSL.
  - It commits once per module when that module's pipeline passes its gate, staging only that module's owned paths.
  - Before each commit, `git status --porcelain` is checked against the ownership map.
- **Ownership.** Write only the paths you own.
  - Stages register by convention (§3.2). Each module owns its stage packages, its schemas, its `models.json` fragment and its CLI verbs.
  - Change requests (in the agent's report) are only for `pyproject.toml`/locks, envelope schemas or fields in the Consumed-by matrix.
- **Offline.** `HF_HUB_OFFLINE=1` and `MVH_OFFLINE=1`, so a missing model fails fast. Tests replay recorded HTTP.
- **Heavy work.**
  - Real-model inference in tests or tools runs inside `mvh.testing.heavy()`, one of two machine-wide slots (`%LOCALAPPDATA%\mvh\locks\heavy-0.lock` / `heavy-1.lock`, implemented by `scripts/heavy_lock.py`), and GPU work also takes `gpu.lock`.
  - `MVH_THREADS` (default 3) is applied in code by `tests/conftest.py` and the runner.
  - Runs expected to take more than 10 minutes go in the background with a log and a `.done.json`. Stage caching resumes interrupted runs.
- **Isolation.**
  - Analysis output goes to `out/_wip/<agent>/<song>/`, and tests use pytest `tmp_path`.
  - Fixture folders are read-only.
  - Servers bind 127.0.0.1 on port 0 and are stopped before the agent reports.
- **Privacy.** Never print lyric text in reports or logs. Recorded HTTP responses containing lyrics stay in `tests/.cache/` (gitignored); only synthetic HTTP fixtures are committed.
- **Gates** use `scripts/gate.ps1 <WF|module>`, which runs:
  - the module's tests, plus the reviewer tests in `tests/review/`;
  - `mvh validate` on the fixtures;
  - the ownership check, the token caps and the determinism diff.

  Gates rely on the gate script and the agents' structured reports, not on the orchestrator reading code.

### Workflows
| WF | Agents | Work | Gate |
|---|---|---|---|
| **Preflight** (orchestrator) | – | `songs/` contains at least one song with clear lead vocals, or the user agrees to run M5's real-song tests as xfail. Then a fresh shell runs `uv --version; ffmpeg -version; node --version` through absolute paths | user answer |
| **W0 Spike** | 2 in parallel: `env-main`, `env-sep` (+ all GPU work: ROCm and the Vulkan whisper) | See the W0 deliverables below | The orchestrator rejects W0 if any §5 tool lacks a dependency row; then updates §3 and §5 from SPIKE.md |
| **W1a Contract architect** (in parallel with W0) | 1 (needs only numpy, jsonschema and node through `uv run --no-project --with …`) | See the W1a deliverables below | — |
| **W1b Foundation** | 3 builders in parallel (runtime · lib · fixtures) → R-CONTRACT ‖ R-PLATFORM → 1 fixer | **runtime**: runner, cache, worker, locks, overrides, ingest, CLI, doctor, validate. **lib**: mvh.js, mvh_load.py, mvh.glsl, golden parity. **fixtures**: `tests/synth` primitives, the synthetic multitrack, `tests/contract/synth/` (from its ground truth), and `tests/contract/real-<song>/` (from the W0 cache via thin adapters) | Contract frozen at v1.0.0-rc |
| **W2 Modules** | `pipeline()` over 8 modules: builder → lens reviewer (writes failing tests) → fixer only if there are blockers or majors | See the module table below | Each module's gate script passes; commit per module |
| **W3 Integration** | 1 integrator → (≤ 1 fixer per affected module ‖ 1 completeness critic) → integrator re-run | See the W3 steps below | The orchestrator checks each song in the viewer |
| **W4 Final review** | R-ADVERSARY ‖ R-DOGFOOD ‖ R-PLATFORM → ≤ 3 fixers split by ownership | The orchestrator re-runs the gate and one `mvh analyze --profile max` | The user reviews a song of their choice in the viewer |

**W0 deliverables.**
- The locks: main, sep-rocm and sep-cpu, with the git-pinned dependencies built into `vendor/wheels/`.
- `scripts/mvh-env.ps1` and `.cmd`, and `bootstrap.ps1`.
- `models.lock.json` covering every library-managed file; all models pre-fetched, and the numba cache pre-warmed.
- Smoke-tested runtimes that research did not verify: torch + MMS_FA `forced_align`, all-in-one-infer, beat_this, lv-chordia, S-KEY ONNX, CLAP ONNX, stable-ts, piano transcription, madmom-infer DBN, the Vulkan whisper filter, Rhubarb on sung vocals, the speaker-embedding model on the rap battle, the ROCm separators and the OpenMP coexistence check.
- Then **sequential benchmarks** under the heavy lock, each recording the concurrent load.
- `docs/SPIKE.md` with:
  - one **dependency row per tool named in §5 and §7**: package or binary, env, lock line, licence and smoke-test result;
  - a go/no-go for each tool, with its fallback;
  - re-baselined thresholds.
- `tests/.cache/real/`, gitignored, containing:
  - `index.json`;
  - every stem for every song;
  - each model's raw output;
  - recorded identity, MusicBrainz, AcoustID and LRCLIB responses.

**W1a deliverables.**
- The envelope schemas and `docs/CONTRACT.md`, with the Consumed-by matrix and IDs.
- The golden-vector spec.
- **StageSpec stubs for every §3.2 stage** with their real deps. Each stub copies its outputs from `tests/contract/synth/`, so `mvh analyze` runs end to end from W1 on (a walking skeleton).

**W2 modules.**

| Module | Stages | Reviewer |
|---|---|---|
| M1 Signal | spectral, loudness, dynamics | R-DSP |
| M2 Rhythm | allin1, rhythm, structure, choreo, cues | R-DSP |
| M3a Separation | separate_fast, separate_hq (+ `envs/sep` worker code), stem_activity, drums | R-ML |
| M3b Pitch & timbre | notes, vocals, instruments | R-ML |
| M4 Harmony & mood | harmony, mood | R-ML |
| M5 Words | identity, lyrics, voices, lipsync | R-WORDS |
| M6a Viewer | viewer stage, `assets/viewer/`, `mvh view` server and edit-mode POST | R-PLATFORM (browser preview) |
| M6b Agent delivery | meaning, brief, frames, `skill/` | R-CONTRACT + R-WORDS |

All eight run at the same time, against `tests/contract/synth/` and `tests/contract/real-*`.

**W3 steps.**
1. The integrator applies the change requests and replaces the stubs.
2. It runs `--profile draft` on one song, then `max` on all songs in the background.
3. It writes `docs/SEAMS.md`, with each item routed to the module that owns it.
4. Then, in parallel:
   - fixers, at most one per affected module, each limited to that module's paths and one round;
   - a **completeness critic** (R-CONTRACT lens), which fills a matrix: R1–R20 and the §4 files → stage → test → present in the real output → usable by a choreography or character agent → licence recorded.
5. The override round-trip test.
6. `docs/RUNS.md`.

**Expected agent count:**

| Phase | Agents |
|---|---|
| W0 | 2 |
| W1 | 1 + 3 + 2 + 1 |
| W2 | 8 + 8 + ≤ 8 (typically 4–5 fixers) |
| W3 | 1 + ≤ 4 + 1 |
| W4 | 3 + ≤ 3 |

The total is **about 35–45 agents over six workflows**, with the orchestrator gating between them. Fixes that are still open after their one loop go to W3's module fixers, not to the orchestrator.

### Git
- The repo is empty. The first commit puts this plan and the research on `master`.
- The build runs on `build/v1`, with one commit per module or gate, and the user merges.
- Remote: `git@github.com:OpenSrcerer/mv-harness.git`.
- `uv` fetches the pinned-commit tarballs over HTTPS (no git needed).

---

## 13. Risks
| Risk | Mitigation |
|---|---|
| The openmirlab packages are recent, come from one org, and are no longer on PyPI | Commit-pinned tarballs built into `vendor/wheels/`; beat_this stays standalone as the primary beat tracker |
| Model mirrors disappear (one BS-RoFormer host was deleted in 2026) | SHA-pinned `models.lock.json`, a local cache, a fallback per model |
| ROCm on Windows is a preview | The sep worker's cpu variant runs the same models; doctor decides; a `degraded` flag otherwise |
| audio-separator re-normalises levels by default | Thresholds disabled; a stems-sum invariant test |
| The Harmonix label vocabulary has no pre-chorus or drop | Custom EDM roles; probabilities exposed; corrections in the viewer |
| Heavily limited masters flatten LUFS | Dynamics also use bass, kick density and spectral slope |
| Lyrics: LRCLIB coverage, partial embedded lyrics, Whisper hallucinations on music, sung-vocal alignment around 56–75 % within 300 ms | Source cascade, repeat expansion, stem-only ASR and filters, A–D grade, nudges in the viewer, a measured gate |
| torchaudio forced_align is in maintenance mode | Vendored CTC Viterbi with parity tests |
| Meaning drafts invent facts | Typed and cited claims, a validator, user intent wins, interview first |
| Several agents on one machine (CPU, caches, PermissionError) | Heavy/GPU locks, offline flags, `UV_NO_SYNC`, per-agent output folders, atomic writes with retry |
| Context blow-ups in the agents that consume the output | No arrays in the manifest, capped brief, section zoom, lines.tsv, skill rules |
| JS and Python helpers drift apart | Golden vectors that cover every helper row |

---

## 14. Open items for the user
1. ~~Add vocal test songs~~: done (Jeremy (Redux Version) and Sir Isaac Newton vs Bill Nye, both on LRCLIB with synced lyrics). In W3, you confirm the
   rap battle's voice-to-character mapping once in the viewer; that becomes the attribution key.
2. Optional free keys: `ACOUSTID_API_KEY` (only for untagged files) and `ANTHROPIC_API_KEY` (only for `--meaning-draft anthropic`).
3. ROCm needs nothing from you: Smart App Control is already off and the driver is current. If ROCm still fails in W0, the build stays on CPU.
   Adding Defender exclusions for speed is optional and a manual step for you.
