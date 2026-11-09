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

## Round 4 (reviewer r-ml-m3b-r4, W3)

Fix verification, S04 (MEGAFAUNA: lyrics and singing have a singer, but vocals said none):

- **Fixed in code, and not a test hack.** `vocals` now tracks the full `vocals` stem when lead_vocals' p95 is more than 20 dB below it
  (`instruments/lead.py`, the same rule as lyrics). It reads `lyrics/lyrics.json`, and pitched frames inside aligned lines pass the
  voice gate. Presence is also true when at least 4 pitched seconds fall inside at least 20 s of lines.
- **Re-run on a copy of the integrator folder** (`out/_wip/r-ml-m3b-r4/megafauna`; stale upstream re-run with
  `--only spectral..lyrics,vocals`):
  - Result: `present` true, 6.96 voiced s, E3-E4, 10 phrases and 33 vocal notes (all three were 0 before).
  - 6.89 of the 6.96 s lie inside lines, and 6.83 s of those lie inside aligned word spans. So the gated pitch follows the words,
    not the synth intro: only 0.07 s lies outside lines.
- **The integration test still fails as committed.** `tests/integration/M3b/test_real_vocal_presence.py` reads
  `out/_wip/integrator/megafauna`, where vocals has not been re-run since 05:10. The integrator has to re-run vocals there.
- **Regressions on real songs:** none outside vocals.
  - jeremy: 194.0 → 196.3 voiced s, E3-C#5 tenor, 588 → 589 notes.
  - newton-vs-nye: identical. The tagger's voice is 1.0 in every line, so no frame is admitted by lyrics alone.
  - versatile: no lines. present stays false.
  - MEGAFAUNA notes and instruments: counts identical, and `notes/notes.mid` is byte-identical to the integrator's.
- **Tests:**
  - tests/unit/{vocals,notes,instruments}: pass.
  - tests/review/M3b/r-ml round-1/2 tests: 3 pass.
  - `tests/unit/contract/test_catalog_dag.py::test_deps_match_plan` FAILS on `vocals`, because the new `lyrics` dependency is not
    in PLAN_DEPS (see r4-m3).

New majors (failing tests in tests/review/M3b/r-ml/, see the report):
- **R-ML-M3b-r4-1:** lyric lines with no acoustic timing still gate voice. `_lyric_mask` ignores `timing_source`, `conf` and
  `grade`, so interpolated or lrclib_line lines with conf 0 turn a synth lead into a singer.
  Test: `test_vocals_lyric_gate_hallucination.py` (synth sawtooth gives present, 24.96 s, p2 57 / p98 69, 52 notes).
- **R-ML-M3b-r4-2:** lyric-only frames are tallied as singing, which flips a rap lead to `singing` and runs the range statistics over
  the rap. Test: `test_vocals_lyric_frames_flip_rap.py`. None of the 4 real songs triggers it today.

New minor findings:

| id | where | claim | evidence | suggested fix |
|---|---|---|---|---|
| r4-m1 | `contract/catalog.py` CONSUMES["vocals"] (frozen; integrator) | vocals now also reads `file:lyrics/lyrics.json (lines t/d)`, `audio:vocals`, `curve:stem.vocals.active` and `file:meta/stems.json stems.vocals.present`. The catalogue lists only lead_vocals inputs. The decision file I-M3b-14 mentions only the lyrics file. | `vocals/__init__.py` L68, L103-L108, L145; catalog.py L789. | Add the four inputs to CONSUMES["vocals"] with the PLAN_DEPS change. |
| r4-m2 | `vocals/__init__.py` STAGE.params | `lyric_min_voiced_s` (4) and `lyric_min_s` (20) are read with `prm.get(..., default)` but are not declared in STAGE.params. They are absent from the declared defaults and from the provenance params, so the human-correction surface does not show them. The I-M3b-14 text names them as params. | STAGE.params keys end at `lyric_pad_s`. | Declare both in STAGE.params. |
| r4-m3 | `tests/unit/contract/test_catalog_dag.py` PLAN_DEPS (integrator) | Gate regression from the S04 fix: `test_deps_match_plan` fails on vocals. This is already routed in docs/contract/decisions/M3b.md. | pytest: 1 failed, 53 passed (unit vocals/notes/instruments + DAG). | Integrator: `"vocals": {..., "lyrics"}`. Also re-run vocals in out/_wip/integrator so the S04 test sees the fix. |
| r4-m4 | `instruments/__init__.py` vocal style (SwiftF0 sustain on `lead_vocals`) | On MEGAFAUNA vocals now pitch-tracks the `vocals` stem, but the style tagger's pitch-sustain feature still runs on lead_vocals (-74 dBFS p95). That leaves no sustain evidence, so the style tally there is 7 s `speech`. vocal_range then reports style `speech` and basis "sung frames (rap/speech-dominant lead)" for a lead that lyrics, voices and meaning treat as sung. | Probe of out/_wip/r-ml-m3b-r4/megafauna: vocal_style secs {speech: 7.0}; vocal_range.style speech. | Use `lead.pick_lead_stem` in instruments' style block as well (same 20 dB rule). This needs an instruments re-run, which only invalidates instruments and vocals. |
| r4-m5 | `vocals/__init__.py` stem rescue via the stem vote | On Versatile (lyrics instrumental, 0 lines) the stem vote triggers the vocals-stem rescue. vocal notes rise 16 → 27 and phrases 6 → 10 while `present` stays false. choreo (`notes.vocals`, `vocal_phrases`) and brief read those events whatever `present` says. | Probe of out/_wip/r-ml-m3b-r4/versatile: present false, 5.59 voiced s, 27 notes, 10 phrases. | Either take the rescue only with lyric lines, or flag the events (or leave them empty) when `present` is false. |
| r4-obs | runner (not M3b) | Observation for R-PLATFORM: an `--only vocals` run refused because upstream was stale dropped all `vocal.*` channels from curves/index.json and curves/vocal.f32, while the vocals event and meta files stayed. | Copy of megafauna at 08:34. | Keep the curve files of stages that did not run. |

## Round 5 (reviewer r-ml-m3b-r5, W3)

Fix verification:
- **R-ML-M3b-r4-2 (lyric-only frames flip a rap lead to singing): fixed, and the fix is real.** Untagged voiced frames
  inside lines now take the tagger's dominant style, so a missed rap verse stays rap. `test_vocals_lyric_frames_flip_rap.py`
  passes with MVH_REAL=1 (style rap, basis null). **But the fix regresses MEGAFAUNA** (new major R-ML-M3b-r5-2): the
  inheritance also applies to "speech", which the r4 suggestion carved out.
- **R-ML-M3b-r4-1 (lyric lines without acoustic support open the gate): only partly fixed.**
  `test_vocals_lyric_gate_hallucination.py` passes, but only because it uses `timing_source` "interpolated" with conf 0.
  - The `conf <= 0.02` part never fires on real data. `lyrics/core._word_conf` floors word confidence at 0.1, so every
    line has conf >= ~0.06. Measured: every line on megafauna, newton-vs-nye and jeremy is "ctc", with conf 0.09-1.0.
  - Forced alignment always places supplied text, so a supplied line is "ctc" or "stable_ts", never "interpolated".
  - End-to-end evidence: `out/_wip/r-ml-m3b-r5/karaoke`, a 40 s voiceless synthetic song (clicks, bass, saw lead) analysed
    with 8 user lines. Result: 7 ctc lines (conf 0.12-0.30, line grade D) plus 1 stable_ts line (conf 0.72), song grade D,
    34.5 s of coverage. vocals logged "lyric coverage 34.5 s in 8 line(s) counted as voice evidence". It stayed
    `present` false there only because the separator put the saw in "other".
  - Re-reported as R-ML-M3b-r5-1 with the measured lines.

Real-song reruns (copies of r4's folders; spectral..lyrics re-run because rhythm and lyrics were stale, then vocals):
- **megafauna:** present true, 6.96 voiced s, vocal notes and phrases have the same counts as r4. **The range is now null**: r4 had
  E3-E4, p2 52.1 / p98 67.0, alto, conf 0.44. Now spoken_pitch covers 6.96 s and style is speech. `notes/notes.mid`
  is byte-identical.
- **newton-vs-nye:** identical to r4 and to the integrator: 72.12 s, rap, range null, spoken_pitch 72.12 s, 259 notes,
  `notes.mid` identical.
- **Tests:** tests/unit/vocals 18 pass (6 real tests skip without MVH_REAL), and both r4 review tests pass with MVH_REAL=1.
- **`tests/integration/M3b/test_real_vocal_presence.py`** still reads the stale integrator folder (vocals 05:10,
  present false). On the r5 rerun `present` is true, so it would pass once the integrator re-runs lyrics and vocals.

New majors (failing tests in tests/review/M3b/r-ml/, see docs/build/reports/r-ml-m3b-r5.md):
- **R-ML-M3b-r5-1:** forced-aligned lines on a voiceless song still open the voice gate.
  Test: `test_vocals_ctc_lines_on_voiceless_song.py`. Result: present, 27.1 s, p2 57 / p98 69, 58 notes.
- **R-ML-M3b-r5-2:** the r4-2 fix makes untagged sung frames inherit a stray "speech" label, which erases MEGAFAUNA's range.
  Test: `test_vocals_inherited_speech_drops_range.py`. Result: range null, spoken 23.2 s.

New or still-open minor findings:

| id | where | claim | evidence | suggested fix |
|---|---|---|---|---|
| r5-m1 | `vocals/__init__.py` `_lyric_mask` L78 | The filter strings "user_line" and "none" are not in the contract's `timing_source` enum (catalog.py L559), so they are dead. The conf test is also dead (see r5-1). | catalog enum: user, lrclib_word, lrclib_line, ctc, whisper, stable_ts, interpolated. | Keep only enum values, and use a working signal (see r5-1). |
| r4-m2 (still open) | `vocals/__init__.py` STAGE.params | `lyric_min_voiced_s` and `lyric_min_s` are still undeclared, so they are missing from the provenance params (checked in the karaoke run's done.json). | `provenance.params` ends at `lyric_pad_s`. | Declare them. |
| r4-m4 (now consequential) | `instruments` vocal style on `lead_vocals` | The stray "speech" label that r5-2 inherits comes from CED and SwiftF0 run on MEGAFAUNA's near-silent lead_vocals. | vocal_style {speech: 7 s}; it covers 0.07 of 6.96 voiced s. | Use `lead.pick_lead_stem` in the style block too. |
| r5-m2 | integrator folder | `out/_wip/integrator/megafauna` still holds the 05:10 vocals output, so the S04 integration test fails on stale data, not on code. | vocal_range present false, 0 voiced s; the r5 rerun gives present true. | Integrator: re-run lyrics and vocals. |
