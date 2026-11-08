# builder-m2 report: M2 Rhythm (allin1, rhythm, structure, choreo, cues)

All five stages are real implementations (stage version 1.0.0). Every frozen catalogue output and field is written;
additive fields and interpretations are recorded in `docs/contract/decisions/M2.md` (M2-D1..D16, CR M2-1..M2-6).
No lyric text appears in any M2 output, log or test.

## What each stage does

**allin1** (`src/mvh/stages/allin1/`). all-in-one-infer 3.1.0 `harmonix-all`, 8 folds, through
`analyze(stems_input=StemsInput(...))` on four float32 stem WAVs it writes from separate_fast (no AllInOneSession in
3.1.0; arrays in, explicit local model paths, per docs/spike/main.md section 2). It keeps beats, downbeats, segments, the
integer bpm plus `bpm_from_beats` (median IBI; the integer bpm can be 2 BPM off), the activations `[T x 13]` at 100 Hz
(beat, downbeat, boundary, 10 Harmonix labels) and the embeddings (4 stems concatenated, 768 dims, mean-pooled to
10 Hz). Activations and embeddings are cache-only (D18). `allin1/read.py::load_allin1` reads both the real record and
the stub copies (CR M2-2).

**rhythm** (`rhythm/__init__.py`, `fusion.py`, `trackers.py`). The beat grid.
1. Trackers: beat_this (logits), madmom-infer RNN beat/downbeat activations + DBN, allin1 activations/beats, and DSP
   (onset envelope, PLP, tempogram). Each tracker is latency-calibrated against physical attacks (median offset to
   transients with a >= 15 dB rise) before fusion (M2-D4).
2. Tempo arbitration (M2-D6): candidates from every tracker, tempogram peaks and the x2 / x0.5 / x1.5 / x2/3 relatives,
   scored by consensus, drum metrical evidence (kick/snare contrast and coverage at that level), tempogram salience
   and a 120 BPM log-normal prior. All candidates are kept with `relation` and score; `override_hint` lists the
   alternatives for `rhythm.bpm`.
3. Beats: a beat-only HMM (madmom-infer state space, own observation model, CR M2-3) on the fused activation inside
   +-20 % of the arbitrated tempo, then nearest-transient snapping (+-25 ms, >= 15 dB). Pulse flags mark no-pulse
   regions and a virtual uniform grid fills them (D11/D12, M2-D2); pickups are recovered backwards where attacks support
   them.
4. Downbeats: 2-of-3 vote (beat_this, allin1, madmom DBN re-decoded at the arbitrated tempo) + mean downbeat activation
   feeding a meter HMM (3/4 and 4/4, switch and early-bar costs). Per-tracker best phase shift is reported; a clear
   offset raises `downbeat_phase_off:<tracker>:<shift>` (M2-D5).
5. Per-segment feel (normal / half_time / double_time) from the trackers' local tempo vs the grid (M2-D7);
   tempo_segments, pulse_regions, bars (pickup, irregular), beats (beat_index, beat_in_bar, in_pulse, conf), curves.
6. QA (M2-D16): tracker F vs grid, pairwise F, downbeat agreement and flags; new `tempo_trackers_disagree` flag and
   warning when the tracker tempi are not even octave-related (MEGAFAUNA). Overrides: `rhythm.bpm`,
   `rhythm.beat_offset_s`, `rhythm.downbeat_phase`.

**structure** (`structure/__init__.py`, `features.py`). Per-bar features (MFCC, chroma from harmony or own CQT, RMS, bass,
centroid, HPSS kick rate, onset rate, allin1 embeddings / label probabilities / boundary activation / segments,
dynamics novelty, impacts, silences). Boundary score = allin1 boundary + segments + Foote novelty (4 and 8 bars) + energy
change + dynamics + silence edges; a DP picks section starts preferring 4/8-bar multiples (min 2 bars except a short
intro bar before the phrase grid). Repeat groups by section similarity with an adaptive threshold. Labels: allin1's
Harmonix labels when informative (verse+chorus >= 30 % of the mass) shared inside a repeat group; otherwise structural
labels (intro / build / drop / breakdown / inst / break / outro / silence) (M2-D8). Phrases (4/8/16-bar choice by
score), and THE EDM roles (build, drop, breakdown) from drive (bass + kick + level) with evidence strings. Overrides:
`structure.boundaries` (add / remove / move) and labels.

**choreo** (`choreo/__init__.py`). Eight-counts E### aligned to phrases and sections (E000 = 5-6-7-8 lead-in, D13,
M2-D14), sub-counts (D14: "1 e & a"), per-beat accents, grooves G## (drum pattern per bar from drum_hits or an own
percussive band classifier; dominant groove), hit_points (>= 3 coinciding kinds, M2-D12), holds (sustains, stops,
silences), `tables/{beats,bars,sections}.csv` (D2). Counts restart at section starts so repeated sections count
identically.

**cues** (`cues/__init__.py`). Tiered cues: 1 section/drop/build/breakdown starts, 2 phrases/impacts/stops, 3 hit
points/downbeats, 4 in-pulse beats as references to beats.json (D15, M2-D9). Near-beat events snap to the beat (M2-D10)
and `mvh.contract.conventions.merge_cues` gives one cue per time (D37) with `kinds[]` / `sources[]` only where several
candidates merged; every cue cites `{file, id}`. Lead-ins per M2-D11; pinned cues from overrides (M2-D13); moments =
top-20 ranked cues with a minimum gap.

## Accuracy vs thresholds (synthetic)

| Check | Threshold | Measured |
|---|---|---|
| Beats F1 at +-70 ms, clicks 90/120/140 BPM (DSP path, unit) | >= 0.98 | 1.00 |
| Tempo error, clicks | <= 0.5 BPM | <= 0.05 |
| Swing 110 BPM + tempo ramp (unit) | F1 >= 0.98 | pass |
| No-pulse gap gets virtual beats, in_pulse false (unit) | D11/D12 | pass |
| Synth song with models (slow): beats F1 / downbeats F1 | >= 0.98 / >= 0.95 | 1.00 / 1.00 |
| Synth song tempo error | <= 0.5 BPM | 0.03 BPM |
| Synth song beat timing | median <= 5 ms | 1.2 ms (p95 15.7 ms) |
| Pickup (1 beat, beat 4 at 0.5 s) and the 3/4 bar 16 | exact | exact |
| Pulse agreement with truth | >= 0.9 | 0.973 |
| Sections: boundary F (+-0.5 bar), labels, repeat groups, bars | F >= 0.95, exact | 1.0, exact |
| Phrases, EDM build bars 13-16 and drop at bar 18 | exact | exact |
| Degraded structure (no dynamics/harmony/allin1) | boundary F >= 0.7, drop +-0.05 s | pass |
| choreo with truth upstream: counts, accents, E000, beats table | exact (accent +-0.02) | exact; hit points 17/17 |
| cues: one per time, ordered, sources, tiers | D37/D15 | pass |

**Full pipeline on the synthetic song** (gate e2e: real separation, real allin1, harmony, dynamics upstream):
rhythm beats F1 1.00, downbeats F1 1.00, tempo 120.033 (error 0.03 BPM), median 1.25 ms, pickup and 3/4 bar exact,
pulse agreement 0.964, tracker agreement 0.968 / downbeats 0.963. Structure is weaker than in the unit tests, because
the contract fixture's allin1 stub encodes the true segments while the real allin1 on the 57 s synthetic song finds
only two (0.99 s and 34.5 s): boundary F (+-0.5 bar) 0.62 -> 0.67 after M2-D17 (starts 1, 5, 13, 18, 22, 27 vs truth
1, 5, 9, 13, 18, 26; the verse -> chorus change at bar 9 is carried by harmony only and the bass enters at bar 3).
EDM roles went from a false drop at bar 5 + build + drop to exactly the truth (build bars 13-16, drop at 34.5 s) with
`drop_context_bars` 2. There is no PLAN threshold for sections; this is reported, not asserted.

## Real songs (upstream from tests/contract/real-<slug>, own allin1 run)

Timings are stage seconds (8-core box, 6 threads, inside a heavy slot for allin1/rhythm).

| Song | allin1 s | rhythm s | structure s | choreo s | cues s | BPM | trackers (bt / a1 / mm) | conf | flags |
|---|---|---|---|---|---|---|---|---|---|
| megafauna | 47 | 77 | 82 | 16 | 0.06 | 105.13 | 162.2 / 105.3 / 193.5 | 0.78 | feel_changes, no_pulse_regions, (now) tempo_trackers_disagree |
| versatile | 48 | 77 | 86 | 19 | 0.08 | 130.25 | 130.4 x3 | 0.95 | downbeat_phase_off:madmom:-1, no_pulse_regions |
| jeremy | 66 | 130 | 129 | 25 | 0.07 | 107.15 | 107.1 x3 | 0.97 | no_pulse_regions |
| newton-vs-nye | 38 | 61 | 69 | 13 | 0.07 | 137.98 | 136.4 / 139.5 / 136.4 | 0.94 | downbeat_phase_off:madmom:-1, feel_changes |

- **MEGAFAUNA (regression case).** The trackers give 162 (beat_this), 105 (allin1) and 194 (madmom DBN): not even
  octave-related. Arbitration picks 105.2 (score 1.57; consensus allin1 + librosa, salience 1.0, coverage 0.87) over
  139.9 (1.07), 84.0 (0.95), 70.0 (0.90). 21 % of the song is flagged double_time feel (the 193-200 BPM layer).
  The alternatives 139.9 / 84.0 / 209.7 / 52.5 are in `override_hint["rhythm.bpm"]`; the SPIKE's 143.6 reading is the
  139.9 candidate. Tracker F vs the grid 0.61-0.73: the grid is the arbitrated reading, not a unanimous one, so the
  stage now raises `tempo_trackers_disagree` and a warning asking the user to confirm. Downbeat vote: all three
  trackers at shift 0. Structure: structural labels (allin1 labels uninformative), build at 123.5 s, drop at 141.8 s;
  17 sections after M2-D17 (was 20: 3+4, 4+3 and 4+4 bar same-loop pairs merged).
- **Downbeat phase (SPIKE).** madmom's downbeats are one beat early on versatile and newton-vs-nye (F 0.27 and 0.06 at
  shift 0, 0.50 and 0.93 at shift -1); the 2-of-3 vote outvotes it and the flag records it. beat_this and allin1 agree
  at shift 0 on all four songs.
- **versatile**: allin1 labels; drops at 84.9 s and 162.5 s, breakdowns at 129.2 / 144.0 s; 18 sections incl. a final
  silence. **jeremy**: allin1 verse/chorus/bridge labels, 8-bar phrases, no EDM roles. **newton-vs-nye**: 138 BPM,
  14 sections, a 5.6 % half-time stretch.
- choreo is `degraded` on all real fixtures (they have no drums/dynamics): own percussive classifier and RMS intensity.
  structure runs its own CQT chroma (no harmony chroma in the fixtures), which is most of its 70-130 s; in the full
  pipeline it takes about 7 s (synth e2e).
- cues.json is 63-118 KB on the real songs (292-546 cues; tier 4 is 63-76 % of them even after dropping no-pulse
  beats and listing kinds/sources only on merged cues). See CR M2-6.

- **Real-song snapshot test** (`tests/unit/rhythm/test_real_songs.py`, `-m real`): runs rhythm (real trackers, heavy
  slot) -> structure -> choreo -> cues on each fixture with W0's allin1 and asserts BPM within tolerance, 4/4, the
  octave alternatives (megafauna ~140), the madmom phase flags (versatile, newton), `tempo_trackers_disagree` only on
  megafauna, beats IBI vs BPM, 8-26 sections, labeling mode, the EDM drops (+-4 s), E000, one cue per time, tier-1
  count. The run (36 min, 4 songs) produced results identical to the own-allin1 runs; its only failure was a wrong
  dict key in the test, fixed, and the assertions (`check_chain`) were re-checked on the kept outputs: 4/4 pass.
- **Determinism**: across the gate's two `--force` runs, allin1 and rhythm outputs (beats, bars, tempo, curves) are
  byte-identical with real model inference.

## Tests

- `tests/unit/{allin1,rhythm,structure,choreo,cues}`: fast synthetic tests (39 pass); `slow` (real models on the synth
  song and on clicks) and `real` (tests/unit/rhythm/test_real_songs.py: the 4-song chain with snapshot tolerances) are
  opt-in: `uv run --frozen --no-sync python -m pytest -q -m real tests/unit/rhythm/test_real_songs.py`.
- Gate (`scripts\gate.ps1 M2`, final run log out/_wip/builder-m2/gate3.log): **FAILED, only for reasons outside
  M2**:
  - unit: all five M2 folders pass (allin1 4+1 skipped, rhythm 19+6 skipped, structure 5, choreo 6, cues 5);
    `tests/unit/contract::test_stub_files_are_stubs` fails because it asserts rhythm is still a stub (CR M2-5; reported
    by M1, M6a, M6b too).
  - ruff: E501 in `tests/review/M4/r-ml/*` (another module's review tests); every M2 file is ruff-clean.
  - contract, validate, e2e (570 s, all 25 stages, validate clean), lib-node: PASS.
  - determinism: no M2 output differs between the two `--force` runs (beats, bars, tempo, sections, phrases,
    edm_roles, counts, grooves, hit_points, holds, cues, moments, tables/*.csv, meta/structure/grooves all identical).
    The differing files come from separation (stems/*.flac, meta/separation.json) and its consumers (stem_activity,
    instruments, vocals, lyrics, voices, lipsync, meaning, curves of those stages).
  - M2 stage times in the e2e synth run: allin1 21-25 s, rhythm 21-24 s, structure 6-8 s, choreo 0.6 s, cues 0.5 s.

## Change requests

See `docs/contract/decisions/M2.md`: CR M2-1 (moments.d nullable vs envelope), CR M2-2 (stub matrices not
registered), CR M2-3 (madmom-infer numpy 2.5 `ndmin`), CR M2-4 (dynamics-dependent fields null on real fixtures),
CR M2-5 (obsolete `test_stub_files_are_stubs`, fails every gate), CR M2-6 (a compact tier 1-3 cue view).

## Open issues

- The first section can be a single intro bar before the phrase grid (megafauna, jeremy S01, 1 bar); deliberate
  (DP allows a short first section) but a choreographer may prefer it merged into S02.
- MEGAFAUNA's tempo level is a judgment call (105 vs 140); flagged for user confirmation.
- Section boundaries rely heavily on allin1 when it is informative; when it is not (the synthetic song, electronic
  tracks) the own features find energy/timbre changes but miss harmony-only changes (synth bar 9). The structure unit
  tests run on the fixture whose allin1 stub encodes the truth, so they are optimistic; the full-pipeline number above
  is the honest one. A repetition (lag-matrix stripe) feature was prototyped and did not help on the synthetic song,
  so it was not added. The viewer's boundary editing (`structure.boundaries`) is the correction hook.
- Real-song choreo grooves/hit points use the fallback percussive classifier until drums lands in the pipeline.
