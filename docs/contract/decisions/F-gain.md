# F-gain: stem-based and onset events at one analysis level (final fix pass, agent ffix-gain)

Extends W4-AN-9 (one fixed analysis level: the gain that puts the canonical stereo mix's BS.1770 integrated loudness at
-10 LUFS) to the stages W4-AN-9 did not reach (W4V2-GAIN-DRUMS / STEMACT / VOCALS / SPECTRAL). Each stage takes a param
`analysis_lufs` (-10; `null` = the old master-level behaviour). The continuous curves stay absolute by design; dB fields
of events are still reported on the stem's / mix's own dBFS scale.

| ID | Stage (version) | Decision |
|---|---|---|
| F-gain-1 | separate_hq worker (`src/mvh/sep/hq_worker.py`, `src/mvh/sep/level.py`) | DrumSep (MDX23C) runs on the SW drum stem scaled by the mix's analysis gain and its six sub-stems are scaled back by the inverse gain, so `stems/drums/*.flac` keep the master's dBFS scale and the DrumSep-sum invariants hold. Worker param `drumsep_analysis_lufs` (default -10; null = master level). The sep env has no pyloudnorm, so `mvh.sep.level` carries a numpy + scipy BS.1770-4 integrated loudness (agrees with `loudness.r128.integrated` to < 0.1 dB; a pure gain shifts it exactly). The worker summary records `settings.drumsep_analysis_level` = {target_lufs, mix_lufs, gain_db}. The RoFormer stems are level stable and unchanged. **The runner's cache key has no code hash**: the separate_hq stage version must be bumped (change request) or old caches keep the master-level sub-stems. |
| F-gain-2 | drums 1.4.0 | Sub-stems and the drum stem are scaled by the analysis gain before every detector (classifier and DrumSep paths, the UD2 kick gate, the hat gate); `min_substem_peak_db` compares `peak_db + gain_db`. `drum_hits.level_db` is reported back on the stem's dBFS (`- gain_db`). The UD2 kick-source scores are relative (vel, agreement, gap shares) and now see level-invariant inputs. Additive `summary.analysis_level`. |
| F-gain-2b | drums 1.4.0 (core) | With DrumSep at the analysis level the synthetic hi-hat stem's typical brightness rose 1.5 dB and the final crash (52.5 s, routed into the hat stem) fell 0.6 dB on the wrong side of the dull-bleed drop. A hat-stem candidate that is crash-shaped (rise >= 2 x `click_rise_db` = 24 dB, decay < `cym_decay_db`, < `bleed_db` under the stroke it lands on, no snare stroke) skips the dull-bleed drop and goes to the existing cymbal relabel. |
| F-gain-6 | instruments 1.1.1, vocals 1.3.1 (`instruments/lead.py`) | `pick_lead_stem` (the karaoke-split rescue: track the full vocals stem when lead_vocals is "nearly silent") compared p95 levels over the NON-SILENT 10 ms frames. On a FLAC lead stem the faint bleed quantises to zero at -12 dB, so the p95 jumped to the voice fragments and the choice flipped (Versatile: vocals stem at master level, lead at -12 dB). New rule: `loud_frame_gap_db` = lead vs vocals energy over the vocals stem's loudest 10 % of frames; rescue when > `lead_gap_db` (20). Level invariant. MEGAFAUNA 40.4 dB (rescue, as before); Versatile 1.5 dB (its sparse lead is real: lead now, the vocals stem before); Jeremy 0.5, Newton 0.1, synth 1.9 (lead). `p95_db` now counts every frame. |
| F-gain-3 | stem_activity 1.1.0 | PLAN's absolute rule "> -45 dBFS" is re-expressed relative to the song: `active_db` (-45) applies at the analysis level, i.e. a stem is active above `-45 - gain_db` dBFS (and within 18 dB of the mix, unchanged). For a commercial master (about -10 LUFS) this is the PLAN rule within a dB (MEGAFAUNA: -45.8 dBFS). `meta/stems.json.thresholds.active_db` stays on the dBFS scale (its contract unit) and holds the effective threshold; additive `thresholds.active_db_at_analysis_level` (the param) and `thresholds.analysis_level` = {mix_lufs, gain_db, target_lufs}. The level-margin confidence uses the same effective threshold. rms_db / rel_db / level curves stay absolute. |
| F-gain-4 | vocals 1.3.0 | The lead stem (16 kHz mono) is scaled by the analysis gain before RMVPE, SwiftF0, CED and the presence gate, so `level_floor_db` (-55) is a level at the analysis level. `vocal_phrases.mean_db` is reported on the stem's dBFS (`- gain_db`); note velocities are per-song relative and unchanged. |
| F-gain-5 | spectral 1.5.0 | The events `hits.mid`, `hits.high` and `onsets.{bass,mid,high}` are picked on a second analysis pass over the mix scaled by the analysis gain (viz dB map, gates and 400 Hz refinement envelopes at one level). Curves (bands, viz values, flux, timbre, stereo, spectrum128 and the hit envelopes between events) come from the mix as is; `hits.<band>` curves flash at the events. An event's `db` stays on the absolute band curve. **`hits.kick` stays on the mix as is**: its gate is already master-relative (`gate_margin_db`), it held F >= 0.997 on -12 / -20 dB copies, and at a raised level a quiet a cappella's formants pass the -46 dB gate (tests/unit/spectral/test_w4_a_cappella.py). Additive `summary.analysis_level`. |

## Interpretations

- F-gain-I1: the -10 LUFS target matches W4-AN-9 (allin1 / rhythm / harmony / structure), so one song has one analysis
  level across the pipeline. On a commercial master the gain is under a dB and the outputs barely move.
- F-gain-I2: the viz-style flux onset rule is not level neutral (its dB map is affine above -88 dB): on the -16 LUFS
  synthetic groove, high-band recall is 0.77 at the native level and 0.64 at -10 LUFS. The unit test now checks both
  (0.7 native, 0.6 at the analysis level). Real masters already sat at about -10 LUFS, so their events do not change.

## Change requests (outside ffix-gain's paths)

- CR-F-gain-1 (separate_hq, M3a stage): bump `separate_hq` to 1.1.0 so cached stems are recomputed with the analysis-level
  DrumSep (the cache key has no code hash), and optionally expose `drumsep_analysis_lufs` as a stage param passed to the
  worker and copy `summary.settings.drumsep_analysis_level` into `meta/separation.json`.
- CR-F-gain-2 (lyrics, M5): the aligner and `lyrics/vocal_env.py` work on the vocal stem at the master level and keep
  the old p95 lead/vocals rule. On MEGAFAUNA -12 dB the first lyric lines (106-116 s) align elsewhere, which removes two
  vocal phrases downstream (phrase IoU 0.79). Scale the stem by the W4-AN-9 gain before alignment and adopt
  `instruments.lead.loud_frame_gap_db`.

## Known residual

- 48 kHz synthetic song (tests/review/M3a/r-ml/test_r2_drums_separated_synth_48k.py): cymbal F1 0.686 < 0.7. Six quiet
  rides (vel 0.47) under snares at 17.5-24.5 s: with DrumSep at the analysis level (+10.4 dB for this -20 LUFS mix) the
  ride stem carries them at -44..-58 dB with a 7-10 dB rise, and the cymbal leak gate drops them. Real masters (about
  -10 LUFS) reach DrumSep at the level they had before.
