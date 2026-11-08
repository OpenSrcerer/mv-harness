# r-ml-m4-r2: R-ML review of M4 (harmony, mood), round 2

Verdict: **fail** (one new blocker introduced by the F1 fix, F3 only half fixed).

## Round-1 findings
| id | status | how verified |
|---|---|---|
| F1 S-KEY double softmax | **fixed** | `keys.recover_probs` inverts the outer softmax (exact algebra, not a test hack); r1 tests pass; real-song recovered p_max per 30 s window 0.13-0.96 (`out/_wip/r-ml-m4-r2/probe_pmax.log`); `methods.skey.note` corrected. The gate it added crashes the stage (B1). |
| F2 chroma tuning unit | **fixed** | `librosa.cqt(..., tuning=tuning * BPO / 12)`; r1 test passes (chord-tone share restored). |
| F3 lone-method confidence | **partly fixed** | Digital silence 20/60 s -> conf 0.25 + `key:no_tonal_evidence` (probe_synth.log). White noise with S-KEY absent/gated -> D minor conf 0.609, no flag: the cap counts KS/Temperley/Albrecht (one chroma) as three independent methods. Re-reported as M1. |

All 4 round-1 tests pass (`out/_wip/r-ml-m4-r2/review_tests.log`); fast unit tests of harmony pass (42).

## New findings
- **B1 (blocker)** `harmony/core.py:193` `KeyError: 'skey'` whenever the song-level S-KEY p_max (mean of window + whole-song recovered
  probabilities) is under 0.2: `g.methods()` drops the gated S-KEY but `analyse_key` still indexes `methods["skey"]`. Hit with the real
  model on 60 s white noise, 60 s pink noise and the r1 `synth_noise` signal; the four real songs stay above (lowest: megafauna 0.366,
  with individual windows at 0.133). Any noise/ambient/atonal piece or one S-KEY reads as several keys kills the stage.
  Test: `tests/review/M4/r-ml/test_skey_gate_crash.py` (fast stub test + real white-noise test; both fail with the KeyError).
- **M1 (major, F3 reopened)** `keys.global_confidence`: `len(winners) < 2` counts the three chroma profiles as independent.
  Test: `tests/review/M4/r-ml/test_key_gating_noise.py` (fails: conf 0.609, flags []).
- Minors m8-m11 in `docs/review/M4-r-ml.md` (Round 2): stale "flat" claims (stage docstring, SPIKE, bench-music); no unit tests for the
  fixes (the existing detuning unit test passes even with the old bug, verified by `out/_wip/r-ml-m4-r2/old_tuning_check.py`);
  S-KEY p_max 0.62 on a drums-only stem (not a tonality gate); `methods.skey` vanishes when gated.

## Regressions checked and absent
Real-song global keys/confidences identical to round 1 (jeremy A minor .836 vs .849, megafauna D minor .50, versatile A minor .50,
newton-vs-nye A minor .902); synth (fixture beats) A minor .515; synthetic cadences A minor / Eb major conf .97 with p_max .86/.89.
Mood code unchanged since round 1 (mtime 16:40), not re-reviewed beyond that.

## Probes (all under out/_wip/r-ml-m4-r2/)
probe.py (`synthetic`, `synthfx`, `<slug>`), probe_noskey.py, probe_pmax.py, old_tuning_check.py, summ.py; logs *.log.
