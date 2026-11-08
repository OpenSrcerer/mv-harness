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
