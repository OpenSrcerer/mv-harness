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
