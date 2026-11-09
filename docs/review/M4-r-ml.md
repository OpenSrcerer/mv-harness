# M4 Harmony & mood: R-ML review, minor findings

Reviewer: r-ml-m4 (independent, R-ML lens: model pre/post-processing, ensembles, licences, CPU/ROCm, gating).
Blocker and major findings carry failing tests under `tests/review/M4/r-ml/` and are listed in
`docs/build/reports/r-ml-m4.md`. Everything below is minor: it was verified by running code, but needs no gate test.

## What was checked and is fine

- **S-KEY pre-processing and label map.** 22.05 kHz mono, peak-normalised, `[1, samples]`. On synthetic I-IV-V-I / i-iv-V-i
  cadences in all 24 keys the wrapper's top key is exact 24/24, so `config.json` `keyMap` (its minor list starts at B minor) is
  parsed correctly by `skey_log`.
- **Essentia mel front end.** `mood/frontend.py` equals librosa's Slaney mel (Essentia `slaneyMel` + `unit_tri`) to 2e-9 in the
  filterbank and 6e-7 in `log10(1 + 10000 x)` (n_fft 512, hop 256, uncentred frames). Patch sizes/hops (187/93, 128/62) match the
  Essentia defaults; the ONNX head inputs (200-d musicnn `embeddings`, 1280-d effnet `embeddings`) match the heads' schemas;
  `(valence, arousal)` order matches the head JSONs. Real-song head values reproduce bench-music §5 (MEGAFAUNA emoMusic
  valence 0.374 / arousal 0.474 on 0..1 = 3.99 / 4.79 on 1..9).
- **lv-chordia feeding.** We write 22.05 kHz mono float32; the library reads it with `librosa.load(sr=22050)` (no resample) and
  checkpoints come from `<venv>/share/lv-chordia/cache_data` (torch 2.15 default `weights_only=True`). Output is identical at
  0, -20 and -30 dB (gain-invariant on the synthetic song). Pure noise and the drums-only stem give 100 % `N` (no hallucinated
  chords). Synthetic song: 26/26 chords, key A minor. Real no-chord shares 4.5 % (jeremy), 14.1 % (megafauna), 18.4 % (versatile),
  21.9 % (newton-vs-nye): inside the SPIKE band 4.5-22 %.
- **Licences in provenance.** `events/key.json` / `events/chords.json` record `skey_onnx` (weights non-commercial) and
  `lv_chordia_ismir2019_chordnet`; `events/mood.json` records both Essentia entries as CC-BY-NC-ND-4.0; `device: cpu`.
  Everything in M4 runs on CPU (onnxruntime CPU EP, torch CPU), so there is no ROCm divergence to check.

## Minor findings

### m1 `key_override` crashes on common spellings (human-correction hook)
- location: `src/mvh/stages/harmony/theory.py` `parse_key_label`; used by `core.analyse_key` for `harmony.key_override`.
- evidence: `parse_key_label("Am")` -> `ValueError: not enough values to unpack`; `"H minor"` -> `KeyError`; `"A dorian"` returns mode
  `dorian` (silently turned into minor by `key_index`). A user typing `Am` in the hook fails the whole stage.
- fix: accept `Am`, `A:min`, `A min`, `a`, `A`, `Bbm`, reject unknown modes with a clear `StageError` message.

### m2 Mood confidence is not gated on near-silent or non-music input
- location: `src/mvh/stages/mood/core.py` `silence_mask` (`SILENCE_DB = -70`), `_conf`.
- evidence (probe, global summary): white noise at -60 dBFS RMS -> arousal 0.418 with `arousal_conf` 0.794, tags
  relaxing/meditative/film; a pure 440 Hz sine -> `arousal_conf` 0.626, tags meditative/relaxing. Only digital silence (< -70 dBFS)
  gets confidence 0. A fade tail or room-tone gap therefore reads as a confident "calm" section.
- fix: scale the confidences by a level/tonality gate (e.g. 0 below about -50 dBFS RMS or 40 dB under the song's p95 RMS, ramping
  up over 10 dB), and lower them where the msd-musicnn top tag activations are all low.

### m3 Mood depends on playback gain; no reference level is applied before the heads
- location: `mood/__init__.py` `run` (feeds the mix as decoded), `frontend.log_mel` (`log10(1 + 10000 x)` is gain dependent).
- evidence: the synthetic song at -20 dB: valence 0.463 -> 0.408, arousal 0.387 -> 0.436 (arousal goes *up* when the song gets
  quieter), top tags `melodic, space, energetic` -> `melodic, happy, energetic`. The synthetic master is quiet (spectral warns of a
  quiet master), so the synthetic mood scores are not comparable with the real songs.
- fix: document it, or loudness-normalise to the heads' training level (commercial masters, about -14 to -9 LUFS integrated) before the
  front end, and record the applied gain in provenance.

### m4 A parallel-mode mixture is reported as a modulation (jeremy)
- location: `harmony/core.py` `analyse_key` (Viterbi with `RELATED_COST = 9` for parallel keys).
- evidence: jeremy -> global A minor conf 0.849, but `events/key.json` has two regions, A major 0-122 s (conf 0.425) and A minor
  122-316.6 s, plus `key:modulation`. bench-music §3 reads the song's A minor / A major alternation as one modal, blues-flavoured key.
  A video agent would cut a "key change" at 122 s that is not in the music.
- fix: treat a parallel key like a relative one for regions when the chord timeline keeps alternating the two tonic triads (or raise
  the parallel switch cost), and report mode mixture as a flag on one region.

### m5 lv-chordia weights licence is not a licence
- location: `models.lock.json` `lv_chordia_ismir2019_chordnet.licence` -> provenance `licence` = "MIT (code); weights from the
  ISMIR2019 LV chord repo".
- evidence: `events/chords.json` provenance carries that string; it names a source, not a licence. PLAN §1 requires every model's
  licence in run.json and provenance.
- fix (W3 integrator, models.lock is not M4-owned): record the weights' actual licence, or "unknown (no licence file upstream);
  personal use" explicitly.

### m6 The S-KEY note in `meta/key.json` states a wrong model property
- location: `harmony/core.py` `methods["skey"]["note"]` = "S-KEY probability is nearly flat (max ~0.07-0.1)".
- evidence: see major finding F1 (double softmax): the model's own probability is recoverable and is ~0.87 on a clean cadence.
  The note will mislead whoever reads the key file. Fixed together with F1.

### m7 Key confidence rule deviates from SPIKE §7 without saying so in the output
- location: `harmony/keys.py` `global_confidence` (cap at 0.5 only when S-KEY and the *chord* model disagree).
- evidence: bench-music §7 (adopted by SPIKE.md): high key confidence needs "window agreement >= 0.75 **and S-KEY = KS**, otherwise report
  two candidates". jeremy: S-KEY A minor, KS A major, S-KEY window agreement 0.763 -> the stage reports A minor with conf **0.849**
  (`agreement: parallel`). decisions/M4.md H8 documents the substitution of the chord model for KS, which is defensible, but
  `meta/key.json` gives a single confident key where the gate rule asks for two candidates.
- fix: apply the SPIKE cap (<= 0.5) whenever S-KEY and KS name different keys that are not relative, or record the rule change as an
  explicit SPIKE amendment in the W3 notes.

## Round 2 (r-ml-m4-r2)

Round-1 majors re-checked against the code, not only the tests: F1 (S-KEY double softmax) and F2 (chroma tuning unit) are
fixed for real (`keys.recover_probs` inverts the outer softmax exactly; `chroma._compute_chroma` passes `tuning * BPO / 12`).
F3 is fixed for digital silence (20 s / 60 s of zeros -> conf 0.25 + `key:no_tonal_evidence`) but not for noise: re-reported
as a major (`tests/review/M4/r-ml/test_key_gating_noise.py`). The F1 gate introduced a crash, reported as a blocker
(`tests/review/M4/r-ml/test_skey_gate_crash.py`). Real songs give the same global keys and confidences as in round 1
(jeremy A minor .836, megafauna D minor .50, versatile A minor .50, newton-vs-nye A minor .902; synth with fixture beats A minor .515).
Probe logs: `out/_wip/r-ml-m4-r2/`.

### m8 Stale "S-KEY is flat" claims remain
- location: `src/mvh/stages/harmony/__init__.py` module docstring ("the S-KEY softmax is flat"); `docs/SPIKE.md` line 51;
  `docs/spike/bench-music.md` §3 (line 98) and §7 table (line 160).
- evidence: the export is softmax(softmax(.)); recovered p_max on real songs is 0.37-0.87 (song level) and 0.13-0.96 per 30 s window
  (`out/_wip/r-ml-m4-r2/probe_pmax.log`). The stage docstring is M4-owned; SPIKE/bench-music are not and no change request asks for the amendment.
- fix: correct the docstring; add a W3 change request (CR-M4-3) to amend SPIKE.md / bench-music §3 and §7.

### m9 No unit tests for the round-1 fixes
- location: `tests/unit/harmony/test_keys.py`, `test_chroma.py`.
- evidence: nothing tests `recover_probs`, `skey_weight`, the `methods()` gate or the `key:no_tonal_evidence` cap (grep finds none);
  `test_chroma_survives_detuning` only checks top-3 membership at +-30 cents, which also passed with the one-third correction.
  The KeyError blocker would have been caught by a unit test of the gate with an unsure S-KEY.
- fix: unit-test `recover_probs` on a synthetic double softmax, the gate paths of `analyse_key` (S-KEY absent / unsure / sure), and the
  chord-tone share on a 45-cent detuned triad.

### m10 Recovered S-KEY p_max is not a tonality detector
- location: `harmony/keys.py` `skey_weight` (gate 0.2, full weight at 0.6).
- evidence: the synthetic drums-only stem gets S-KEY p_max 0.62 ("B minor"), i.e. full vote weight, while lv-chordia gives 100 % N.
  The stage ends at conf 0.404 with `key:low_confidence` only because the profiles disagree. p_max measures how sure the model is
  among keys, not whether there is tonal content.
- fix: also gate S-KEY on the chord model's no-chord share in the window (or on harmonic-to-percussive energy), and say so in the note.

### m11 S-KEY's p_max disappears from `meta/key.json` exactly when it matters
- location: `harmony/core.py` `analyse_key` (`methods` is built from `g.methods()`, which drops a gated S-KEY).
- evidence: when the song-level p_max is under 0.2 the `methods.skey` entry is absent (today it crashes instead: blocker B1). A reader
  cannot see that S-KEY ran and was gated.
- fix: when fixing B1, always write `methods.skey` when S-KEY ran (`p_max`, `windows`, `voted: false`).

## Round 3 (r-ml-m4-r3)

r2 findings re-checked against the code, not only the tests. B1 is fixed for real: `core.analyse_key` now writes
`methods.skey` whenever S-KEY ran (`methods.setdefault("skey", ...)` plus `voted`, `p_max`, `windows`), so a gated S-KEY no
longer crashes the stage and is visible in `meta/key.json` (this also closes m11). Real S-KEY on 60 s white noise: no crash,
`voted: false`, p_max 0.092. M1 is fixed for the cases it named: `keys.global_confidence` maps ks/temperley/albrecht to one
"profiles" source and caps conf at 0.25 with `key:no_tonal_evidence` when fewer than two sources have a winner (white, pink and
synth_noise give 0.25 + the flag). It is a general rule, not a test-specific hack. Real songs are unchanged against r2
(jeremy .836, megafauna .50, versatile .50, newton-vs-nye .902; synth A minor .515): no regression. Fast suite (unit harmony/mood
plus tests/review/M4, not real): 57 pass; the only failure is the new round-3 test. Probe logs: `out/_wip/r-ml-m4-r3/`.
Gate note: `scripts/gate.ps1 M4` stops at `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` because the rhythm
stage is no longer a stub (another module); that is not an M4 defect.

New major (failing test `tests/review/M4/r-ml/test_key_gating_band_noise.py`): the no-chord share is still not tonal evidence.
Band-limited noise with real lv-chordia (100 % N) and real S-KEY (p_max 0.41, votes) gives F minor conf 0.70-0.80 with no
low-confidence flag.

### m12 The no-tonal-evidence label fires on tonal a cappella input
- location: `harmony/keys.py` `global_confidence` (`len(sources) < 2`).
- evidence: the synthetic vocals-only stem, lv-chordia returning one N segment and no S-KEY (`out/_wip/r-ml-m4-r3/fast2.py`): the
  profiles alone name the right key but the stage writes `key:no_tonal_evidence`. The cap to 0.25 is fair (one source), but the
  label says the audio is atonal when it says "only one source" (with S-KEY present the same stem gets A minor .913).
- fix: emit `key:single_source` when there is chroma energy but only one source, and keep `key:no_tonal_evidence` for the
  masked-chroma / all-N-and-gated cases.

### m13 A single short spurious chord counts as a full independent source
- location: `harmony/keys.py` `global_confidence` (sources set) and `Evidence.methods()` (a chord vector counts once it has any spread).
- evidence: white noise, no S-KEY, lv returns N except one 2 s D:min (`out/_wip/r-ml-m4-r3/fast.py`): conf 0.882, no flags. Real
  lv-chordia gave 100 % N on every noise probe, so this did not reproduce with the real model; it is the same root cause as the
  round-3 major (no floor on the non-N share).
- fix: count `chords` (and `phrase`) as a source only when the non-N share in the span is above a floor (for example 25 %).

### m9 (still open) No unit tests for the gate paths
- evidence: `tests/unit/harmony` still has no test of `recover_probs`, `skey_weight`, the `methods()` gate, the `voted` flag or the
  `key:no_tonal_evidence` cap (grep finds none). Only the review tests cover them.

## Round 4 (r-ml-m4-r4)

R3-M1 (band-noise key) is FIXED, and the fix is general, not a test hack. `keys.global_confidence` now takes the lv-chordia
no-chord share of the span (`no_chord_share_in`). A share of 0.9 or more caps confidence at 0.3 and adds
`key:no_tonal_evidence` + `key:low_confidence`. Chords and phrase count as sources only when chords cover at least 25 % of the span.
`core.analyse_key` passes the share for the global key and for each region. Probe `out/_wip/r-ml-m4-r4/probe.log` (real S-KEY,
real lv-chordia): band noise at 200-500, 400-900 and 800-1600 Hz, brown noise and a riser are all capped at 0.3 or below and
flagged. All review tests pass (61 fast, 5 real), and so does m13 (one spurious chord no longer makes a source).
No regression on real mixes: jeremy, megafauna, versatile and newton-vs-nye give the same keys and confidences as the
integrator run, and the jeremy harmony re-run through `mvh analyze` is byte-identical to it (harmony is deterministic across
processes). Mood re-run on jeremy and newton-vs-nye reproduces the integrator's section values to within 5e-5 (rounding).

New major R4-M1 (regression from the R3-M1 fix, failing test `tests/review/M4/r-ml/test_key_gating_a_cappella.py`): the gate
reads lv-chordia's "no chord" as "no key". The synthetic song's lead-vocal stem (A minor) gives no-chord share 1.0, while S-KEY
(p_max 0.566, voted) and KS, Temperley and Albrecht all say A minor. It is now A minor at 0.30, flagged no_tonal_evidence; with the gate
disabled it is 0.97, unflagged. The median normalised chroma entropy separates the two cases: noise is 0.91-0.97 and this
vocal 0.71 (`out/_wip/r-ml-m4-r4/peaky.py`). On REAL separated lead-vocal stems the gate costs less, because S-KEY mostly does
not vote there (p_max 0.17-0.34) and the profiles split. The jeremy A-minor region drops from 0.83 to 0.30.

### m14 harmony `stage_version` was not bumped after a behaviour change
- location: `src/mvh/stages/harmony/__init__.py` (`StageSpec(... "1.0.1" ...)`).
- evidence: the R3-M1 fix changes key confidence and flags, but the cache key (`runner/run.py key_inputs`: version, params, models,
  upstream) does not change. Every song folder analysed before the fix, including the integrator's folders (05:10, fix 05:48),
  serves the pre-fix key as a cache hit unless `--force harmony` is passed.
- fix: bump harmony to 1.0.2 (and do so for any later change that alters the output).

### m15 The chord evidence keeps its full ensemble weight when chords cover only a small share
- location: `keys.ensemble` (`WEIGHTS["chords"]=1.0`, `phrase` 0.7); `CHORD_SOURCE_FLOOR` only affects the source count.
- evidence: a monophonic Eb-major melody (probe `melody_Ebmaj`, real models). lv-chordia gives no-chord share 0.875, and the
  remaining 12.5 % (Bb:maj, D:maj, C:maj) makes the chord and phrase evidence point at Bb major. That outvotes S-KEY and all three profiles (Eb major), so the global key is
  "Bb major" at 0.228 (flagged low_confidence and models_disagree, so the error is visible).
- fix: scale the chord and phrase weights by the chord-covered share (for example `min(1, covered/0.5)`).

### m16 A region shorter than one key window gets a confidence with no window support
- location: `core.analyse_key` (region branch): `inside` is empty when the region is shorter than `key_window_s`, and
  `global_confidence` then uses the method credit as the window agreement.
- evidence: megafauna (integrator beats): region 73.5-91.6 s "D major" conf 0.97, which is 18.1 s, below `key_min_region_s` = 20
  after the boundaries are snapped to downbeats. The chords there are D:maj (17.6 s), so the label is plausible, but 0.97 is not supported by the 30 s windows. Same output as the integrator's
  pre-fix run, so this is not a regression.
- fix: when no window lies inside the region, use the overlapping windows weighted by overlap, or cap the region's confidence (for example at 0.7). Re-apply the minimum length after snapping.

### m17 An overridden key keeps the evidence flags that the override contradicts
- location: `core.analyse_key` (`flags += cinfo["flags"]` before `if forced: conf = 1.0`).
- evidence: band noise with `key_override="C major"` gives conf 1.0 together with `key:low_confidence` and `key:no_tonal_evidence`
  (`out/_wip/r-ml-m4-r4/override_check.py`).
- fix: when the key is overridden, drop the confidence flags (keep `key:overridden`; keep the model opinion in `methods`).

### m18 The M4 decisions file does not describe the new gate
- `docs/contract/decisions/M4.md` still documents only the "< 2 sources -> 0.25" cap. Add the no-chord-share gate
  (0.9 -> 0.3 + flags) and the 25 % chord-source floor, which are additive behaviour behind the `key:no_tonal_evidence` flag.

### m9 (still partly open) unit tests
- `tests/unit/harmony/test_key_no_chord_gate.py` now covers the gate. There is still no unit test of `recover_probs`, `skey_weight`
  or the `voted` flag. There is also no `tests/integration/M4/` (the W3 integration tests exist for M1, M2, M3a, M3b, M5 and RUNTIME).

m12 is superseded by R4-M1. m13 is fixed.

## Round 5 (r-ml-m4-r5)

R4-M1 (a-cappella key labelled atonal) is FIXED for the case it was filed on, and the fix is general code, not a test
hack. `keys.global_confidence` exempts chord-less spans from the no-chord gate when the three profiles agree (exact or
relative) with a mean top correlation >= `TONAL_PEAK` 0.55 and S-KEY votes for the winner (`key:chroma_only`). The synthetic
lead-vocal stem gives A minor 0.67 (real models) and the round-4 tests pass. Five of six transpositions of that stem keep
their key (0.66-0.97). Band noise, brown noise, a riser, TTS speech, a pure sine and single square/saw notes stay gated
(`out/_wip/r-ml-m4-r5/probe5.log`). Real mixes are unchanged: jeremy, megafauna, versatile and newton-vs-nye give the
integrator's keys, regions and confidences through `core.analyse` with the integrator's beats (`probe_real.log`). The
jeremy lead-vocal A-minor region is back to 0.83. Mood re-run on jeremy and megafauna reproduces the integrator's section
values to within 5e-5 and gives the same tags (`mood_check.log`). An end-to-end `mvh analyze --only harmony` on copies of
the integrator folders does not run, because rhythm is stale after the W3 M2 fixes (an upstream change, not M4).

Two new majors with failing tests:
- R5-M1 (`tests/review/M4/r-ml/test_key_gating_atonal_line.py`): a random 12-tone line gets "C minor" at 0.67 with no low-confidence flag.
- R5-M2 (`tests/review/M4/r-ml/test_key_gating_a_cappella_fifth.py`): when S-KEY lands on the fifth, the a-cappella stem is labelled atonal again.

The root cause of both: the carve-out measures tonality with a Pearson correlation, which cannot see how flat the chroma is,
and requires S-KEY to agree exactly.

### m19 A chroma-only key can reach the full 0.97 confidence
- location: `keys.global_confidence` (`tonal_without_chords` branch: no ceiling).
- evidence: vocals_shift-3 and -2 give 0.97, and -5 gives 0.96, with `key:chroma_only` (probe6.log). That is the same ceiling
  as a full mix where the chord model also agrees, although the only sources are S-KEY and one chroma read by three profiles.
- fix: cap the carve-out at about 0.8, as round 4 suggested.

### m20 The relative key is not flagged on a chroma-only key
- evidence: a sung D-major line (sung_sine, no chords; probe5 `sung_Dmaj`) gives "B minor" at 0.78 with only `key:chroma_only`.
  All four methods say B minor. A single line has no harmony to fix the tonic, so the relative key is always a live
  alternative, but no `key:relative_ambiguity` is emitted. The input is synthetic and its melody dwells on B, so this is a hint only.
- fix: add `key:relative_ambiguity` (or list the relative key first in `alternatives`) whenever `key:chroma_only` fires.

### m18 / m14 / m17 still open
- m18: `docs/contract/decisions/M4.md` still documents only the "< 2 sources -> 0.25" cap. It does not describe the no-chord gate, the 25 %
  chord-source floor, `TONAL_PEAK`, or the new `key:chroma_only` flag.
- m14: harmony `stage_version` is still "1.0.1" after two behaviour changes (R3-M1 and R4-M1), so cached song folders keep the old key.
- m17: unchanged code (`flags += cinfo["flags"]` before `if forced: conf = 1.0`), so an overridden key still carries contradicting flags.
- m9: there is still no `tests/integration/M4/`.
