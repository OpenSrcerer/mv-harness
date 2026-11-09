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

## Round 3 (r-dsp-m2-r3)

Scope: verify the fixer's F4-r2 change to `structure` (drum-pattern and embedding novelty, edge damping, gated dynamics
evidence, phrase-grid refinement, agglomerative repeat groups), then look for regressions. Probes are in
out/_wip/r-dsp-m2-r3/probes (p_sens, p_full, p_jitter, p_pattern, p_loop, p_mega, replay/cmp_*).

### Status of F4-r2
- With the fixture's rhythm the fix holds and is not a one-parameter hack. F stays 1.0 and the choruses stay in group C
  across split_min_novelty 0.45-0.6, w_pattern 0.5-0.9, w_embedding 0.3-0.7, dyn_gate 0.5-1.0, section_cost_q 70-80 and
  repeat_adjacent_penalty 0.8-0.9 (p_sens.log). The 17.0 s boundary comes only from the phrase-grid refinement.
- The real pipeline is still not right. A fresh full `mvh analyze` of the synthetic song gives 0.99/5.0/9.0/17.0/25.0/34.5/50.52 s,
  which is F 0.923 with a spurious 2+2 intro split. The only input that causes this is the real rhythm: two downbeats are
  18 ms late, while beats F1 is 1.0. The review test passes only because it uses the fixture rhythm, which is the truth rhythm
  (a third circular input). This is the new major F4-r3, test tests/review/M2/r-dsp/test_structure_rhythm_jitter.py.
- A new major regression on MEGAFAUNA: the drop is shortened from 141.8-212.7 s to 141.8-176.1 s, against the SPIKE loud
  plateau of 146-217 s. This is F6-r3, test tests/review/M2/r-dsp/test_structure_drop_extent_real.py (-m real).

### Minor findings, round 3

**r3-m1. The phrase-grid refinement splits a loop that never changes**
- **Location:** `structure.run`, refinement block.
- **Cause:** `split_min_novelty` is compared with `norm01(foote(S_hom, 4))`. That value is normalised to the song's own
  p98, not to "the in-section level" that the docstring describes. On a song without real changes, noise is scaled up
  to 1.0.
- **Evidence:** a 32-bar uniform 120 BPM loop (kick, hat, the same 4 saw chords; p_loop.py) goes from 6 sections
  (refinement off) to 9. Every 8-bar section becomes 4+4, and the halves are adjacent and in the same group B.
- **Why it matters:** the refinement runs after the same-group merge, so it undoes what the merge intends (fewer cuts
  that change nothing).
- **Suggested fix:** use an absolute or in-section-relative floor, for example the raw Foote value against the median of
  the section's own grid points. Do not split when both halves fall in the same repeat group.

**r3-m2. The dynamics gate almost never applies**
- **The issue:** the gate is `clip(own / dyn_gate)` with `dyn_gate` 0.7. In the full synthetic run, about 25 of 28 bars
  have own >= 0.7, so the dynamics segments, impacts and novelty are added in full almost everywhere.
- **Evidence:** at 5.0 s they add +0.75 (own 1.72 -> 2.47). That is what lifts the bar over the merge guard of 2.41 in
  F4-r3.
- **Suggested fix:** gate on own relative to the section cost (for example own >= cost), or scale the gate by
  own / cost.

**r3-m3. Labels inside one repeat group mix roles, and a mid-song section is labelled 'outro'**
- **MEGAFAUNA:** group J = drop, drop, drop, inst and group K = drop, inst, inst. The material is the same and the
  energies are equal. This is a side effect of F6-r3.
- **Versatile:** 129.2 s (8 bars) changes from break (G) to 'outro' (group C), although it carries the edm_role
  breakdown 129.2-144.0 s. The round-2 note about the outro group's over-reach still applies.

**r3-m4. The DSP-only rhythm fallback locks onto the off-beat hats**
- **Evidence:** on a simple loop (sine-sweep kick on every beat, noise hat on the off-beats; p_loop.py, use_models=False),
  beats land at 0.246, 0.761, 1.262 s while the kicks are at 0.5, 1.0, 1.5 s. The tempo is correct (119.99 BPM) and the
  phase is half a beat off.
- **Scope:** fallback path only. The model path was not checked on this signal.

**r3-m5. Test coverage**
- The structure tests, both unit and review round 2, still use the fixture's truth rhythm. None checks stability under
  tracker jitter.
- `test_pattern_features.py` does not cover hits that sit on the slot edges.

## Round 4 (r-dsp-m2-r4, W3 verify)

Fixes checked: F4-r3 (bar-jitter stability) fixed, F6-r3 (MEGAFAUNA drop extent) fixed, S05 (Jeremy band entry) fixed in the
stage, S09 (synthetic intro/bridge labels) fixed for the synthetic song. These were verified by re-running structure, choreo and cues
with the current code on the integrator's real runner caches (out/_wip/r-dsp-m2-r4/real/<slug>, probes/runreal.py). The synthetic
song gives boundary F 1.0 with labels intro/verse/chorus/bridge/chorus/outro. The structure stage also holds F 1.0 under every
constant bar shift from -40 to +40 ms and random per-bar jitter of ±20/±30 ms (12 seeds; p_jit2_*.log). One new major:
F7-r4 (the S05 snap shifts the eight-count grid; tests/review/M2/r-dsp/test_structure_impact_snap_counts_real.py).

**r4-m1. The integration tests for S05/S09 still fail, but only because the integrator outputs are stale**
- out/_wip/integrator/* was produced at 05:10, before fixer-m2-r3 (06:21). On a re-run from the same upstream, Jeremy's top
  impact (19.47 s) is a section start and the synthetic intro is one 'intro' section. Both tests will pass once the integrator re-runs.
- The structure cache key changes only because new params were added (bar_jitter_frames, short_section_margin,
  impact_snap_strength). See r4-m2.

**r4-m2. The structure StageSpec version is still "1.0.0" after three rounds of behaviour changes**
- The runner key covers the stage version and params, not the code. A future behaviour-only fix that adds no param would leave
  every cached structure/choreo/cues output stale.
- Suggested fix: bump the stage version with each behaviour change (choreo and cues follow through the upstream key).

**r4-m3. Jeremy: 11 of 19 sections are still labelled chorus** (the second half of S09, carried over)
- The four 8-bar sections from 220.7 to 271.5 s (group G) and 203.1 s (F) are all 'chorus', after the choruses at 176.1/194.1 s.
- Labels come from allin1 shared within groups. No relabel rule covers a long repeated outro/vamp.

**r4-m4. r3-m4 still open: the DSP-only rhythm fallback locks onto the off-beat**
- p_loop.py (kicks at 0.5 s + 0.5 k): bars land at 0.76 s, so the 'ab' song's B section starts at 32.74 s instead of 32.5 s.
- Fallback path only.

**Round-3 minors re-checked:** r3-m1 is fixed (on the uniform loop the refinement no longer adds splits; same sections with and
without it). r3-m3 is fixed (MEGAFAUNA groups I/J are all drop; Versatile 129.2 s is 'break' + breakdown). r3-m2 is unchanged
(dyn_gate is still absolute) but is no longer decisive on the synthetic song. r3-m5 is covered by the fixer's tests/unit/structure/test_robustness.py.

## Round 5 (r-dsp-m2-r5, W3 verify)

Fix checked: **F7-r4 is fixed for Jeremy.** verse#1 is phrased P02 19.47 s (1 bar) + P03 21.80 s (8 bars); the eight-counts are
E005 19.47 s (4-beat partial) then 21.80 / 26.37 / 30.96 / 35.56 s, the pre-snap grid; no partial dangles before the chorus. The
section cue stays at 19.47 s (tier 1) and 21.80 s gets a tier-2 phrase cue. The fix is a general rule (`structure.phrase_layout`), not a
test-specific hack. r4-m2 is fixed (structure StageSpec 1.1.0). Re-run with the current code on the integrator's real caches
(out/_wip/r-dsp-m2-r5/real/<slug>, probes/runreal.py) for all four real songs and the synthetic song: byte-identical to fixer-m2-r4's
re-run and to a second run of my own (deterministic). Tests: tests/review/M2/r-dsp + M2 unit tests 75 passed / 13 skipped,
`-m real` 6 passed. tests/integration/M2 still fails 2/2, only because out/_wip/integrator/* (05:10) is stale (see r4-m1).

New major: **F8-r5**, the phrase-remainder placement is a global vote of every other section start, so it depends on how many
sections lie before vs after the section rather than on the section's music
(tests/review/M2/r-dsp/test_phrase_grid_nonlocal.py, fast, synthetic truth).

**r5-m1. The same sec_ranges give the pickup reading early in the song and the trailing reading late in the song** (explains F8-r5)
- probes/p_layout.py, phrase_layout(..., 8):
  - A verse#1 with a trailing stop bar, (0,8),(8,17),(17,25),(25,33),(33,41),(41,49): verse -> (8,9),(9,17), a pickup. This is
    the same layout as Jeremy's snapped verse, so the two can never be told apart, and count 1 moves off the vocal entry.
  - The same trailing bar in the second-last section, (...,(32,41),(41,49)): -> (32,40),(40,41), remainder at the end.
- The song start (bar 0) is excluded from the support, so for the first section after the intro only the LATER sections vote.
- The impact snap knows which start it moved; that is the one case where "pickup" is evidenced.

**r5-m2. An odd pickup of 3+ bars still leaves a partial count right before the main phrase**
- phrase_layout((0,8),(8,19),(19,27),(27,35),(35,43), 8) gives a 3-bar pickup (8,11). choreo cuts every phrase forward from its start,
  so the pickup becomes an 8-beat count plus a 4-beat partial ending at bar 11: the F7-r4 "dangling partial" shape, one phrase earlier.
- For a leading (pickup) phrase, choreo should align its counts backwards from the phrase end (partial first).
- No real song hits this today.

**r5-m3. With the snap disabled, Jeremy's 9-bar intro now gets a 1-bar pickup at the song start**
- (0,9),(9,17),... -> (0,1),(1,9): the intro's first bar (0.48 s) becomes a 4-beat partial. Before round 4 it was 8 + 1 (remainder at
  the end, at the band-entry bar). Only reachable with impact_snap_strength 0; noted because it changes a user-override path.

**r5-m4. The pickup count is numbered 1-4 (first_count 1)**
- A 1-bar pickup into a phrase is danced "5-6-7-8". CONTRACT allows first_count 5 only for E000 (D13), so the stage cannot say so.
  A contract/CR question for the W3 integrator, not a stage bug.
