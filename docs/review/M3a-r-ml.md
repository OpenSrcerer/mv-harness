# M3a Separation: R-ML review (r-ml-m3a), minor findings

Reviewer: r-ml-m3a (lens R-ML). Date 2026-11-08. Blockers and majors have failing tests under `tests/review/M3a/r-ml/`
and are summarised in `docs/build/reports/r-ml-m3a.md`. Everything below was measured by running the code.
Runs: `out/_wip/r-ml-m3a/` (synth song, newton-vs-nye, 12 s excerpts at 44.1 kHz / 48 kHz / mono, a CPU-variant
excerpt); scripts in `out/_wip/r-ml-m3a/scripts/`. No lyric text is quoted anywhere.

## What holds (verified)

- **separate_hq gain invariants**: synth sum residual -35.3 dB, newton-vs-nye -36.0 dB (W0: -36.0); LS gains <= 0.03 dB on
  every gated stem; `instrumental + vocals == mix` and `lead + backing == vocals` at -150 dB; DrumSep sum vs drums -31.4 dB.
  normalization_threshold=100 / amplification_threshold=0 are set as attributes after `Separator()` (hq_worker), float WAV.
- **Faithful lift of the W0 reference**: the stage's newton-vs-nye stems equal the W0 `tests/.cache/real/newton-vs-nye/sep`
  stems to -84..-122 dB (bass, other, vocals, lead, backing, toms, hihat, crash); drums/kick/snare -58..-70 dB only because the
  comparison read the 24-bit FLAC, which clips peaks > 1 (the D23 float `.wav` twin exists).
- **Sample rate / channels**: a 48 kHz excerpt and a mono excerpt come back at the song's rate, channel count and length with
  zero lag (cross-correlation against the truth stems), and the same SDR as the 44.1 kHz excerpt (vocals 16.3, drums 19.4,
  bass 20.7 dB). Resampling is soxr precision 28 both ways.
- **separate_fast**: demucs-onnx array route; `mvh.sep.demucs` applies demucs.separate's song-level mean/std normalisation and
  scales back (demucs_onnx's chunker does not), fp16 weights, quarter overlap, 7.8 s segments as the export. Synth SDR vocals
  11.3, drums 14.7, bass 15.8, other 7.7 dB, zero lag; sum residual -31.5 dB (information only, as SPIKE says).
- **Vocal presence vs synth leads (SPIKE)**: MEGAFAUNA vocals `present=false`, conf 0.298 (SW vote ~0, htdemucs ~0.6);
  newton 0.989, jeremy 0.994, versatile 0.704, synth 0.997: the cross-model vote works where it exists.

## Minor findings

### m1. Provenance: duplicate and unused models, no SHA-256 pin (separate_hq, separate_fast, drums)
- **Evidence**: `out/_wip/r-ml-m3a/synth/.cache/separate_hq/*/_mvh/done.json` provenance.models has 9 entries: the runner's 5
  (every `STAGE.models` id, including `demucs_onnx_htdemucs_6s`, which did not run) plus the stage's 4 again with an extra
  `role` key (so `provenance_block`'s dedupe misses them). separate_fast (max profile, htdemucs only) also lists
  `demucs_onnx_htdemucs_6s` ("weights probably CC-BY-NC"). The separator `revision` is the mutable tag `model-configs`; the
  SHA-256 (the real pin, SPIKE §5) is in `ModelHandle.sha256` but nowhere in provenance. drums hard-codes a DrumSep licence
  string that differs from models.lock.json.
- **Fix**: stage side, emit model entries with the same keys as the runner (`id, licence, revision`) plus `sha256` of the
  checkpoint, only for models that ran; drums should copy the licence from separate_hq's provenance/meta. Change request
  (W3, runner): `models_prov` should list models the stage reports as used (or mark declared-but-unused), and the
  provenance schema should allow `sha256`.

### m2. Guitar / piano "confirmation" is not independent evidence (stem_activity, max profile)
- In the max profile the only alternative for `guitar` and `piano` is htdemucs `other`, which contains every non-drum,
  non-bass, non-vocal source, so the agreement is ~1 whenever SW's guitar/piano is active: MEGAFAUNA guitar conf 0.998
  (an electronic track where SW's guitar is probably synth; SPIKE: guitar 13.5 dB below the mix), jeremy 1.000, synth piano
  1.000. `evidence` lists `htdemucs:other`, which reads like a second opinion. 
- **Fix**: mark such evidence `superset:htdemucs:other` and cap the confidence (e.g. at the level-margin value) unless a
  dedicated alternative (htdemucs_6s guitar/piano, CED tagger in instruments) agrees; document that instruments must not
  treat it as confirmation.

### m3. MEGAFAUNA vocal verdict hangs on one model
- conf 0.298 against min_conf 0.4; htdemucs alone gives 0.594 (`present=true`). Without `sep/vocals_sw.flac` (the degraded
  htdemucs path, or an old cache) vocals would be confirmed on a synth lead. Record per-alternative agreements in
  meta/stems.json (`agreement: {sw: .., htdemucs: ..}`) so M3b/M5 can see the disagreement, and treat a strong disagreement
  as `unconfirmed` rather than averaging.

### m4. Faint drum hits keep high confidence
- On the separated synth, 10 hat hits with vel < 0.05 (peaks ~46 dB under the p98 hat) carry mean conf 0.84; they are
  bleed/artefacts (false positives at x.449 s in the intro). conf ignores velocity. Hat velocity correlation with truth on
  separated stems is 0.26 (cymbal -0.52) vs 0.87 on generator stems. Fold vel (or level vs top_ref) into conf.

### m5. Piano activity under-detected on the synthetic song
- SW leaves most of the synthetic piano in `other` (piano SDR 2.25 dB, -46.6 vs -40.8 dBFS truth): active ratio 0.079 vs
  0.283 in the truth's own measurement. notes masks by activity, so piano notes are lost. A second piano source
  (htdemucs_6s piano, CED piano evidence) could widen the activity; at least report the low-confidence presence.

### m6. Unused / unvalidated separate_hq params
- `normalization_threshold` / `amplification_threshold` are passed to the worker but ignored (hard-coded 100 / 0), so a user
  override would be recorded in provenance without effect. `variant_order` is not validated: `--param
  separate_hq.variant_order=[cpu]` (quotes eaten by PowerShell) became the string "[cpu]", every character was filtered out
  and the stage silently ran ROCm (out/_wip/r-ml-m3a/edge, first CPU attempt). Validate (list of known names) and fail fast.

### m7. `gain_gate` ignores polarity
- `invariants.gain_gate` takes `abs(w)`: a stem written with inverted polarity (w = -1) would pass the 0.1 dB gate. Gate on
  `w > 0` too.

### m8. Lead / backing assignment is fragile beyond mono
- Same 12 s synth excerpt, stereo: at 44.1 kHz lead SDR 8.3 dB, resampled to 48 kHz 13.5 dB; the karaoke model's
  split moves by 5 dB SDR on a resampling. Two ROCm runs of the same excerpt differ by -43 / -40 dB on lead / backing (vocals -125 dB, SW stems bit-identical),
  so the karaoke output is the least deterministic stem (determinism tolerances must allow for it). The CPU variant through
  the stage (`MVH_SEP_VARIANTS=cpu`, 12 s excerpt, 333 s) works and matches ROCm to -84..-117 dB on the SW, Mel and DrumSep
  stems, but only -39.9 / -36.5 dB on lead / backing (W0 newton: -73 / -51 dB).
  Expose a per-segment confidence for the split (e.g. lead share of the vocal energy) so voices/lyrics can tell.

## Round 2 (r-ml-m3a-r2, 2026-11-09)

Re-verification of the fix round (fixer-m3a) by running the code: fresh ROCm end-to-end runs of the synthetic song at
44.1 kHz and 48 kHz, separate_hq on near-mono excerpts, and probes on the generator's clean sub-stems. Runs and scripts in
`out/_wip/r-ml-m3a-r2/` (`scripts/*.py`). Blockers / majors have failing tests under `tests/review/M3a/r-ml/test_r2_*.py`
and are summarised in `docs/build/reports/r-ml-m3a-r2.md`.

### Status of round-1 findings
- **F1 (drums on separated stems)**: fixed for the 44.1 kHz synthetic song. A fresh ROCm run reproduces the fixer's
  numbers exactly (kick 1.000, snare 0.993, hat 0.918, tom 0.857, cymbal 0.769), both F1 review tests pass, and the
  crashes at 34.5 / 42.5 / 52.5 s are cymbals. The fix does not generalise (new majors N1-N3: a song-wide cymbal gate,
  an absolute brightness threshold, and a 48 kHz rendering of the same song at tom 0.545 / cymbal 0.514).
- **F2 (classifier path)**: not fixed; the review test still fails (hat 0.793, cymbal 0.444). The mitigation (conf capped
  at 0.45, `low_confidence_class`, `summary.low_confidence_classes`, warning, `degraded:drums`) does not reach the
  consumers: the choreo and cues packs project `events:drum_hits` to `t, drum, vel` (catalog.py lines 803 / 818) and
  `curve:drums.{hat,cymbal}` are velocity-scaled, not conf-scaled. Re-reported as major.
- **F3 (karaoke on mono)**: fixed for exact mono / dual mono (side >= 30 dB under mid). Not fixed for near-mono: at
  side -24 dB (L/R correlation 0.992) the split still inverts with no flag; the "backing louder than lead" sanity flag
  was not added. Re-reported as major.
- Minors: m4 (velocity in conf), m6 (params honoured, `variant_order` validated), m7 (gain gate fails w <= 0) verified
  done in code. m1, m2, m3, m5 and the m8 split confidence are still open as written in round 1.

### Minor findings (round 2)

#### r2-m1. The tom gate is song-wide, like the cymbal gate (N1)
- `drumsep_hits(tom_gate_db=20)` drops tom hits more than 20 dB under the toms stem's 3rd loudest hit, song-wide. Less
  aggressive than the 12 dB cymbal gate (a fill 20 dB under the loudest is rare), but on jeremy it removes 96 tom
  candidates (121 -> 25 hits; 29 of the removed cymbal/tom candidates rise >= 15 dB, i.e. look like strokes; no truth
  to settle it). Make both gates local (relative to the drum stem's level around the hit, e.g. a 4-8 s window) rather
  than to the song's loudest strokes.

#### r2-m2. Separation flags do not reach `manifest.status.flags`
- `finalize.py` collects `fallback:*`, `degraded:*`, tempo and key flags, not `meta/separation.json` `flags`. So
  `sep:sum_residual` and `sep:gain` (and the new `sep:lead_backing_mono`) only reach the manifest as warnings; the mono
  case surfaces only through `fallback:lead_vocals:=vocals(mono)`. Change request (W3, runner): fold `sep:*` flags in
  like `key:*`.

#### r2-m3. The classifier cross-check never adds hits
- In the DrumSep path the classifier on the full drum stem only raises conf (+0.15) of hits that already exist. When a
  DrumSep sub-stem drops strokes (N3: 10 of 16 rides and 5 of 8 toms are not even candidates in the 48 kHz run) nothing
  recovers them. A classifier hit with no DrumSep counterpart could be added at low conf with evidence
  `classifier_only`, at least for tom (the classifier now reaches tom F1 1.0 on the clean drum stem).

## Round 3 (r-ml-m3a-r3, 2026-11-09)

Re-checked against fixer-m3a-r2 by running the code: all review tests, fresh ROCm end-to-end runs of the synthetic
song at 44.1 kHz and 48 kHz, the mono and near-mono excerpts, two new separation variants (-6 dB master, 0.5 s of
leading silence that moves every separator chunk boundary), the W0 stems of all four real songs, and probes on the
generator's clean sub-stems (scripts in `out/_wip/r-ml-m3a-r3/probe/`).

### Status of round-2 findings
- **F2 (classifier path hat / cymbal): fixed with one of the round-2 options.** `core.classify` is unchanged (clean drum
  stem: kick .977, snare .967, hat .793, tom 1.000, cymbal .444). On the stage with `drums.path="classifier"`, hat and
  cymbal have vel <= 0.45 (raw value in `vel_raw`) and conf <= 0.45. Kick vel goes up to 1.0. The fallbacks are
  `drums:classifier` and `drums:low_confidence(hat,cymbal)`, and the envelopes follow the scaled vel. Round 2 asked for
  the review test to be updated to the chosen behaviour, so `test_drums_classifier_path.py` now checks the PLAN gates
  on kick, snare and tom plus that scaling.
- **F3-R (near-mono karaoke): fixed.** On the narrow-24 excerpt the split is dropped (`sep:lead_backing_suspect`,
  `sep:lead_backing_narrow`, `lead_backing_split=false`, lead = vocals). The mono excerpt is flagged
  `sep:lead_backing_mono`. On the real W0 stems the new rule only flags, because all four masters are wide (side/mid
  -7.4 to -15.1 dB):
  - megafauna: backing 33 dB over lead, flagged `sep:lead_backing_suspect`.
  - versatile: lead only 2.5 dB over backing, flagged `sep:lead_backing_suspect`.
  - jeremy (lead +9.2 dB) and newton (+22.4 dB) are not flagged.

  `checks.lead_share_frames` exposes the per-second confidence.
- **N1 (soft passage loses cymbals): fixed.** Clean sub-stems, kit attenuated in 16.9-20.95 s, 16.9-24.5 s or
  34-56.5 s by 0 to 24 dB: cymbal recall in the window does not change (8/9, 15/16, 3/3). In 0-34 s it stays 16/17
  except at exactly -20 dB (see r3-m3, a detector level cliff that is not caused by the gate). Crash level relative to
  the ride (+0 to +12 dB) and ride level (0 to -12 dB) leave ride recall at 1.0.
- **N2 (absolute brightness threshold): fixed.** The hi-hat stem was darkened by a high-cut of 6-25 dB above 6.5 kHz
  (typical brightness -3 to 13 dB): all 32 open hats stay hats, hat F1 .964-.997 and no relabels. On the real W0 hi-hat
  stems, slow-decaying (open-like) and fast-decaying hits have the same median brightness relative to the stem's
  typical value (newton +0.4 / +0.3, jeremy +0.1 / -2.9 dB), and only 2-5 hits per song are relabelled (megafauna 65,
  an electronic kit). Residual: r3-m4.
- **N3 (gates hold for one separation output only): fixed.** Fresh ROCm runs, all passing (gates .9/.9/.9/.7/.7):

  | Run | kick | snare | hat | tom | cymbal |
  |---|---|---|---|---|---|
  | 44.1 kHz | 1.000 | .993 | .926 | 1.000 | .800 |
  | 48 kHz | .994 | .980 | .917 | .889 | .714 |
  | -6 dB master | 1.000 | .986 | .910 | .800 | .821 |
  | 0.5 s pad | .994 | .980 | .916 | .941 | .757 |

  The margins are still thin: hat by 1-2 hits in each run, cymbal by 1 hit at 48 kHz.

### New major finding (failing test)
- **R3-1: a ride in 8th notes loses about 95 % of its strokes.** Test:
  `tests/review/M3a/r-ml/test_r3_drums_ride_eighths.py`. Ride / crash candidates need a broadband rise of
  `cymbal_rise_db` = 8 dB, and each stroke rises over the ring of the previous one. One clean ride stroke of the
  generator, tiled at a uniform spacing, gives these results:

  | Ride rate | Spacing | Recall |
  |---|---|---|
  | quarter notes | 0.5 s | 1.0 |
  | 8ths at 120 bpm | 0.25 s | .967 (rise 8.2 dB) |
  | 8ths at 140 bpm | 0.214 s | .057 |
  | 8ths at 150 bpm | 0.2 s | .053 (rise 6.4 dB) |

  With `cymbal_rise_db=4`, recall is 1.0 and precision 1.0 at every tempo. End to end (the synthetic MIX with its ride part doubled at +0.214 s, real ROCm separation): ride recall .219 (7/32), song cymbal F1 .385 (gate .7). A ride with dynamics loses its softer strokes
  in the same way: every other quarter-note stroke 6 dB down rises 7.5 dB and is lost (ride recall .56). The synthetic
  song only has quarter-note rides, so no gate exercises this.

### Minor findings (round 3)

#### r3-m1. Duplicate drum events from the classifier
- `core.classify` can emit two hits with the same (sample, drum): two band-onset clusters snap to the same broadband
  onset. In the DrumSep path, `drums.run` adds classifier-only toms against `have`, which is computed before the loop,
  so both copies are added. In the 48 kHz run `events/drum_hits.json` holds `(32.132, tom)` twice (1 of the 2 tom false
  positives). On the classifier path the duplicate goes straight out: `(8.996871, hat)` twice on the synthetic
  separated stem. Fix: dedupe on (sample, drum) in `classify`, and update `have` as toms are added.

#### r3-m2. Classifier-only toms carry full vel (and outrank the DrumSep toms)
- The recovered toms (N3 fix) have conf <= 0.5, but `velocities()` pools their peaks with the DrumSep toms' peaks. The
  two sources measure on different signals: the full drum stem's 160-400 Hz band or broadband peak, against the toms
  sub-stem.
- On newton the 15 `classifier_only` toms get vel .74-1.0 and the 19 DrumSep toms get .36-.88. The consumers read
  `t, drum, vel`, so the unverified toms become the song's strongest tom accents. This is the same gap F2 closed on the
  classifier path.
- On the synthetic song the two scales happen to agree. Even there tom vel tracks the programmed velocity poorly
  (Pearson .41 on clean sub-stems; a second stroke 125 ms after the first rides on its ring).
- Fix: scale `classifier_only` vel by its conf cap, as on the classifier path, or compute vel per source.

#### r3-m3. The detector's adaptive threshold has a level cliff near -60 dB
- `detect()` sets its threshold from the ODF spread over blocks whose 10 ms level is above `abs_floor_db + 10`
  (-60 dBFS). When a stem's strokes straddle that level, the block set and the threshold jump.
- The generator ride stem (peak -30 dBFS) scaled by -20 dB keeps 1 of 16 candidates at the 8 dB cymbal floor. At -19
  and -21 dB it keeps 16 of 16. The hi-hat stem at -28 dB loses 67 of 182 candidates.
- The real W0 sub-stems peak at -4 to -17 dBFS, so this matters for quiet masters or sub-stems only. A relative floor
  (for example the stem's p99 level minus 60 dB) would remove the cliff.

#### r3-m4. Residual of N2: open hats darker than closed hats
- The relabel rule `bright < typ - 7.5` (slow decay, large rise) still switches all at once on the hats themselves.
  Open hats only, darkened by 8 dB above 6.5 kHz: no change. By 10 dB: all 32 become cymbals, cymbal F1 .974 -> .535.
- The real stems do not show such a gap (see N2 above), so this is minor. A coincident ride / crash onset, or a decay
  longer than an open hat's, would make the relabel safe.

#### r3-m5. Hi-hat F1 sits at the gate on band-limited sources
- With the clean hi-hat stem low-passed at 10 kHz or at 12 kHz, as on a low-bitrate lossy source, hat F1 drops from
  .997 to exactly .900. At 6 kHz it is .787. No relabel or drop rule fires, so the loss is in the 8-16 kHz air-band
  detector, which finds the soft closed hats after an open hat. When the band above about 11 kHz is empty, the air band
  could fall back to 6-11 kHz.

#### r3-m6. `sep:lead_backing_suspect` fires on the stereo synthetic song
- The synthetic song is ordinary stereo: lead 6.4 dB over backing in the truth, separated lead minus backing 3.3 dB at
  44.1 kHz and 4.0 dB at 48 kHz. That leaves 0.3-1.0 dB of margin over the 3 dB `lead_suspect_db`.
- In the ride-8ths variant (only the drum part changed) the margin is gone: lead minus backing 2.7 dB, which raises
  `sep:lead_backing_suspect` and a run warning.
- On a wide master the rule only flags, so the cost is a false QA flag. But the flag also fires on versatile
  (+2.5 dB), and will fire on most duets.
- A per-section check on `lead_share_frames`, or a wider margin that applies only together with a narrow width, would
  be more specific.
