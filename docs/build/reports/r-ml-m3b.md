# r-ml-m3b report: R-ML review of M3b (notes, vocals, instruments)

Lens: model use (pre/post-processing vs training recipes, ensemble arbitration, licences and pins in provenance, CPU vs
ROCm, separator gain behaviour, gating against hallucinated output). Findings were formed from the code, the libraries'
own sources and runs; the builder report was read afterwards only to locate things. No real-song lyric text appears here.

Verdict: **pass-with-fixes**: 2 majors (failing tests under `tests/review/M3b/r-ml/`), 9 minors (`docs/review/M3b-r-ml.md`).
The model recipes themselves are right: basic-pitch, RMVPE, CED, CLAP audio and the piano CRNN are fed as trained.

## What was run

| Run | Command / harness | Output |
|---|---|---|
| Synthetic song, full pipeline (real upstream stages, real separate_hq) | `mvh analyze tests/contract/synth/_truth/synth-song.flac --out out/_wip/r-ml-m3b/synth --no-network` (14m51s, heavy-slot waits) | `out/_wip/r-ml-m3b/synth/` |
| Same, notes with a lower piano floor | `mvh analyze out/_wip/r-ml-m3b/synth --only notes --param notes.piano_min_active=0.02` | piano notes 0 -> 25 (18 correct) |
| Real songs (4) | M3b stages through the builder's `tests/synth/m3b/fxctx.run_stage` on the read-only overlays `out/_wip/builder-m3b/fx/<slug>`, 6 threads, one heavy slot | `out/_wip/r-ml-m3b/real/<slug>/<stage>/`, log `out/_wip/r-ml-m3b/realrun.log` |
| Edge cases | `edge_case("mono_44k")`, `edge_case("stereo_48k")` through the full pipeline | `out/_wip/r-ml-m3b/edge/<case>/` |
| Probes | CLAP text batching, RMVPE gain sweep, SwiftF0 timestamp offset, CED I/O and level, vocals on vibrato sung sines | reviewer scratch scripts (not committed) |

Scores vs `tests/contract/synth/_truth/` (onset +-50 ms, mir_eval):

| | Full pipeline (separated stems) | Builder cache (truth stems) | Threshold |
|---|---|---|---|
| bass note F1 | 0.858 | 0.907 | >= 0.8 (PLAN §7) |
| piano note F1 | 0 notes (gate) / 0.404 with floor 0.02 (P 0.72) | 0.985 | - |
| vocal notes F1 | 0.642 | 0.739 | - |
| vocal range | G3-A4 (truth 55-69) | G3-A4 | +-1 st |
| vibrato sung sines (G3..A4, +-40 c) | lowest/highest G3/A4 exact, p2/p98 54.7/69.1, 15/15 notes | | +-1 st |

Real songs: Jeremy present, 192 s voiced, range E3-C#5, p2/p98 53.2/70.6, register tenor; Newton vs Nye rap, 71 s voiced,
range null (rap rule), spoken pitch reported; MEGAFAUNA present=false (overlay lead stem is digital silence; instruments warns
the vocals stem is ~87 s of non-vocal content); Versatile present=false (1.5 s). Piano: 0 notes on all four (CED gate), no
invented notes. Mono 44.1 kHz edge case: no voice, pad notes A3/C#4 exactly, no crash.

## Majors

### R-ML-M3b-1 CLAP text prompts embedded in a padded, mask-less batch (major)
- Location: `src/mvh/stages/instruments/clap.py` `Clap.text` (used for the synth sub-type prompts, the neutral baseline and
  the user's `params.vocabulary` terms).
- Claim: the Xenova `text_model_quantized.onnx` has only `input_ids` (no `attention_mask`); `Clap.text` tokenises with
  `padding=True` and runs one batch, so `<pad>` tokens are attended and (dynamic int8) the batch composition changes every
  prompt's embedding. CLAP-derived curves therefore depend on which other prompts/terms are in the batch.
- Evidence: cos(batched, alone) = 0.843 for "a deep synth bass line", 0.970-0.987 for the other sub-type prompts; the user term
  "bass" batched with one longer term: cos 0.594. On a sawtooth pad the stage's sub-type split moves from pad/lead
  0.51/0.49 (batched) to 0.004/0.996 (alone). On Versatile 148 of 158 synth frames go to `synth_bass`, the most distorted prompt.
- Test: `tests/review/M3b/r-ml/test_clap_text_padding.py` (2 tests, fail now).
- Fix: encode each prompt alone (batch of 1) in `Clap.text`; or re-export with `attention_mask`.

### R-ML-M3b-2 Short piano parts get no notes: the activity floor is a fraction of the whole song (major)
- Location: `src/mvh/stages/notes/__init__.py` `run` / `_piano_gate` (`piano_min_active = 0.10`), documented as I-M3b-8.
- Claim: below 10 % of the song the gate returns "skip" before CED, and the basic-pitch fallback is blocked as well, with no
  warning (provenance only). The SPIKE rule is "CRNN only when the piano stem is active AND CED reports piano", meant to stop
  invented notes on a silent stem; it does not ask to drop an active, clean piano stem because the part is short. Piano
  notes are an explicit user requirement (R7).
- Evidence: full synthetic pipeline: piano stem active 4.5 s (0.079) -> 0 notes; with `--param notes.piano_min_active=0.02`
  the same stage writes 25 notes, 18 correct. Test case (8 clean piano notes, active 7.2 % of a 60 s song): 0/8 now; with the
  floor at 0.02 CED reports piano (mean 0.053) and the CRNN finds 8/8.
- Test: `tests/review/M3b/r-ml/test_notes_short_piano_part.py` (fails now).
- Fix: an activity floor in seconds (or per active segment), CED condition kept for the CRNN only, basic-pitch otherwise, and a
  warning when an active stem is skipped.

## Minors (detail in docs/review/M3b-r-ml.md)
m1 CLAP sub-type softmax at T = 0.01 is a per-second top-1 label in disguise (Versatile 90.5 % of synth frames one sub-type
> 0.9) · m2 SwiftF0 timestamps shifted by +8 ms although they are already frame centres · m3 "sustained" extremes accumulate
0.15-0.18 s glide fragments (Jeremy highest C#5 from 0.18 s, conf 0.45; held C5/B4 exist) · m4 register unstable at
boundaries (Jeremy tenor vs PLAN's baritone; the male synthetic lead reads alto) · m5 the -55 dBFS absolute level floor makes
presence gain-dependent · m6 `vocal_style.dominant` confident on instrumental songs (MEGAFAUNA speech 1.0 from 7 s) ·
m7 `models.lock.json` used_by incomplete for CED / SwiftF0 (not M3b-owned) · m8 no `vocals`-stem fallback when the karaoke
lead is empty · m9 CLAP edge windows zero-padded vs the extractor's `repeatpad`.

## Checked and consistent
basic-pitch array route identical to `run_inference` (padding, windows, output names, unwrap, frame times); RMVPE 16 kHz,
centred 10 ms frames on the contract grid, gain-robust to -50 dBFS peak; CED single `logits` output already in 0..1, no sigmoid;
CLAP audio windows exactly 10 s (no random crop, deterministic); piano CRNN 16 kHz, explicit checkpoint, CPU; ORT/torch
thread caps applied; provenance lists every declared model with licence and revision; all stages CPU (no ROCm path needed).

## Owned files written
- `tests/review/M3b/r-ml/conftest.py`, `m3b_fakectx.py` (in-memory Ctx for notes/vocals), `test_clap_text_padding.py`,
  `test_notes_short_piano_part.py`
- `docs/review/M3b-r-ml.md`, `docs/build/progress/r-ml-m3b.md`, this report; run outputs under `out/_wip/r-ml-m3b/`.

## Change requests
- Lock owner: `models.lock.json` `used_by` for `ced_base_onnx` (+notes, vocals) and `swift_f0_onnx` (+instruments) (m7).
