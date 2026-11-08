# M2 Rhythm: R-DSP review, minor findings (r-dsp-m2)

Reviewer r-dsp-m2 (PLAN §11, lens R-DSP). The blocker and major findings have failing tests under
`tests/review/M2/r-dsp/` and are listed in `docs/build/reports/r-dsp-m2.md`. This file lists the **minor** findings.
Every claim below was checked by running code. The probe scripts are in `out/_wip/r-dsp-m2/probes/` and are not
committed. No real-song lyric text was read or printed.

## What holds up (measured)

- **Synthetic song, full `mvh analyze`** (real upstream stages):
  - rhythm: beat F1 1.00 (±70 ms), downbeat F 1.00, tempo error 0.033 BPM, median beat error 1.25 ms;
  - the pickup is found (bar 0, beat_in_bar 4, at 0.498 s);
  - the 3/4 bar 16 is found, with meter changes at 31.0 and 32.5 s.
- **Click tracks with the models** (60, 75, 100, 160, 180, 200 BPM, swing, 48 kHz): beat F1 ≥ 0.992 and tempo error
  ≤ 0.21 BPM.
- **A musical 3/4 piece** (kick and bass on 1, hats on 2 and 3, a chord per bar) at 100 and 150 BPM gives 3/4 with
  downbeat F 1.00. The 4/4 version gives 4/4.
- **Real songs** (W0 tracker outputs replayed). Tempi are 105.13 (MEGAFAUNA, with alternatives 139.9 and 209.7
  recorded and the `tempo_trackers_disagree` flag), 130.25, 107.15 and 137.98 BPM. madmom's one-beat downbeat
  offset is flagged on versatile and newton-vs-nye, as SPIKE predicts. In-pulse inter-beat intervals deviate more
  than 10 % from the local median on at most 2 beats per song.
- **structure, choreo and cues with the exact (truth) upstream** reproduce the truth exactly. That covers sections,
  phrases, EDM roles, eight-counts including E000 and the partial counts, and grooves with their swing and
  syncopation (all bars except the outro bars 26 and 27). This result is partly circular; see major F4.

## Minor findings

### m1. Beat snapping lands on the low-band body of a kick, 13-18 ms after the attack
- **Location:** `src/mvh/stages/rhythm/fusion.py` (`transients`, `snap_beats`).
- **Claim:**
  - `transients()` merges broadband transients with transients from a 200 Hz low-pass band. A kick produces a second,
    later low-band "transient" about 13-18 ms after its attack, with a rise of 15.8-17.8 dB.
  - The snap accepts only transients with a rise of at least 15 dB. The broadband attack usually rises less than
    that (for example 11.9 dB at 50.5 s), so the beat snaps to the later low-band transient.
- **Evidence:**
  - On the synthetic song the beats at 7.0, 16.0 and 50.5 s are +18.0, +16.5 and +18.2 ms late, and the p95 error is
    15.7 ms (the median is 1.25 ms).
  - At 50.5 s the eligible transients are +6.2 ms (broadband, 11.9 dB) and +18.2 ms (low-band, 15.8 dB). That is a
    whole 60 fps frame late on a kick.
- **Suggested fix:** take the earliest transient in a cluster within about 25 ms (the attack), or snap only to
  broadband transients and use the low band only as a fallback. Also report the time where the energy rise starts,
  not its steepest point. The steepest point also gives a bias of about −2 ms on clicks.

### m2. In the DSP-only fallback, a single weak estimator gets full consensus, so fast click tracks are halved
- **Location:** `fusion.arbitrate_tempo` (`cons` is normalised by `wsum` of the estimators that are present).
- **Claim:** when beat_this, madmom and allin1 are all missing (`rhythm:dsp_only`), librosa's estimate alone has
  weight 0.5 but receives consensus 1.0. Metrical evidence cannot outvote it.
- **Evidence:** with `use_models=False`, click tracks at 160, 180 and 200 BPM come out at 79.97, 90.02 and 100.06 BPM.
  That is a tempo error of 80-100 BPM against the §7 limit of 0.5. The builder's DSP tests cover only 90-140 BPM.
  With the models the same tracks are correct.
- **Suggested fix:** normalise consensus by the nominal weight of all trackers (3.5), or cap it when only one
  estimator is present. Add DSP tests at 160-200 BPM.

### m3. Kick and metrical evidence barely affects the tempo octave on the case SPIKE names
- **Location:** `fusion.metrical_evidence` and `arbitrate_tempo`.
- **Claim:** SPIKE asks for the tempo octave to be arbitrated "against kick evidence". On MEGAFAUNA the metrical
  score is nearly flat across the candidates (0.11-0.26).
- **Evidence:**
  - The metrical score ranks 105 BPM (0.159) *below* 69.96 BPM (0.257) and 84.0 BPM (0.221). The choice of 105 comes
    from consensus (allin1 and librosa, 0.43), salience (1.0) and the prior.
  - This is acceptable because the alternatives are recorded and `override_hint` offers them. But
    `arbitration.rows[].parts` shows that the kick term did not decide.
- **Suggested fix:**
  - Measure kick-on-beat coverage per candidate using the spectral stage's `hits.kick` events, not mixed kick and
    snare flux.
  - State in `meta/tempo.json` which term decided.

### m4. Small arbitration-output problems
- **Location:** `rhythm/__init__.py` and `fusion.arbitrate_tempo`.
- **Claim and evidence:**
  - **Duplicate rows.** On MEGAFAUNA `arbitration.rows` holds the 162.162 BPM row twice. Candidates are de-duplicated
    on the raw value and then refined to the same value.
  - **Unused parameter.** The param `tempo_ratios` is declared, and so is part of the cache key, but it is never used.
    Candidates are only ×1, ×2 and ×½ of the estimates plus the tempogram peaks.
  - **Undeclared parameter.** choreo reads `groove_similarity_noisy`, which is not declared in `params`.
- **Suggested fix:**
  - De-duplicate after the refinement.
  - Use `tempo_ratios` to generate candidates, or drop the param.
  - Declare `groove_similarity_noisy`.

### m5. A beat at the start of a stop or silence is still in_pulse, and so is the outro decay
- **Location:** `fusion.pulse_flags` and `regularize_grid`.
- **Evidence:**
  - On the synthetic song (full analyze) the beat at 32.496 s, where the digital silence of bar 17 starts, is
    `in_pulse: true`, and the pulse region runs to 33.0 s. The truth has no pulse from 32.5 s.
  - The beats at 54.50, 54.98 and 55.48 s (the outro decay; truth has no pulse from 54.5 s) are also in pulse.
  - pulse_agreement is 0.964.
- **Why it matters:** an agent using `rhythm.in_pulse` keeps dancing for half a beat into the stop.
- **Suggested fix:** decide the in_pulse flag of a beat from the activation and level *after* the beat (the span it
  owns), not only from the ±2-beat median at the beat.

### m6. A spurious meter change in the trailing virtual bars
- **Location:** `fusion.decode_meter` and `build_bars`; `meta/tempo.json` `meter.changes`.
- **Evidence:** the 100 BPM musical waltz (24 bars of 3/4) reports a change to 4/4 at bar 25 (43.7 s). That bar is
  the virtual tail after the music ends.
- **Suggested fix:** virtual (no-pulse) bars should inherit the meter of the preceding pulse bar, and `meter.changes`
  should list only changes between in-pulse bars.

### m7. allin1 embeddings are offset 45 ms from their declared timebase
- **Location:** `src/mvh/stages/allin1/__init__.py` (`pool_embeddings`).
- **Claim:** pooled block k averages 100 Hz frames 10k..10k+9, so it is centred at k/10 + 0.045 s. The declared
  `rate_hz: 10` implies k/10 under the CONTRACT §2 centre rule.
- **Suggested fix:** centre the pooling window on frames 10k−5 .. 10k+4, or record the offset in `allin1.json`.
  structure pools by bar, so the effect today is small.

### m8. Group-majority labels overwrite confident per-section allin1 labels on loop-based songs
- **Location:** `structure/__init__.py`, label assignment (`lab = max(agg)` when a repeat group has several members)
  and `grouping()` (tau floor 0.5).
- **Evidence (newton-vs-nye replay):**
  - allin1 labels 55.7 s and 94.0 s as chorus (the sections' own label probabilities are 0.71 and 0.47 for chorus).
    Both are grouped with verses in repeat group B and relabelled `verse`.
  - The intro at 0.1 s (intro 0.45) becomes `verse#1`. The result is ten `verse` sections in a row.
  - On jeremy, 203.1 s (allin1 chorus) becomes `verse`.
  - There is no ground truth here, so this is minor. It is the same mechanism as major F4 (repeat groups that do not
    follow the musical function).
- **Suggested fix:**
  - Keep a section's own label when its probability is at least about 0.5 and differs from the group's label, and
    split the group instead.
  - Base the repeat threshold on the song's own similarity distribution, not a fixed floor of 0.5.

### m9. Test-coverage gaps
- **Location:** `tests/unit/rhythm`, `tests/unit/structure`.
- **Gaps:**
  - No test runs rhythm on short inputs (see F2), on a full 3/4 piece (only one 3/4 bar), or on DSP tempi above
    140 BPM.
  - The structure tests use the truth-derived allin1 intermediate (see F4).
  - `test_overrides_bpm_offset_phase` checks `rhythm.beat_offset_s` only on the DSP path, where no tracker downbeats
    vote. I checked the model-free vote path with offsets of 0.03-0.15 s: downbeat F stays 1.00, so there is no
    finding.
- **Suggested fix:** add `p_waltz.py`-style musical 3/4 and 6/8 fixtures, and run the structure tests with the
  recorded real allin1 output (`tests/review/M2/r-dsp/data/synth_real_allin1.npz`).

## Round 2 (r-dsp-m2-r2)

Reviewer r-dsp-m2-r2 checked the fixer's changes for F1-F5 and looked for regressions. Probes are in
`out/_wip/r-dsp-m2-r2/probes/` (not committed). Runs:
- real-song replays (W0 tracker outputs, the same as round 1) for all four songs;
- a full `mvh analyze` of the synthetic song (the round-1 song folder re-run `--from rhythm`);
- edge cases on the DSP and the model paths.
No real-song lyric text was read or printed.

### Status of the round-1 majors

| id | status | evidence |
|----|--------|----------|
| F1 pinned cue | **fixed** | The pin leads the merged cue (`kind: pinned`, strength 1.0, tier 1) and is in moments.json. Only tier-4 cues are nulled. |
| F2 short inputs | **fixed for inputs of 1 s and longer** | `smooth_same` gives the same output as `np.convolve(..., 'same')` (checked for kernels of 1-441 samples). Click tracks of 1-7 s, 2-20 s silence, noise and a sine pass rhythm, structure, choreo and cues, on both paths. For the remaining crash below 0.68 s, see r2-m1. |
| F3 sections < 2 bars | **fixed** | segment_dp no longer emits a short first section. None of the four songs has a non-silence section shorter than 2 bars. For a side effect, see r2-m2. |
| F4 structure circular / real allin1 | **NOT fixed** | See the new major below. |
| F5 downbeat vote | **fixed** | versatile: no 3-beat bar and no meter change. allin1 downbeat F against the fused bars rises from 0.844 to 0.907. The other songs give the same bars as round 1. The synthetic song's downbeat F is still 1.00. For a reservation, see r2-m4. |

### Major (failing test): F4 is still open with realistic upstream
`tests/review/M2/r-dsp/test_structure_real_upstream.py` (data: `data/synth_real_harmony_dynamics.npz`).
- **Why the round-1 test passes.** It swapped in the real allin1 but kept the fixture's dynamics and harmony. The
  fixture's `events/dynamics.json` segments start exactly at the truth sections, which is a second circular input.
- **Real harmony chroma alone:** chorus#1 at 17.0 s is missed, F 0.909. The two choruses are not in one repeat group.
- **Real harmony and real dynamics** (equal to the full pipeline): sections at 1.0, 5.0, 9.0, 25.0, 34.5, 42.5 and
  52.5 s, F 0.615. Round 1 scored 0.667.
- **Full `mvh analyze` after the fix:** the same 0.615.

### Minor findings, round 2

**r2-m1. tempogram_peaks still crashes on non-silent inputs shorter than 0.68 s** (residual of F2)
- **Location:** `fusion.py:147`.
- **Cause:** when the song is shorter than the 8 s window, the autocorrelation `irfft(..., 2*len(seg))` has
  `2*len(seg)` lags. The accumulator has `lag_hi + 2 = 136`.
- **Evidence:** a 0.6 s click track raises
  `ValueError: operands could not be broadcast together with shapes (136,) (120,)` on both the DSP and the model
  paths. A 0.3 s clip passes only because it is silent.
- **Suggested fix:** zero-pad the FFT to at least `lag_hi + 2`, or skip windows shorter than `lag_hi`.

**r2-m2. The absorbed intro bar moves the phrase and eight-count grid by one bar**
- **Location:** structure phrases, F3 side effect.
- **Before the fix:** jeremy and megafauna had a 1-bar S01 before an 8-bar intro. The odd bar sat at the start, like a
  pickup bar, and the counts started on the strong boundary (jeremy 3.0 s, megafauna 3.5 s).
- **After the fix:** the 9-bar intro starts its phrase grid on the odd bar.
  - jeremy: P01 runs 0.5 s for 8 bars, then a 1-bar P02 at 19.5 s. The counts are E001 0.5, E002 5.7, E003 10.9,
    E004 15.7 (partial, 6 beats) and E005 19.5 (partial, 4 beats).
  - megafauna: there is a 1-bar phrase at 17.3 s.
  - In both songs every count of the intro is one bar off the round-1 grid.
- **Note:** there is no ground truth for these songs. allin1 has no boundary at 3.0 s. But a choreographer expects the
  odd bar at the start.
- **Suggested fix:** when the DP's best path had a strong boundary within the first `min_len` bars, keep it as a phrase
  boundary inside the merged section, so that the partial phrase comes first.

**r2-m3. The melodic fingerprint over-groups, and group-majority labels make it visible** (worse than round-1 m8)
- **Cause:** section similarity is `max(main, melody)`, and the melody residual is cosine-normalised, so even small
  residuals count fully.
- **Synthetic song (real allin1, exact rest):** intro and verse fall into one group, A and A (truth: A and B).
  - With `melody_residual` monkeypatched to noise, they become A and B.
- **newton-vs-nye:** the two allin1 chorus sections (121.8 and 135.7 s, group F `chorus` in round 1) join verse group
  B. 12 of the 14 sections are now `verse`.
- **versatile:** 29.5 s and 144.0 s (round 1: `inst`, group B) are grouped with the outro sections and labelled
  `outro`. The 29.5 s section is the 3rd of 18 sections.
- **jeremy:** 158.3 s `bridge` becomes `verse`.
- **Suggested fix:** let the melody term count only when the residual energy is above a floor, combine the two terms
  with weights instead of `max`, and do not give `intro`/`outro` labels to sections in the middle of the song.

**r2-m4. The F5 phase correction is measured against the first-pass fused decode, not leave-one-out**
- **The issue:** the first pass includes the corrected tracker's own votes. Its reference is therefore partly itself.
  Also, a shift is applied to the whole song as soon as `f_best > f + 0.2`. A tracker that is off in 60-70 % of the
  song and right in the rest has its correct votes rotated too.
- **No harm found yet:** the four real songs and the synthetic song are unchanged or better.
- **Spurious flag:** noise (20 s, models) still raises `downbeat_phase_off:madmom:-1`.
- **Suggested fix:** compare each tracker with the decode of the other trackers, and allow the shift per region (for
  example per tempo segment).

**r2-m5. A pin is snapped to the nearest beat within 50 ms, and the user's own time is not kept**
- **Location:** `cues.on_grid`.
- **Evidence:** a pin at 20.51 s comes out at 20.5 s. A pin 40 ms off the beat (for example, on a vocal onset) is moved
  by 2.4 frames at 60 fps.
- **Suggested fix:** keep the pin's `t`, or record the original time in the moment description or in provenance.

**r2-m6. Exceptions to the 2-bar rule are recorded only in M2 decisions**
- **The issue:** forced short pieces and a short tail may be shorter than 2 bars (M2-D-minbars). The frozen catalogue
  text still says that segments shorter than 2 bars are merged.
- **Suggested fix:** add a change request for the W3 integrator to amend the text.

**r2-m7. Test coverage**
- tests/unit/{rhythm,structure,choreo,cues} are unchanged since round 1.
- There is still no unit test for short inputs.
- The structure unit tests still score against two truth-derived inputs: the fixture allin1 segments and the fixture
  dynamics segments.
