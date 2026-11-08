# SPIKE.md: W0 spike and W1a contract gate (2026-11-08)

This file is the gate record for workflow A (`wf_f9a3f942-cb7`). **It amends PLAN.md.** Where this file or
`docs/CONTRACT.md` (decisions D1–D28) disagrees with PLAN.md, this file and CONTRACT.md win.

Detailed evidence lives in:
- `docs/spike/main.md`: the main env, **one dependency row per tool in §5 and §7** (§3 of that file), the verified feeding
  recipes and the exact commands.
- `docs/spike/sep.md`: the sep worker env, ROCm, the separator models, the stems invariants and Vulkan whisper.
- `docs/spike/bench-music.md`: full-length benchmarks of the music tools on all 4 songs.
- `docs/spike/bench-words.md`: identity, LRCLIB, ASR, alignment, voices and lip-sync on jeremy and newton-vs-nye.
- `docs/build/reports/*.md`: the per-agent reports.

## Gate result: PASS

| Check | Result |
|---|---|
| Every §5/§7 tool has a dependency row | yes (`docs/spike/main.md` §3; sep tools in `docs/spike/sep.md` §5) |
| Main env | 142-package `uv.lock`, 28/28 smoke checks pass offline |
| Sep env | two uv projects (`envs/sep/cpu`, `envs/sep/rocm`), both verified; CPU and ROCm outputs agree to −110 dB or better |
| models.lock.json | 28 entries, all SHA-256 pinned (21 main + 7 sep/ggml merged from `envs/sep/models.fragment.json` by the orchestrator) |
| Real-song cache | `tests/.cache/real/` (about 15 GB, gitignored) with raw outputs from every tool on all 4 songs plus the sep stems |
| Contract | v1.0.0-rc.1 frozen; 90 unit tests pass in the main env; `mvh.contract.gen --check` confirms all 70 schemas are current |

## Decisions taken at the gate (orchestrator)

### Environments (amends §3.1)
- **Vendored wheels come from PyPI**, not commit tarballs: all-in-one-infer 3.1.0, madmom-infer 0.2.0, demucs-infer 4.4.0,
  SHA-verified in `vendor/wheels/`. The commit route (566f96c3 / a9ed04ec / ffe0080e) is not pursued.
- uv needs `environments = ["sys_platform == 'win32'"]` (basic-pitch pins tensorflow-macos).
- **ROCm works** for the sep worker: torch 2.11.0+rocm7.13.0 on gfx1201 (preview stream, pinned in `envs/sep/rocm/uv.lock`).
  It runs at about 1× real time; CPU is 15.6× slower. **The default sep variant is rocm, with cpu as the fallback.**
  `mvh doctor` re-runs the cuda matmul smoke test.
- audio-separator: set `normalization_threshold = 100.0` as an **attribute after `Separator()` construction** (the constructor
  rejects values above 1). The worker needs the ffmpeg bin first on PATH and `PYTHONPATH=<repo>/src`.
  audio-separator resamples input to 44.1 kHz.
- Heavy-lock protocol: `heavy-0.lock`, `heavy-1.lock` and `gpu.lock` under `%LOCALAPPDATA%\mvh\locks\`, implemented by
  `scripts/heavy_lock.py`. Its `run` subcommand needs an absolute, forward-slash interpreter path.
- No symlink privilege on this account (WinError 1314): libraries that symlink need a copy strategy (SpeechBrain uses
  `LocalStrategy.COPY`).
- `%LOCALAPPDATA%\mvh\config.json` is read with `utf-8-sig`.

### Tool recipes (amends §5)
- **demucs-onnx**: use the array route with our own ORT session (`_chunked_separate_single`, fp16 weights). Its public
  `separate()` reads paths through libsndfile and fails on Versatile.
- **all-in-one-infer 3.1.0**: there is no `AllInOneSession`. Call `analyze(stems_input=StemsInput(...))` with four float32 stem
  WAVs we write. Its labels are uninformative on electronic songs.
- **CLAP** is `Xenova/larger_clap_music_and_speech` (quantized). It has low contrast, so use it only for relative curves and
  user-supplied terms, never as a top-1 label.
- **CED-base** ONNX output is already a probability, so never apply a sigmoid.
- **S-KEY** uses a pinned HF revision of `musetric/skey-onnx` (NC weights). Its probability is flat, so confidence comes
  from window and cross-method agreement (KS/Temperley profile ensemble).
- **Rhythm**: beat_this half/double-tempo flips and madmom's downbeat phase are each wrong on 2 of 4 songs. The rhythm stage
  carries **tempo candidates** and a per-segment feel, arbitrates the tempo octave against kick evidence, and **fuses downbeats by a
  2-of-3 vote** (beat_this, allin1, madmom). MEGAFAUNA (about 105 / 143.6 / 193–200) is the regression case.
- **Dynamics**: fixed-threshold Foote segmentation fails on limited masters (Jeremy gets only 3 segments). Use adaptive thresholds plus
  bass and kick features, falling back to allin1 sections.
- **Pitch**: RMVPE is the arbiter, gated on confidence 0.3. SwiftF0 is **not** used for vocal presence on rap.
- **Vocal presence** must not come from stem energy alone. On MEGAFAUNA the Mel-RoFormer vocals stem picks up synth leads
  (−12.8 dB). Combine it with the instruments tagger and the lyrics.
- **Piano transcription** runs only when the piano stem is active and CED reports piano; on a silent stem it invents notes.
- **Lyrics cascade ranking**: after the title and artist gate, among candidates within 2 s, prefer `has_synced`, then the
  smallest |Δdur|. Always search (Jeremy's `/get` was 2.4 s off).
- **Global lyric offset detection is a Must**: apply it when |offset| > 0.15 s, and flag a version mismatch above 3 s
  (newton is −1.33 s).
- torchaudio's compiled `forced_align` is available, so the vendored `ctc_viterbi.py` is only the fallback before stable-ts.
- **Identity**: for version-tagged titles, retry MusicBrainz without the parenthesised tag, page past 8 results, and back off on 503.
- **Voices**: ECAPA is primary and WeSpeaker ONNX is the fallback. They give identical partitions at k = 3 and 4. The eigengap estimate is
  only a lower bound, so the user's character count wins.
- **mouth_open**: gate it with the **sustain-extended word span**: hold each word end to the next word start, and hold a line's last word while the envelope stays
  within 20 dB of p95, for at most 1.5 s. Use an ungated fallback for wordless vocals. Per-voice tracks are safe (5.6 % overlap).
- **Rhubarb** is a decoration track only (Should); it hardly ever closes the mouth on dense rap.
- **ffmpeg whisper filter**: draft/fast path only, **without `vad_model`** (Silero there is CPU-bound and drifts past EOF).
- `lead_vocals` from the karaoke pass is the stem for words, voices and Rhubarb.
- **Ingest**: Versatile loses its last 2291 samples (52 ms) to the corrupt frame. This is a warning, not an error.

### Re-baselined thresholds (amends §7)
- **separate_hq six-stem sum residual ≤ −20 dB** (was −30). Measured: −36.0, −30.3, −23.6 (MEGAFAUNA) and −35.2 dB.
  The per-stem gain gate is 0.1 dB for stems within 6 dB of the mix and 0.5 dB for stems within 20 dB.
- **separate_fast** has no −30 dB invariant: the htdemucs stem sum differs from the mix by 2–10 % RMS.
- **Alignment gate**: use checks G1–G8 in `docs/spike/bench-words.md` §5. They include lyrics_match_score ≥ 0.70, MMS word coverage
  (score ≥ 0.10) ≥ 0.75 with the stable-ts fallback triggered below 0.60, mean token score ≥ 0.30, and line placement
  within 1 s after the global offset ≥ 0.85. **Never gate on per-line mean score** (AUC about 0.5). The old 90 % word coverage
  target is retired. Both real songs grade B.
- The music thresholds are in `docs/spike/bench-music.md` §7. There is no ground truth, so F1 and accuracy targets stay on the synthetic fixture.

### Contract (amends §3.2, §4, §5, §8)
CONTRACT.md decisions D1–D28 are accepted as written. The most visible ones are:
- D1: a `meta/<topic>.json` folder.
- D2: `tables/*.csv` are produced by choreo.
- D3/D5: `speaker_hint` on lyrics; `singer` is a character and `voice_id` is a voice.
- D6: `notes.vocals` comes from the vocals stage.
- D7: drafts go to `meaning/authored.json`.
- D19: `frames` runs on demand.

`contract/writer.py` and `resample.py` from §6 are replaced by `conventions.py`, `curvefile.py` and `events.py`. The Writer
implementation belongs to the W1b runtime builder.

## Known gaps carried forward
- No ground truth exists for the real songs, so word timings, speaker identity, visemes, note F1 and chord accuracy rest only on agreement
  between tools. The synthetic multitrack fixture (W1b) carries the scored checks.
- The newton voice blocks are plausible but unlabelled. The user's voice→character mapping is the source of truth.
- Piano transcription was never exercised on real piano. htdemucs_6s piano quality is untested.
- Licences for the Mel vocals, karaoke and DrumSep models are recorded as personal use without a primary source.
- The ROCm stream is a preview (rocm7.13).
- Disk: about 15 GB in `tests/.cache/real/`, and the `sep/_work/` folders can be deleted.
