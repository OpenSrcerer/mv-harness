# r-ml-m4: R-ML review of M4 Harmony & mood (harmony, mood)

Independent reviewer (PLAN §11, lens R-ML). Findings were formed from the spec, the code and runs before the builder's report was
opened (it was only grepped at the end to check whether these points were already known: they were not).

**Verdict: pass-with-fixes.** 3 majors (failing tests under `tests/review/M4/r-ml/`), 7 minors (`docs/review/M4-r-ml.md`), no blockers.
Pre-processing for lv-chordia and the Essentia heads is right, the 24-key S-KEY label map is right, chords on the synthetic song are
26/26 and gain-invariant, the real no-chord shares sit inside the SPIKE band, and the licences reach provenance. The majors are one
model post-processing error (S-KEY double softmax), one DSP unit error in the chroma (tuning applied at one third), and one gating
gap (a confident key from digital silence).

## What was run (nothing printed lyric text)

| Run | Command / script | Result |
|---|---|---|
| S-KEY on synthetic cadences, 24 keys | scratchpad `skey_probe.py` (heavy slot) | 24/24 exact; max exported prob 0.093-0.096 on every clean cadence |
| S-KEY double-softmax check | same | recovered p = log q - mean(log q) + 1/24 sums to 1.000, in [0.0045, 0.87]; cadence 0.87, white noise 0.13, near-silent impulses 0.51 ("G# minor") |
| Essentia mel front end vs librosa Slaney | scratchpad `melcheck.py` | filterbank diff 2e-9, log-mel diff 6e-7 |
| harmony `core.analyse` with real S-KEY + lv-chordia | scratchpad `probe_h.py` -> `out/_wip/r-ml-m4/probe_h.log`, `probe/*.json` | see below |
| mood heads on synth / degenerate / real | scratchpad `probe_m.py` -> `out/_wip/r-ml-m4/probe_m.log` | see below |
| short and silent inputs | scratchpad `edge.py` -> `out/_wip/r-ml-m4/edge.log` | 0.5 s, 5 s, 10 s run; digital silence -> key "C minor" conf 0.75 |
| chroma tuning | scratchpad `tuning.py`, `tuning2.py` | see F2 |
| `mvh analyze --only harmony,mood --force harmony,mood` on a copy of the builder's synth folder | `out/_wip/r-ml-m4/run.ps1` -> `out/_wip/r-ml-m4/synth` | harmony ok in 60 s (incl. slot wait); mood stayed pending (structure not cached in that copy); provenance checked on events/key.json, chords.json |

Harmony results (key, conf, agreement, no-chord share, mean chord conf):
synth A minor 0.515 relative 5.3 % 0.965 (26/26 chords, identical at -20 and -30 dB);
megafauna D minor 0.50 fifth 14.1 %; versatile A minor 0.50 fifth 18.4 %; jeremy A minor 0.849 parallel 4.5 % (two regions: A major
0-122 s, A minor 122-316.6 s); newton-vs-nye A minor 0.902 fifth 21.9 %. Noise -> Eb minor 0.289 low_confidence, 100 % N; synth drums
stem -> C minor 0.173, 100 % N; synth vocals stem -> A minor 0.929 (melody-only, plausible).

Mood (0..1, global): megafauna V .468 A .445 (emoMusic .374/.474 = bench-music 3.98/4.82 on 1..9), versatile .508/.529,
jeremy .530/.622, newton-vs-nye .522/.611; valence_conf .087-.327, arousal_conf .361-.602. Noise -> conf .05 (heads disagree);
-60 dBFS noise -> arousal_conf .794 (minor m2); digital silence -> conf 0 (correct).

## Major findings (each has a failing test)

### F1 (major) S-KEY output is a double softmax; the stage throws away the model's calibrated probability
- location: `src/mvh/stages/harmony/keys.py` `SKey.log_scores`, `skey_log`, `global_confidence`; `core.py` `methods.skey.note`.
- claim: the pinned ONNX export ends in softmax(softmax(logits)); the "flat probability" is an export artefact, not a model property.
- evidence: the exported probs are bounded by e/(e+23) = 0.106 for any input. Inverting the outer softmax
  (p = log q - mean(log q) + 1/24) gives a distribution that sums to 1 and lies in [0, 1]: 0.87 on a clean cadence, 0.13 on white
  noise, 0.51 on near-silent impulses. The stage z-scores log q (= p + const), so ranking survives, but the S-KEY vote has full weight
  (z clipped at 3) whether S-KEY is 87 % sure or guessing, and `meta/key.json` tells readers the model is flat. Test run: exported max
  0.094 on the cadence; tonal-minus-noise gap 0.047.
- suggested_fix: in `SKey.log_scores` recover p (`lq = np.log(q); p = lq - lq.mean() + 1/24; p = clip(p, 0, 1) / sum`), return p as the
  probability and log p as the score; weight the S-KEY evidence by its p_max (or entropy) and use p_max as one confidence term and as a gate
  (ignore windows with p_max below ~0.2); fix the note. SPIKE.md/bench-music §3/§7 should be amended ("S-KEY softmax flat" is wrong).
- test: `tests/review/M4/r-ml/test_skey_output.py` (2 tests).

### F2 (major) Chroma tuning correction is applied in the wrong unit (one third of the estimated offset)
- location: `src/mvh/stages/harmony/chroma.py` `_compute_chroma`: `estimate_tuning(..., bins_per_octave=12)` returns semitone fractions,
  passed to `librosa.cqt(..., bins_per_octave=36, tuning=tuning)`, which applies `fmin * 2**(tuning / 36)`.
- evidence: A minor triad 45 cents sharp: tuning estimate 0.45 (right), chord-tone share of the chroma 0.734 vs 0.868 in tune; with
  `tuning * 36 / 12` it is 0.870. The real song jeremy is estimated at +0.28 semitones (its chords.json provenance note), so ~19 cents stay
  uncorrected on a test song. Affects `curves/chroma12.f32`, the three profile methods, the template check, chord `conf` and `bass_pc`.
- suggested_fix: `tuning=tuning * BPO / 12` (or estimate with `bins_per_octave=BPO`), plus a unit test on a detuned triad.
- test: `tests/review/M4/r-ml/test_chroma_tuning.py`.

### F3 (major) Digital silence gets a confident key; a single method counts as full agreement
- location: `keys.py` `global_confidence` (credit and window agreement computed over whatever methods are present), `SKey.log_scores`
  (peak-normalises silence/noise to full scale), `core.analyse_key`.
- evidence: 20 s of zeros -> `meta/key.json` global "C minor", conf 0.75, no `key:low_confidence` flag (out/_wip/r-ml-m4/edge.log). Only
  S-KEY has a non-constant vector (all chroma evidence is masked), so it agrees with itself: window agreement 1, method credit 1. The same
  confidence formula gives 0.97 to a 0.5 s input. A -60 dBFS noise tail after tonal music did *not* create a spurious region (checked).
- suggested_fix: require at least two independent non-anchor methods (or a minimum amount of unmasked harmonic energy / duration) before
  confidence can exceed ~0.3; gate S-KEY with its recovered p (F1) and skip windows whose RMS is far below the song's; flag
  `key:no_tonal_evidence`.
- test: `tests/review/M4/r-ml/test_key_gating.py`.

## Minor findings (details in docs/review/M4-r-ml.md)
m1 `key_override` crashes on "Am"/"H minor" and accepts "A dorian"; m2 mood confidence not gated on near-silent/non-music input
(-60 dBFS noise -> arousal_conf 0.79); m3 mood depends on playback gain (synth at -20 dB changes arousal and tags); m4 jeremy's A minor /
A major mixture is emitted as a modulation at 122 s; m5 lv-chordia weights licence string is not a licence; m6 the S-KEY note in
meta/key.json is wrong (F1); m7 the key confidence cap uses S-KEY vs chords instead of SPIKE §7's S-KEY vs KS (jeremy conf 0.849 with
S-KEY != KS).

## Change requests
- None for M4's env or contract. The F1 fix should come with a SPIKE.md/bench-music amendment (orchestrator) and m5 needs a
  `models.lock.json` licence update (W3 integrator).

## Files
- tests: `tests/review/M4/r-ml/{conftest.py, m4rml_signals.py, test_skey_output.py, test_chroma_tuning.py, test_key_gating.py}`
  (S-KEY tests take a heavy slot; the tuning test is pure DSP).
- minors: `docs/review/M4-r-ml.md`; progress: `docs/build/progress/r-ml-m4.md`; probe outputs: `out/_wip/r-ml-m4/`.
