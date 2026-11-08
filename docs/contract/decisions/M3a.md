# M3a Separation: contract decisions and interpretations (builder-m3a)

Scope: `separate_fast`, `separate_hq` (+ `src/mvh/sep/**` worker code), `stem_activity`, `drums`. Everything here is
**additive** (CONTRACT §13) or an interpretation of a frozen field; nothing renames, removes or retypes a frozen field.

## Additive outputs and fields

| Stage | Addition | Kind |
|---|---|---|
| separate_hq | `sep/vocals_sw.flac` (cache only, optional): BS-RoFormer-SW's own vocals stem | new optional non-public output |
| separate_hq | `meta/separation.json`: `checks{}` (all invariants), `flags[]`, `definitions{}`, `worker{}` (torch, hip, audio-separator, settings, devices), `models[].role` | optional keys |
| separate_fast | `fast/separation.json`: `model`, `stem_level_vs_mix_db{}`, `notes[]`, `invariants.sum_error_db` (informational) | optional keys |
| stem_activity | `events/stem_activity.json` items: `conf` (0..1), `mean_rel_db` (dB) | optional item fields (documented in `fields`) |
| stem_activity | `meta/stems.json` per stem: `conf`, `evidence[]`, `present_energy`, `active_s`, `n_segments`; top level: `decision_window_s`, `min_conf`, `level_norm{lo,hi}`, `flags[]` | optional keys |
| drums | `events/drum_hits.json` items: `sub_stem`, `rise_db`, `in_active`, `evidence[]` | optional item fields |
| drums | provenance `drum_stats` (candidate / bleed / confirmation counts) | provenance extra |

## Interpretations

- **M3a-1 `backing_vocals = vocals - lead_vocals`** (exact) instead of the karaoke model's second output. The model's own
  second output equals it to about -150 dB (SPIKE); the difference is recorded as
  `checks.karaoke_backing_model_vs_vocals_minus_lead_db`. This makes `lead + backing = vocals` exact by construction.
- **M3a-2 Sum invariant** is on the six BS-RoFormer-SW stems (including SW's own vocals), gate -20 dB (SPIKE). A failure
  is a QA flag (`sep:sum_residual`) and a warning, never a stage failure: it is a model property (MEGAFAUNA -23.6 dB).
  The per-stem gain gate (0.1 dB within 6 dB of the mix, 0.5 dB within 20 dB) sets `sep:gain`.
- **M3a-3 Activity decision window.** `stem.{stem}.rms_db` uses the 46 ms window (as `loud.rms_db`); the *activity
  decision* (`active`, segments, `present`) uses a 0.4 s centred RMS so sparse parts (a kick every second, staccato
  stabs) do not flicker between hits. Hysteresis is non-causal: runs of qualifying frames joined across gaps
  < 500 ms, then runs < 300 ms dropped; a segment starts where the stem starts.
- **M3a-4 Split stems are judged against their parent.** For `drums_*` (DrumSep's input is the drums stem) and
  `lead_vocals` / `backing_vocals` (the karaoke model's input is the vocals stem) "within 18 dB of the mix" reads
  "within 18 dB of the parent stem", and the split can only be active where the parent is. Otherwise every hi-hat
  and most backing vocals sit more than 18 dB below the full mix and would never be active. `rel_db` curves stay
  relative to the full mix (literal registry description); `mean_rel_db` in the segments is relative to the
  reference that was used (`evidence` lists `reference:<parent>`).
- **M3a-5 `present` is energy AND cross-model confirmation** (SPIKE: vocal presence must not come from stem energy
  alone). `present_energy` keeps the energy-only verdict (>= 2 s active, or a quarter of a very short song).
  `conf` = mean over active frames of the agreement with an independent separator (`clip((alt_db - stem_db + 15)/9,
  0, 1)` on 0.4 s levels): htdemucs (separate_fast) for vocals/drums/bass/other/instrumental (guitar/piano against
  htdemucs `other`, or its own stem in draft), plus BS-RoFormer-SW's vocals for `vocals`; lead/backing inherit the
  vocals agreement; drum sub-stems use a level-margin confidence (no independent model). `present` requires
  `conf >= 0.4`; an energy-present but unconfirmed stem gets the flag `<stem>:unconfirmed` and a warning.
  Measured: vocals conf megafauna 0.30 (synth leads, present=false), versatile 0.70, jeremy 0.99, newton 0.99.
- **M3a-6 Level normalisation** of `stem.{stem}.level` is one p02-p99.5 range over all stems' non-floor frames (the
  registry says "per-song 0..1 over all stems"), recorded as norm lo/hi on every level channel.
- **M3a-7 Drum velocity** `vel` = peak |x| of the hit (first 30 ms) / p98 of the peaks of the same drum class,
  clipped to 1: loudness relative to the loudest hits of that drum (a programmed MIDI velocity is not recoverable
  across instruments from audio). `level_db` = the loudest 10 ms RMS in the 60 ms after the onset (dBFS).
- **M3a-8 Drum event time** is the one-shot's first sample: the first sample whose |x| exceeds
  max(1.5 x the tail's max |x| in the 5 ms before, 2 % of the attack peak). Measured on the synthetic song: median
  error 0.0 ms, p95 <= 0.6 ms for kick/snare/hat/cymbal; toms (tonal attacks on a tonal tail) median 3.3 ms.
- **M3a-9 `perc`** stays empty (zero curve, no events): DrumSep has no percussion stem and the classifier does not
  guess one. Claps and shakers land in snare/hihat via DrumSep.
- **M3a-10 Classifier path** runs only when there are no DrumSep sub-stems (`separate_hq` htdemucs fallback); the
  stage status is then `degraded` with fallback `drums:classifier`. In the DrumSep path the classifier also runs on
  the full drum stem and adds +0.15 confidence (`evidence: classifier_agrees`) to hits it confirms within 15 ms.
- **M3a-11 Hits outside `stem.drums.active`** are kept with confidence x0.6 and `in_active: false`.
- **M3a-12 separate_fast normalisation.** The song is normalised by its mono mean/std before demucs-onnx and the stems
  scaled back, as `demucs.separate` does (allin1 was trained on that pipeline). Stems are cache-only float32 WAV at
  the song's sample rate.
- **M3a-13 Non-44.1 kHz songs.** The separators get `ctx.audio('mix', sr=44100)` (ffmpeg/soxr); stems are resampled
  back to the song's rate with ffmpeg and fitted to the mix length and channel count; `instrumental = mix - vocals`
  is computed on the native-rate mix, so it stays exact.
- **M3a-14 DrumSep artefact rules** (core.drumsep_hits; stats in provenance `drum_stats.drumsep`). Measured on the
  synthetic song after real ROCm separation, they lift F1@10 ms kick .939 -> 1.0, snare .966 -> .979, hat .688 -> .749,
  cymbal .40 -> .615 (tom .80 unchanged) and leave the generator stems at kick/snare/hat/cymbal 1.0, tom .80:
  kick/snare candidates rising < 6 dB are separator second bumps (`weak_rise_dropped`); a ride/crash candidate under
  an 18 dB louder sub-stem that rises < 10 dB is bleed; a hi-hat candidate under a louder sub-stem whose brightness
  (> 7 kHz over 1.5-6 kHz, first 30 ms) is 12 dB below the stem's typical brightness is snare/kick bleed
  (`dull_bleed_dropped`); a ride/crash hit within 15 ms of a kept hi-hat hit that decays >= 6 dB in 30 ms is an open
  hat DrumSep routed into the cymbal stem (`hat_duplicates_dropped`).
- **M3a-15 Known ceiling.** On separated stems the PLAN §7 hat (>= 0.9) and cymbal (>= 0.7) F1 are not reached
  (.749 / .615): 36 of the 182 synthetic hats (soft closed hats 125 ms after an open hat) show no onset at all in the
  DrumSep hi-hat stem, and DrumSep splits the synthetic ride between ride and crash. The thresholds are asserted on
  the generator stems (the fixture's stems, PLAN §7.1), where every drum passes.

## models.lock.json envelope schema (explicit permission in the module brief)

`mvh/envelope/models_lock` now accepts what W0 wrote: `envs` items may be `main`, `sep`, `sep-rocm`, `sep-cpu`,
`ffmpeg-whisper`; top-level `schema` (integer), `generated_by`, `models_dir` and per-model `bundled`, `note`,
`notes`, `source` are optional; `schema_version` became optional. `models.lock.json` itself is unchanged
(`python -m mvh.contract.gen` regenerated `schema/envelope/models_lock.schema.json`; `--check` and
tests/unit/contract pass).

## Fixer round (fixer-m3a): additive changes and interpretations

- **M3a-F1 Mono / dual-mono input** (`separate_hq`): the karaoke lead/backing model needs a stereo pan cue, so for a
  one-channel song or a (near) dual-mono pair (`mvh.sep.fit.is_mono`: side energy >= 30 dB under mid) the karaoke
  step is **skipped** (worker param `skip_steps: ["karaoke"]`): `lead_vocals := vocals`, `backing_vocals` is written
  silent (D17), `meta/separation.json.lead_backing_split = false`, flag `sep:lead_backing_mono`, fallback
  `lead_vocals:=vocals(mono)`, the karaoke model is absent from `models[]`. Downstream stages already read
  `lead_backing_split` (stem_activity, voices).
- **M3a-F2 Drum hit labels**: unchanged vocabulary (`kick snare hat tom cymbal perc`). New `evidence[]` tags on drum
  hits: `air_band` (found by the 8-16 kHz detector), `relabelled_from_hihat_shape` (a crash/ride routed by DrumSep into
  its hi-hat stem, relabelled `cymbal`), `relabelled_ride_twin`, `template_excess` (classifier path: a hat / ride found
  under a kick or snare stroke), `low_confidence_class` (classifier path: hat / cymbal / perc). In the classifier path
  `conf` of those classes is capped at 0.45 and `summary.low_confidence_classes` lists them.
- **M3a-F3 Drum hit `conf`** is multiplied by `0.5 + 0.5 * clip(vel / 0.15, 0, 1)` (a faint hit is more often bleed).
- `separate_hq.variant_order` is validated (list drawn from rocm, cpu, htdemucs; anything else fails the stage);
  `normalization_threshold` / `amplification_threshold` are now honoured by the worker (defaults 100.0 / 0.0).
- `invariants.gain_gate`: an inverted stem (negative LS weight) fails the gain gate.
