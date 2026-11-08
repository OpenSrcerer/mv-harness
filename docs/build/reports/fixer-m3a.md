# fixer-m3a report (M3a Separation, one fix round)

Status: **partial**. F1 and F3 are fixed and their review tests pass; F2 (classifier path at the PLAN gates) is only
partly reachable and its review test still fails. `scripts\gate.ps1 M3a` does not exit 0 (reasons below).

## F3 (karaoke on mono): fixed
`separate_hq` detects a mono or dual-mono mix (`mvh.sep.fit.is_mono`, side energy >= 30 dB under mid) and skips the
karaoke step (worker param `skip_steps`). `lead_vocals := vocals`, `backing_vocals` silent, `lead_backing_split=false`,
flag `sep:lead_backing_mono`, fallback `lead_vocals:=vocals(mono)`. Review test `test_karaoke_mono` passes. Unit tests:
mono stage path, `is_mono`.

## F1 (drumsep path on separated stems): fixed
Measured on the reviewers' separated synthetic song (out/_wip/r-ml-m3a/synth sub-stems, +-10 ms): kick 1.000, snare
0.993, hat 0.918, tom 0.857, cymbal 0.769 (was 1.000 / 0.979 / 0.749 / 0.800 / 0.615). Both review tests of
`test_drums_separated_synth.py` pass on a fresh end-to-end run (ROCm, DrumSep). Changes in `drums/core.drumsep_hits`:
- an air-band (8-16 kHz) low-threshold detector on the hi-hat stem (`detect_air`): quiet hats on a broadband bed rise ~1 dB
  full-band but 8-10 dB in the air band (recovers most of the 52 lost drop hats);
- pre-echo drop (next 30 ms >= 15 dB louder than the first 30 ms);
- bleed judged on strokes (onsets within +-8 ms, or within 60 ms for pre-echo / ripple), not on energy that rings on in
  another stem (the old forward-looking level track dropped real quiet hats and kept ripples);
- hi-hat stem shape rules: crash / ride routed into the hi-hat stem (dull above 7 kHz, slow decay, large rise) are
  relabelled `cymbal`; weak dull bumps and kick-click / snare-noise leakage are dropped; a hat with a ride stroke of the
  same level at the same instant is that stroke's copy;
- ride / crash stems: hits more than 12 dB under the stem's 2nd loudest, or 10 dB under a hi-hat stroke, are leakage;
  coincident cymbal hits of different sub-stems are merged; toms 20 dB under the stem's loudest are leakage;
- `conf` is multiplied by `0.5 + 0.5 * clip(vel / 0.15, 0, 1)` (faint hits are mostly bleed).
Margin on hat is thin (0.918 vs 0.9); the reviewers' ROCm run is not bit-reproducible.

## F2 (classifier path): partial, review test still FAILS
`core.classify` on the generator's clean drum stem, before -> after: kick 0.977 -> 0.977, snare 0.943 -> 0.967,
tom 0.421 -> 1.000, hat 0.795 -> 0.793, cymbal 0.160 -> 0.444. Kick, snare, tom meet the gates; hat (0.9) and cymbal (0.7)
do not. Done: tonal-tom rule (body >= 15 dB over 1.5-6 kHz and the sub band 10 dB under the body), air-band events,
and a template-excess pass (a lone kick or snare stroke whose high bands sit above the song's own bare-stroke floor
carries a hat, or a ride / crash).
Why the rest is not reachable with honest rules: ~25 closed hats of the drop sit under the decaying snare tail in the
mixed drum stem (hi-hat stem alone shows them at +10 dB, the mixed stem at +2 dB or less, no onset), 8 more hats and 8
rides sit under snares with the same band ratios as each other (a hat under a snare and a ride under a snare differ
by 0.3 dB), and the generator crashes sit on kicks. A rule that separates them on this song would be a threshold of
0.3 dB fitted to the synthetic samples. I did not add it.
Follow-through as the reviewer suggested: in the classifier path the stage caps `conf` of hat / cymbal / perc at 0.45,
tags them `low_confidence_class`, adds `summary.low_confidence_classes` and a warning; `core.CLASSIFIER_RELIABLE`
= kick, snare, tom. The builder's unit test now asserts the gates for those three and floors (hat 0.75, cymbal 0.4)
for the rest.

## Minor findings
- m4 (faint hits keep high conf): done (velocity factor on `conf`).
- m6: `variant_order` is validated (fails fast on `"[cpu]"` etc.); `normalization_threshold` / `amplification_threshold`
  are honoured by the worker (defaults 100 / 0).
- m7: `gain_gate` fails an inverted stem.
- m8 (lead/backing fragile beyond mono): covered for mono only. A per-segment confidence for the split is not done.
- m1 (provenance duplicates, sha256), m2 (guitar/piano confirmation from `other`), m3 (per-alternative agreement in
  meta/stems.json), m5 (piano activity): not done (m1 needs the runner / provenance schema).

## Gate (scripts\gate.ps1 M3a), log out/_wip/fixer-m3a/gate.log
- unit: separate_fast, separate_hq, stem_activity, drums pass. `tests/unit/contract` fails `test_stub_files_are_stubs`
  (rhythm is no longer a stub: another module's work, not mine).
- review: 3 of 4 pass; `test_classifier_path_meets_plan_f1_on_the_clean_synthetic_drum_stem` fails (hat 0.793, cymbal 0.444).
- ruff: my files are clean after the fix; the one remaining error is in `src/mvh/stages/spectral/dsp.py` (another module).
- contract, validate, e2e (539 s), lib-node: PASS.
- determinism: the differing files are curves/core, chroma12, mood_1hz, spectrum128, vocal and manifest (stems, drum_hits and
  stem curves identical); the `spectral` stage fails with `KeyError: 'kick_viz_excess_db'` in that run (another module).

## Not touched
`models.lock.json` schema: `mvh/envelope/models_lock` already validates the lock (0 errors), nothing to change.

## Real end-to-end runs (mvh analyze --only ingest,separate_fast,separate_hq,stem_activity,drums)
- newton-vs-nye: rocm, lead_backing_split true, no flags, sum residual -35.98 dB; drums kick 200, snare 371, hat 703, cymbal 69, tom 60.
- jeremy: rocm, lead_backing_split true, no flags, sum residual -30.27 dB; drums kick 644, snare 355, hat 712, cymbal 319, tom 25.
- `pytest -m real tests/unit/drums` (4 real-song hit-rate checks on the W0 fixtures): pass.
