# r-dsp-m2: R-DSP review of M2 Rhythm (allin1, rhythm, structure, choreo, cues)

**Verdict: fail.** I found 5 majors and no blockers. The rhythm core is accurate on the synthetic song and on click
tracks. Five defects need fixing:

1. A beat-grid crash on any input shorter than 6 s.
2. A user pin that is lost from cues and moments.
3. Sections of 1 bar, which the frozen contract forbids.
4. Circular structure tests that hide weak section and repeat detection.
5. A downbeat vote that lets the tracker it flags as wrong flip the bar phase on versatile.

All majors have failing tests in `tests/review/M2/r-dsp/`. The minors are in `docs/review/M2-r-dsp.md`.

I formed these findings before reading `docs/build/reports/builder-m2.md`. I then used that report only to check
whether a behaviour was intended. The builder calls the 1-bar first section deliberate, but there is no recorded
decision for it. M2-D13 says a pinned cue is tier 1 with strength 1.0, and the output contradicts that.

## What I ran

| Run | Result |
|---|---|
| Full `mvh analyze` of the synthetic song (all real stages, 6 threads) into `out/_wip/r-dsp-m2/synth` | rhythm: beats F1 1.00, downbeat F 1.00, tempo error 0.033 BPM, median 1.25 ms / p95 15.7 ms, pickup and the 3/4 bar exact. structure: sections at 0.99/9.0/25.0/34.5/42.5/52.5 s against the truth 1/9/17/25/34.5/50.5 (boundary F 0.667); labels verse/verse/verse/chorus/chorus/outro |
| Click tracks with the models (60-200 BPM, swing, 48 kHz) | beat F1 ≥ 0.992, tempo error ≤ 0.21 BPM |
| Click tracks on the DSP path | correct at 60-140 BPM; **halved at 160-200** (minor m2) |
| Musical 3/4 and 4/4 pieces (`p_waltz.py`) with the models | meter correct, downbeat F 1.00 |
| Real songs, rhythm → structure → choreo → cues with the W0 tracker outputs replayed (`replay.py`, no inference) | 105.13 / 130.25 / 107.15 / 137.98 BPM; madmom phase flags on versatile and newton-vs-nye; grid smooth (at most 2 inter-beat intervals per song deviate more than 10 % from the local median) |
| structure, choreo and cues on the synth fixture with the exact upstream | equal to the truth (sections, phrases, EDM roles, counts including E000, grooves) |
| Edge cases on the DSP and model paths (silence, noise, a sine, 1-10 s clips, the 3 s 48 kHz tone) | rhythm crashes below 6 s; choreo crashes below 2 s |
| The `rhythm.beat_offset_s` override at 0.03-0.15 s | downbeat F stays 1.00 (no finding) |

## Majors

1. **F1. A pinned cue becomes a tier-1 "beat" with null strength and is dropped from moments.**
   - **Location:** `src/mvh/stages/cues/__init__.py`:
     - `on_grid(pin)` snaps the pin onto a beat;
     - after `merge_cues` the stage nulls strength and lead-in for every `kind == "beat"` cue;
     - moments are filtered on `kind` only.
   - **Root cause:** `pinned` is last in `CUE_KIND_PRIORITY` (conventions.py, frozen). After merging, the cue's kind
     is `beat`.
   - **Evidence:** pins at 20.51 and 44.0 s produce `{kind: "beat", tier: 1, strength: null, kinds: ["beat", "pinned"]}`.
     moments.json contains neither pin.
   - **Test:** `tests/review/M2/r-dsp/test_cues_pinned.py`.
2. **F2. rhythm crashes on any input shorter than about 6 s, and choreo crashes below 2 s.**
   - **rhythm:** `fusion.metrical_evidence` uses a window of max(6 s, 4 beats) and indexes past the padded envelope,
     raising IndexError. This happens on the DSP and model paths alike. It hits the 3 s tone48 runtime fixture and
     4-5 s click tracks.
   - **tempogram_peaks:** the `np.convolve(..., 'same')` trend removal fails below 1 s.
   - **choreo:** the movement smoothing `np.convolve(dens, hanning(201), 'same')` breaks the broadcast below 2.01 s.
   - **Impact:** once the stubs are replaced in W3, every stage downstream of rhythm fails on short inputs.
   - **Test:** `test_short_inputs.py`.
3. **F3. Sections shorter than 2 bars are emitted.**
   - **Location:** `structure.segment_dp` deliberately allows a short first section.
   - **Contract:** `events/sections.json` says "segments shorter than 2 bars are merged". No M2 decision records the
     exception.
   - **Evidence:** `segment_dp` returns `[0, 1, 9]` when bar 1 has a boundary score of only 1.5. On real songs
     jeremy and megafauna both get a 1-bar intro S01 before an 8-bar intro S02 in the same group.
   - **Test:** `test_structure_min_bars.py`.
4. **F4. The structure synthetic-truth tests are circular, and with realistic input the stage misses sections and
   repeats.**
   - **Circularity:** the fixture allin1 segments and labels are the truth sections and labels, so
     `tests/unit/structure` passes by copying them.
   - **With realistic input:** I fed in the real allin1 output on the synthetic song. It is committed as
     `tests/review/M2/r-dsp/data/synth_real_allin1.npz` (940 KB, float16). With it:
     - intro and verse merge, so the boundary at 9.0 s is lost (boundary F 0.909);
     - chorus#1 and chorus#2 land in different repeat groups (the truth puts both in C);
     - in the full analyze, the chorus at 17.0 s and the outro at 50.5 s are missed (F 0.667).
   - **Test:** `test_structure_real_allin1.py`.
5. **F5. The downbeat vote flips the phase toward madmom, the tracker the stage itself flags as one beat off.**
   - **Location:** `rhythm/__init__.py`, the downbeat vote and `decode_meter`.
   - **What happens on versatile:**
     - the stage flags `downbeat_phase_off:madmom:-1`;
     - it still counts madmom's unshifted votes;
     - it inserts a 3-beat bar at 203.1 s;
     - from 204.5 s to the end, fused downbeats match madmom (F 1.00) and allin1 not at all (F 0.00).
   - **Internal votes after 204.4 s:**
     - allin1: 7 on beat 2;
     - beat_this: 6 on beat 1 and 5 on beat 2;
     - madmom: 10 on beat 1.
     - Corrected by madmom's own detected shift, the vote is 22 : 6 for keeping the phase.
   - **Test:** `test_rhythm_downbeat_vote_real.py`, marked `real`. It replays the W0 cache and needs no inference.

## Verification

`python -m pytest -q tests/review/M2/r-dsp` gives 11 failed, 1 passed and 2 skipped (the real tests). The one that
passes, `test_fixture_allin1_is_the_truth`, documents the circularity. With `-m "real or not real"` the two versatile
tests fail as well, on F 0.00 and the 3-beat bar 110. ruff is clean.

## Minors (in `docs/review/M2-r-dsp.md`)

- **m1.** Beats snap to a kick's low-band body transient, 13-18 ms late (p95 15.7 ms).
- **m2.** On the DSP-only path a single estimator gets full consensus, so 160-200 BPM clicks are halved.
- **m3.** On MEGAFAUNA the kick and metrical evidence is nearly flat and does not decide the octave.
- **m4.** The arbitration rows contain duplicates; the `tempo_ratios` param is unused; `groove_similarity_noisy` is
  undeclared.
- **m5.** A beat at the start of a stop, and the outro decay, are marked in_pulse.
- **m6.** A spurious meter change appears in the virtual tail bars.
- **m7.** allin1 embeddings are offset 45 ms from their declared 10 Hz timebase.
- **m8.** Group-majority labels overwrite confident allin1 chorus and intro labels (newton-vs-nye, jeremy).
- **m9.** Test-coverage gaps.

## Change request (W3 integrator)

- **CR-r-dsp-m2-1.** Put `pinned` first in `CUE_KIND_PRIORITY` in `src/mvh/contract/conventions.py`, or exempt it
  from merging, so a user pin keeps `kind: pinned` (D37). The cues stage can work around it meanwhile:
  - do not null the strength of tier-1 cues;
  - build moments from `kinds[]`.

## Files

- **Tests:**
  - `tests/review/M2/r-dsp/conftest.py`
  - `tests/review/M2/r-dsp/test_cues_pinned.py`
  - `tests/review/M2/r-dsp/test_short_inputs.py`
  - `tests/review/M2/r-dsp/test_structure_min_bars.py`
  - `tests/review/M2/r-dsp/test_structure_real_allin1.py`
  - `tests/review/M2/r-dsp/test_rhythm_downbeat_vote_real.py`
  - `tests/review/M2/r-dsp/data/synth_real_allin1.npz`
- **Minors:** `docs/review/M2-r-dsp.md`
- **Progress log:** `docs/build/progress/r-dsp-m2.md`
- **Probes and outputs (not committed):** `out/_wip/r-dsp-m2/`
