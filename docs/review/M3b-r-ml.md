# M3b review, lens R-ML (reviewer r-ml-m3b): minor findings

Majors (with failing tests under `tests/review/M3b/r-ml/`) are in `docs/build/reports/r-ml-m3b.md`. Everything below was
measured by running the code; no real-song lyric text is quoted. Real-song numbers come from the M3b stages run on the
`out/_wip/builder-m3b/fx/<slug>` overlays (outputs in `out/_wip/r-ml-m3b/real/<slug>/`); synthetic numbers from a full
`mvh analyze` of `tests/contract/synth/_truth/synth-song.flac` (`out/_wip/r-ml-m3b/synth/`) and from reviewer probes.

| id | where | claim | evidence | suggested fix |
|---|---|---|---|---|
| m1 | `instruments/__init__.py` CLAP block (`z = (sims - mean) / 0.01`) | The synth sub-type "share" is a softmax at T = 0.01 over CLAP cosines, which turns differences of a few hundredths into near one-hot weights: `inst.synth_pad/lead/arp/bass` behave as a per-second top-1 CLAP label, which SPIKE.md rules out for CLAP. | Fraction of frames with `inst.synth` > 0.3 where one sub-type holds > 90 % of it: versatile 0.905 (148 of 158 frames `synth_bass`), newton-vs-nye 0.905 (108 of 126 `synth_lead`), megafauna 0.733. On a synthetic sawtooth pad the four shares were 0.004 / 0.996 / 0 / 0. | Use a temperature matched to CLAP's spread (e.g. T ~ 0.05-0.1, or z-score over time per prompt), and describe the channels as similarity ranks, not shares. Fix the batching major first (it distorts the bass prompt most). |
| m2 | `vocals/__init__.py` `ts = r.timestamps + 0.008` | SwiftF0 0.3.0 timestamps are already frame centres (`loudness_db` is the 32 ms centred on each timestamp; `_timestamps(k) = k * 0.016`); adding 8 ms shifts the second opinion by half a hop against RMVPE. | Vibrato sung-sine probe (G3..A4): mean abs error vs truth 0.042 st with offset 0, 0.056 st with +0.008; matched frames 828 vs 816. Only `vocal.conf` scaling and the agreement statistic are affected. | Drop the +0.008. |
| m3 | `vocals/pitch.py` `sustained_extremes` | "Sustained" extremes accumulate short glide fragments: any pitch with >= 0.3 s in total across notes >= 0.15 s qualifies, regardless of confidence. | Jeremy: highest = C#5 (t 200.54), whose longest note is 0.18 s (conf 0.45; the other 0.16 s, conf 0.39), while held C5 (0.57 s, conf 0.61) and B4 (0.85 s) exist. W0's conservative range was G3-G#4; the stage's p98 is 70.6 (A#4). | Require one held note >= ~0.3 s (after the consonant-gap join) and a minimum note conf, or weight by conf; keep the 0.15 s notes for `notes.vocals` only. |
| m4 | `vocals/pitch.py` `register_of`, `_female_share` | The register cue is unstable at the boundaries and the CED gender share is unreliable on synthetic or high male voices. | Jeremy (PLAN §7: "plausible for a baritone"): `tenor` (median 61.6, boundary 58). Synthetic song: lead V1 is the male voice (43 of 53 lead words) but `alto` (CED female share 0.61); a genderless harmonic sung-sine also reads `alto` (share 0.66). | Report `register: null` (or a two-way label) when the median is within ~2 st of a boundary or the female share is within 0.3-0.7; record the share in the document. |
| m5 | `vocals/__init__.py` level gate `max(level_floor_db=-55, p99 - 35)` | The absolute -55 dBFS floor makes vocal presence depend on the stem's absolute gain (the separators keep stems un-normalised). | Sung-sine probe at -50 dB gain (peak -59.6 dBFS): RMVPE voiced on 96 % of the true voiced frames, the level gate passes 0 %; at -40 dB gain it passes 98.6 %. RMVPE itself is gain-robust down to that level. | Use the relative criterion only (p99 - 35 dB) with a much lower absolute floor (e.g. -80 dBFS) as a digital-silence guard. |
| m6 | `instruments/__init__.py` `meta/instruments.json.vocal_style.dominant` | `dominant` is computed from style-segment time shares only, so a song with a few seconds of voice gets a confident-looking dominant style. Consumers (meaning, brief) read `dominant` without the voice coverage. | MEGAFAUNA: voice coverage 0.032 (one 7 s tagger segment), `dominant: speech` with share 1.0. Versatile (vocal chops, voice coverage 0.17): `speech` 0.97. | Set `dominant = "none"` below a voice-coverage floor (e.g. < 10 % or < 15 s), or add `voice_coverage` next to `shares`. |
| m7 | `models.lock.json` `used_by` (not M3b-owned) | Provenance relies on the lock for licences; `used_by` is incomplete for M3b models. | `ced_base_onnx.used_by = [instruments]` (also used by notes and vocals); `swift_f0_onnx.used_by = [vocals]` (also used by instruments). | CR to the lock owner: add the missing stages. |
| m8 | `vocals/__init__.py` reads `lead_vocals` only | When the karaoke split leaves `lead_vocals` empty while `vocals` carries a voice, vocals reports no lead vocal; instruments already falls back to `vocals` in that case (style only). | MEGAFAUNA overlay: `lead_vocals` -120 dBFS (active 0 %), `vocals` active 39 %; vocals: RMVPE voiced 1.2 s, `present: false`. Here the vocals stem is mostly synth, so the result is right, but the path is untested for a real lead routed to backing. | If `lead_vocals` is inactive and `inst.voice` is high on `vocals`, run the trackers on `vocals` and add a fallback tag (`vocals:lead_from_vocals`). |
| m9 | `instruments/clap.py` `audio_grid` | Windows are zero-padded at the song edges, while the CLAP feature extractor's own padding mode is `repeatpad`; the first and last ~5 s are embedded from half-silent windows. | `preprocessor_config.json`: `"padding": "repeatpad"`; `audio_grid` pads with `np.zeros`. | Clip the window to the song and let the feature extractor repeat-pad, or reflect-pad. |

## Checked and found consistent with the training recipes

- basic-pitch: `bp.BasicPitch.activations` reproduces `basic_pitch.inference.run_inference` exactly (22.05 kHz mono, half-overlap
  pre-pad of 15 frames x 256, 2 s windows of shape [1, 43844, 1], output names `StatefulPartitionedCall:1/2/0` -> note/onset/contour,
  `unwrap_output`, `model_frames_to_time`); arrays in, never a path. Mono = channel mean, resampled by ffmpeg soxr (precision 28).
- RMVPE: 16 kHz mono in, hop 160 with `center=True`, so frame k is centred at k * 10 ms = the contract grid; voicing gate on the
  salience max at 0.3 (SPIKE). Voicing is gain-robust (100 % of truth-voiced frames at peak -50 dBFS).
- CED-base: one input `waveform [B, samples]` at 16 kHz, one output `logits [B, 527]` whose values are already probabilities
  (0..0.52 on noise/silence); the stage applies no sigmoid. 4 s windows centred on every second, -70 dBFS silent windows skipped.
- CLAP audio: 48 kHz mono, exactly 480 000-sample windows, so `rand_trunc` never draws a random crop (deterministic).
- piano_transcription_inference: 16 kHz mono array, explicit checkpoint path, CPU, torch threads set; CED gate before it.
- Thread caps: every ORT session gets `ctx.threads` (RMVPE through the runner's SessionOptions patch); torch threads set.
- Vocal range on vibrato sung sines (+-40 cents, G3..A4, 15 notes): lowest/highest G3/A4 exact, p2/p98 54.7/69.1, all 15 notes
  found. Synthetic song through the real upstream stages: bass note F1 0.858 (>= 0.8), vocal range G3-A4 (truth 55-69).

## Round 2 (reviewer r-ml-m3b-r2)

Fix verification (both round-1 majors are fixed, and the fixes are real, not test-specific):

- R-ML-M3b-1 (CLAP padded batch): `instruments/clap.py` `Clap.text` now tokenises and runs every prompt alone (batch of 1,
  `padding=False`), so no `<pad>` token reaches the mask-less Xenova text model. The fix covers the synth sub-type prompts,
  the neutral baseline and the `params.vocabulary` terms. `tests/review/M3b/r-ml/test_clap_text_padding.py` passes (2 tests).
  Effect on real data: on Versatile (`mvh analyze --only instruments` on a copy of `out/_wip/builder-m3a/versatile`), the argmax
  sub-type over the 158 frames with `inst.synth` > 0.3 moved from 148 `synth_bass` (round 1) to pad 7 / lead 28 / arp 56 / bass 67.
  The distorted bass prompt no longer dominates.
- R-ML-M3b-2 (piano floor as a share of the song): the floor is now `notes.piano_min_active_s` = 1.0 s of activity. CED now only
  chooses between the CRNN and basic-pitch, and a stem active under the floor gets a warning. `test_notes_short_piano_part.py`
  passes. On the full synthetic song (spectral, rhythm, notes and vocals re-run on a copy of the round-1 song folder,
  `out/_wip/r-ml-m3b-r2/synth`), the piano part, active 4.48 s (0.079 of the song), now gets 25 notes, 18 of them correct
  (P 0.72), through the basic-pitch fallback (CED piano mean 0.024 on the synthetic piano voice), with status degraded and fallback
  `piano:basic_pitch`. Before the fix it got 0 notes. The low recall (18 of 64) comes from upstream: the separate_hq piano stem is
  about -115 dBFS from 17 to 37 s, where the truth piano plays.
- Regression checks: on the real songs (jeremy, megafauna, newton-vs-nye, versatile) the real `stem_activity` marks piano
  `present: false`, so the lower floor cannot add hallucinated piano notes there. Determinism: re-running instruments, notes
  and vocals on the synthetic song gave byte-identical outputs for all 17 M3b files (events, MIDI, curves, meta). Other
  checks: ruff is clean on the M3b paths, and tests/unit/instruments plus tests/unit/notes pass (24 tests). The bass F1 is
  still 0.858, and the vocal range is still G3-A4.

New minor findings:

| id | where | claim | evidence | suggested fix |
|---|---|---|---|---|
| r2-m1 | `instruments/__init__.py` CLAP block (`/ 0.01`) | Round-1 minor m1 is still there after the batching fix: the synth sub-type "share" is still a near one-hot per-second CLAP label. | Share of `inst.synth` > 0.3 frames where one sub-type holds > 90 %: synthetic song 0.849 (0.774 in round 1), Versatile 0.778. | As in m1: use a temperature matched to CLAP's spread (or z-score each prompt over time), and describe the channels as relative ranks. |
| r2-m2 | `notes/__init__.py` floor branch / `piano_min_active_s` = 1.0 | In the pipeline, the new floor and its "active under the floor" warning can never fire: `stem_activity` sets `present` only for >= 2 s of activity (`min_present_s`) with conf >= 0.4, and notes skips a stem that is not present before it checks the floor. A short piano part that `stem_activity` misses (present false, present_energy true) is dropped with no warning, only a method string. | `stem_activity/core.py`: `present_energy = active_s >= min(min_present_s, 0.25 * duration)`, then `present = present_energy and conf >= min_conf`. `notes._stem_present` returns before the floor. | Warn in notes when `present_energy` is true but `present` is false for piano, guitar or bass. Alternatively, align the floor with `min_present_s` and drop the dead branch. |
