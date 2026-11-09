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

## Round 4 (r-ml-m3a-r4, 2026-11-09, W3 verify)

Re-checked against fixer-m3a-r3 (`cymbal_rise_db` 8 -> 4) and the W3 integrator's changes to M3a (D47: DrumSep on the
CPU). Ran: the fast and the real review tests (fresh synthetic end-to-end runs at 44.1 and 48 kHz, mono and near-mono
excerpts, CPU DrumSep), tests/integration/M3a and the module's unit tests, `drumsep_hits` at several rise floors on the
round-3 separated variants and on the integrator's real-song sub-stems, and the four stages re-run (`--force`) on
newton-vs-nye and versatile from copies of the integrator's folders. Probes: `out/_wip/r-ml-m3a-r4/probe/`.

### Status of round-3 findings
- **R3-1 (8th-note ride): fixed for the ride, but the fix causes a new major (R4-1).** The review test passes. On the
  round-3 separated stems of the ride-8ths mix, the drumsep path at the new floor gives ride recall .812 (26/32, was
  .219) and song cymbal F1 .806 (was .385). The recovered strokes come from the ride stem (21) and the hi-hat stem (5).
  On jeremy, the 35 ride-stem hits the new floor adds are real strokes: 69 % sit on the 16th grid (chance 28 %), and
  71 % show a 6-16 kHz rise in the drums stem.

### D47 (DrumSep on the CPU): verified
- newton-vs-nye, CPU sub-stems from the integrator vs the W0 ROCm sub-stems, same drums input (residual -300 dB):
  kick -139 dB, snare -130 dB, toms -106 dB, hi-hat -112 dB, ride -92 dB, crash -106 dB. The model behaves the same
  on the CPU. `meta/separation.json worker.devices` records `drumsep: cpu` next to the GPU RoFormer steps.
- The kick and snare FLACs of real songs peak above full scale (newton: 1.094 and 1.052), so the stage reads the float
  WAV copies it keeps beside them. A FLAC-only consumer gets clipped kick and snare sub-stems. This is a contract
  question for the integrator, not a model-use defect.

### New major finding (failing tests)
- **R4-1: the 4 dB floor also applies to the crash stem, and adds DrumSep artefacts and ring bumps as cymbal hits.**
  Tests: `tests/review/M3a/r-ml/test_r4_drums_crash_floor.py` (new, real-song sub-stems, 24 s) and the existing
  `tests/review/M3a/r-ml/test_r2_drums_separated_synth_48k.py`, which passed in round 3 and now fails.
  - **48 kHz synthetic song, fresh end to end** (current code, CPU DrumSep): cymbal F1 .596 against the PLAN §7 gate
    of .7 (round 3: .714). The same stems at the old floor give .714. The 5 extra false positives are 4 bumps in the
    ring 40-50 ms after a true ride or crash stroke (22.543, 24.01, 42.543, 52.55 s; rise 4-6 dB) and a snare leak in
    the ride stem (30.875 s). At 44.1 kHz cymbal F1 is .800 -> .791, and on the -6 dB master .821 -> .791.
  - **Real songs** (the fixer's reruns against the integrator's): jeremy has 169 -> 275 cymbal hits, megafauna 151 -> 180.
    Of the added hits, 81 (jeremy) and 34 (megafauna) come from the crash stem. Those hits:
    - are not events in the DrumSep input: a >= 3 dB 6-16 kHz rise in the drums stem at 6 % of them, which is the
      same rate as random instants (9-13 %);
    - fall on the 16th grid at 16 % and 21 %, which is chance level (28 %); kept ride hits score 80 %;
    - still get conf 0.81 / 0.84 and vel 0.46 (medians), so choreo and cues act on them.
  - The fixer's report says "the added strokes are ride strokes". On jeremy, 81 of the 116 are from the crash stem.
  - Suggested fix:
    - Lower the floor for the ride stem only.
    - Or admit a candidate below the old 8 dB only when the DrumSep input (the drums stem, already loaded for the
      classifier) shows a 6-16 kHz onset at that instant.
    - Mask cymbal-stem candidates within about 60 ms of a louder stroke in the same stem, unless they rise more than
      the old floor.
    - Keep `test_r3_drums_ride_eighths.py` and the 48 kHz gate green together.
- **R4-2: the Mel-RoFormer vocals and the karaoke split are not bit-reproducible on ROCm, so NF1 still fails.**
  Test: `tests/review/M3a/r-ml/test_r4_hq_vocals_determinism.py`.
  - D47 says "the RoFormer steps have no convolutions and stay on the GPU (bit-identical under memory pressure)". The
    integrator's experiment (`drumsep_det.py`) only measured DrumSep.
  - Two `separate_hq` runs of newton-vs-nye with the same code, params, models and devices: the integrator's max run,
    and this review's `--force` re-run of a copy, with other agents using the GPU.
  - What matches: the BS-RoFormer-SW stems (drums, bass, other) and the CPU DrumSep sub-stems are byte-identical.
  - What differs:

    | Stem | Max abs. diff | Residual | Samples changed |
    |---|---|---|---|
    | `vocals.wav` | 4e-7 | -134 dB | 87 % |
    | `instrumental.wav` | 3.9e-7 | -139 dB | 56 % |
    | `lead_vocals.wav` (karaoke) | 1.6e-3 | -75 dB | 97 % |
    | `backing_vocals.flac` (karaoke) | 1.6e-3 | -52 dB | 38 % |

    The karaoke model amplifies the vocals difference.
  - The failure is intermittent: the same re-run on versatile matched the integrator's run byte for byte. That fits
    kernels being chosen by the GPU state at run time, as D47 found for DrumSep.
  - Everything that reads these stems follows: stem_activity's curves and `meta/stems.json`, vocals, lyrics alignment,
    voices, lipsync, the manifest and the viewer.
  - Suggested fix:
    - Run the Mel-RoFormer and karaoke steps under the same rule as DrumSep (CPU, or a measured deterministic GPU
      setting such as `torch.use_deterministic_algorithms(True)` with fixed hipBLAS / attention kernels).
    - Re-measure SW 6-stem the same way, with a GPU memory hog, rather than relying on one identical pair.
    - Correct D47 in CONTRACT.md.

### Minor findings (round 4)

#### r4-m1. The jeremy crash stem was already mostly artefacts at the old floor
- At 8 dB, the 25 crash-stem cymbal hits on jeremy sit on the 16th grid at 12 % (chance 28 %). Only 25 % of the 16
  kept ones show a 6-16 kHz rise in the drums stem (kept ride: 93 %).
- R4-1's input-onset check would remove these as well.

#### r4-m2. Classifier "confirmation" of cymbals is not specific on real kits
- On the full drums stem, `core.classify` finds 1002 cymbals on jeremy and 534 on megafauna. That is about 3 per
  second of drumming, so a +-15 ms match is often chance.
- 24 of the 81 crash-stem artefacts on jeremy carry `classifier_agrees` (+0.15 conf). The same confirmation also
  relaxes the ride / crash leak gate (`rings and confirmed`).
- It should count as evidence only where the classifier's cymbal density is low, or only with a 6-16 kHz onset.

#### r4-m3. The lower floor also turns about 1-2 % of jeremy's hats into cymbals
- Hats go from 988 to 974 at 4 dB. Partly these are `ride_twin` relabels against the new low-rise ride hits (5 -> 8)
  and cymbal merges (7 -> 11). The rest was not traced.
- The count is small. It is listed so that the fixer for R4-1 checks hat F1 too.

## Round 5 (r-ml-m3a-r5, 2026-11-09, W3 verify)

Scope: verify fixer-m3a-r4's fixes for R4-1, R4-1b and R4-2, then look for regressions. All numbers below come from fresh
runs of the current code (folders under `out/_wip/r-ml-m3a-r5/`).

### Status of round-4 findings
- **R4-2 (RoFormer steps not bit-reproducible on ROCm): FIXED.**
  - Two `--only separate_fast,separate_hq,stem_activity,drums --force` runs of newton-vs-nye (`detA`, `detB`) were made on
    copies of the integrator's folder.
  - During `detB`, another process held 12.6 GiB of the 15.8 GiB free GPU memory and ran 1024x1024 matmuls the whole time.
  - Every stem, sub-stem, `events/drum_hits.json`, `meta/stems.json` and `curves/stems.f32` is byte-identical between the two
    runs. The stems also match the fixer's `det3`, run an hour earlier under different GPU load.
  - The fix (`mvh.sep.determinism`) is a real one, not a test hack:
    - a fixed-order 0/1 matmul replaces the atomic `scatter_add_`;
    - the `math` SDPA backend replaces the auto-tuned memory-efficient kernel;
    - rocBLAS replaces hipBLASLt.
  - Quality is unchanged: compared with the integrator's run, vocals differ at -133 dB, drums at -131 dB and the SW stems at
    -106..-126 dB. separate_hq takes 534 s against the integrator's 552 s, so there is no slowdown.
  - The round-4 test `test_r4_hq_vocals_determinism.py` compared two folders made by the OLD code, so it could never pass.
    It now compares `detA` with `detB` and passes; the versatile case skips. Override the folders with
    `MVH_REVIEW_M3A_DET_A` / `MVH_REVIEW_M3A_DET_B`.
- **R4-1 (crash-stem artefacts admitted by the 4 dB floor): FIXED.**
  - A ride / crash candidate that rises less than 8 dB must now show a >= 3 dB 6-16 kHz rise in the drums stem.
  - The test passes, which it must by construction, so it was checked independently against the beat grid, on the fixer's
    real reruns compared with the integrator's:
    - jeremy: ride hits 139 -> 163, with 79 % on the 16th grid (chance 28 %); crash 25 -> 22 (the crash-stem artefacts
      did not come back);
    - megafauna: crash 29 -> 28.
- **R4-1b (48 kHz synthetic cymbal gate): FIXED, with a thin margin.**
  - Fresh end-to-end runs give:
    - 44.1 kHz: kick 1.000, snare .993, hat .929, tom 1.000, cymbal .895;
    - 48 kHz: kick .994, snare .980, hat .921, tom .889, cymbal .737 (gate .7, about one hit of margin).
  - The pass relies on the new rule M3a-R4-3, which causes R5-1 below.

### New major finding (failing test)

#### R5-1. The coincidence-decay rule (M3a-R4-3) drops real ride strokes that land on a kick
- **Location:** `src/mvh/stages/drums/core.py` `drumsep_hits`: `coinc_decay_db=9.0` and the
  `stroke_level(h.sample, stroke_s)` check, which covers kick, snare and tom strokes.
- **What the rule assumes:** "snare crack leaking into the stem dies out faster". That holds on the synthetic song. Every hit
  the rule drops there sits at a snare stroke:
  - 44.1 kHz: 0.5, 9.5, 16.5 and 30.875 s;
  - 48 kHz: also 29.75 s;
  - the truth has a snare at each of those times.
- **What it actually does:** it fires on any kick / snare / tom stroke within +-6 ms, with a 4-16 kHz decay threshold tuned on
  the synthetic ride sample (real strokes decay 0.5-7.6 dB, leaks 10.6-14.5 dB). Real rides decay faster than that:
  - MEGAFAUNA: 88 % of the kept ride hits that are not at a drum stroke decay more than 9 dB (median 17.4 dB);
  - Jeremy: 25 % do.
- **Hits it drops that cannot be snare leakage** (integrator stems; the test re-runs `drumsep_hits` the way the stage does):
  - MEGAFAUNA: 133.85, 161.97, 166.54 and 171.12 s.
  - Jeremy: 66.71 and 191.86 s.
  - Their rise in the ride stem is 10.7-23.8 dB. There is no snare or tom hit within 8 ms.
  - In 4-16 kHz the ride stem is 6-37 dB above the kick stem and 16-43 dB above the snare stem.
  - The ride stem's 4-16 kHz waveform correlates 0.91-0.95 with the drums stem (the DrumSep input) and -0.82..0.27 with
    the snare stem.
  - A kick has no 4-16 kHz energy to leak, and a leak is quieter than its source. These are real ride strokes that were in
    every earlier round's output.
- **Which coincident rides survive is arbitrary.** On MEGAFAUNA, 6 of the 11 rides that coincide with a drum stroke survive
  only through the full-stem classifier's confirmation. That confirmation is near chance on real kits (r4-m2).
- **Test:** `tests/review/M3a/r-ml/test_r5_drums_coinc_kick_rides.py` fails on megafauna (4 hits) and jeremy (2 hits).
  - With the same criterion it passes on the synthetic stems at 44.1 kHz and 48 kHz and on versatile, so a narrower rule keeps
    the R4-1b gate.
- **Suggested fix:**
  - Apply the rule only to a SNARE (or tom) stroke at the same instant, or also require the snare stem to be at least as loud in
    4-16 kHz as the ride / crash candidate (a leak is quieter than its source).
  - Expose `coinc_decay_db`, `input_rise_db` and `input_check_below_db` as drums stage params.
  - Keep `test_r2_drums_separated_synth_48k.py`, `test_r4_drums_crash_floor.py` and this test green together.

### Minor findings (round 5)

#### r5-m1. D47 still states the claim R4-2 disproved
- `docs/CONTRACT.md` D47 still says the RoFormer steps "stay on the GPU (bit-identical under memory pressure)".
- The fixer's decision text (M3a-R4-2 in `docs/contract/decisions/M3a.md`) still reports an intermediate measurement:
  "identical ... in all but one of 4 runs" with a 90 % hog. The final configuration (rocBLAS) was identical in every run,
  including this review's full-song run with a hog.
- The W3 integrator should rewrite D47 to describe the three determinism fixes and drop the stale sentence.

#### r5-m2. The provenance cannot show that the determinism patch took effect
- `worker.settings.deterministic_roformer` is hard-coded `True`, including on the CPU variant and on steps where it does
  nothing.
- `mvh.sep.determinism.STATS` (patched vs fallback `scatter_add_` calls) is never reported.
- If an audio-separator update changed the mask-sum shapes, the patch would silently fall back to the atomic kernel, and only
  a determinism diff would notice.
- Suggested fix: record `STATS` per step and the effective BLAS backend in `meta/separation.json.worker`, and fail or flag
  when `patched == 0` on a Mel step on the GPU.

#### r5-m3. The new drum rules have no stage params
- `input_rise_db`, `input_check_below_db` and `coinc_decay_db` are library defaults in `drumsep_hits`. The drums stage passes
  only `bleed_db`, `bleed_rel_db` and `confirm_ms`.
- A user correcting cymbal recall on one song cannot reach them through `params` (PLAN: human-correction hooks).
