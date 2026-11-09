# r-dsp-m1-r3: independent review, round 3, M1 Signal (lens R-DSP)

Scope: fixer-m1-r2's changes to `spectral` hits.kick (`dsp.select_kick_events`, the `kick_glide` pitch drop and
`low_excess_db`), checked against B1-R2, R2-M1 and R2-M2, plus regressions. Loudness and dynamics code are unchanged
since round 2. Re-run on the four real songs, the dynamics outputs still look right: MEGAFAUNA's drop hints are 96.1 and
141.6 s (plus 28.7), and Versatile's are 51.72 and 162.48 s. The scratch scripts are in `out/_wip/r-dsp-m1-r3/`. No
production code was changed.

## Verdict: fail

Two blockers and two majors. Every blocker and major has a failing test.

| id | sev | status | test |
|---|---|---|---|
| B1-R2 | blocker | NOT fixed (worse) | `tests/review/M1/r-dsp/test_rdsp_r2_kicks.py::test_kick_events_on_the_contract_fixture_song_meet_plan` (and r1 `test_rdsp_kick_events.py::test_kick_events_on_the_contract_fixture_song`) |
| R3-B1 | blocker | NEW, a regression | `test_rdsp_r3_kicks.py::test_kicks_over_the_builders_groove_bass_line[default,seed3,four-on-the-floor]`, `::test_kicks_over_a_sixteenth_bass_riff` |
| R2-M1 | major | fixed for the tested cases; NOT over a held bass note | `test_rdsp_r3_kicks.py::test_rock_eighth_kick_pairs_over_a_held_bass_note[140.0,160.0]` |
| R2-M2 | major | fixed only at the tested tempo | `test_rdsp_r3_kicks.py::test_sixteenth_double_kicks_beyond_the_tested_tempo[170bpm,180bpm,160bpm-under-crash]` |

The round-2 tests that now pass: the three hat cases, the crash at 130 and 150 BPM, 16th kicks at 160 BPM, and the
opt-in Jeremy kick-stem recall (MVH_REAL_TESTS=1). The builder's opt-in real-count test also passes, but only with the
bar the fixer widened (see m18).

## B1-R2: not fixed. The fixture song gets worse, and the cause is the bass line, not the hats
- Fixture song kicks at ±10 ms: F1 **0.864** (P 0.835, R 0.894). Round 2 had 0.880. The round-1 floor test (P ≥ 0.85,
  R ≥ 0.9) now fails too.
- Each of the six kicks at 9.9, 11.9, 15.9, 20.4, 22.4 and 24.4 s has a truth bass note
  (`truth.notes.bass`: midi 29/33, 44-55 Hz, inside the viz kick band) and a hat 100 ms before it. The bass-note onset is a
  viz-strength kick-band attack (x 1.7-3.3, viz true) with a real low-band attack (step 7-13 dB, excess 8-19 dB), so it is
  emitted as a kick.
- The real kick 100 ms later falls inside the 0.2 s refractory. Over the held bass note its ≤ 400 Hz excess is only
  2-4 dB (it needs 3.5) and its step 3-8 dB (it needs 6.5), so it is dropped (`dbg_fix.py`).
- Round 2 put this down to hats. The hat only adds the click.
- The fixer reports that band-envelope evidence cannot separate these. Their own feature does on this material:
  `kick_glide` is 1.93-2.25 at 8 of the 9 lost kicks and 0.48-0.80 at 6 of the 7 bass onsets that pre-empt them (one
  reads 1.61). The function's docstring promises rules that would use it (m16), but they are not implemented. Simple
  variants (a refractory override when glide ≥ 1.7, a song-level veto below 1.1) do not reach 0.95 on their own
  (`probe_glide_override.py`, `probe_glide_combo.py`). The pre-emption itself has to go.

## R3-B1 (NEW, a regression): kicks over a moving bass line
The ≤ 400 Hz "own attack" that now decides kick events belongs as much to the bass instrument as to the kick. Bass-note
onsets inside the kick band are emitted as kicks, and through the refractory they suppress the real kicks after them.
- **Builder's `tests/synth/m1/signals.groove()`** (its default texture, with sustained bass notes changing on the
  off-beats, "sub energy that the kick detector must ignore"): F1 **0.754** (P 0.78, R 0.73). Seed 3 gives **0.739**.
  Straight four-on-the-floor gives **0.880**, with 12 off-beat bass onsets emitted as kicks at kick_conf 0.965-1.0.
  Without the bass the same grooves score 0.976 / 1.0.
- Some kicks are lost even 242-363 ms after the previous kick, because a bass-onset event sits 121 ms before them
  (`probe_groove2.py`).
- **The fixer lowered** `tests/unit/spectral::test_kick_events_with_sub_bass_line` from recall ≥ 0.85 to ≥ 0.7 to pass.
  That is the regression's footprint.
- **16th-note bass riff** (rock/EDM gallop) under four-on-the-floor kicks, with or without 16th hats: the G1 note one
  16th before each downbeat is emitted as a kick in every bar. 40 events for 32 kicks, F1 **0.889**.
- `kick_conf` does not flag these events (m17).
- Suggested fix:
  - Judge the kick's own attack on the kick band itself (35-100 Hz, or a 30-120 Hz zero-phase envelope), not ≤ 400 Hz,
    where bass harmonics dominate.
  - Never let a candidate without a kick-body pitch drop (glide < ~1.1, in a song where most candidates show the drop)
    open a refractory over a following candidate that has one.
  - Use `kick_glide` in `kick_conf`.
  - Restore the unit-test bar (F1 ≥ 0.95 per PLAN §7) and add groove(seed=3) and the riff to the unit tests.

## R2-M1: fixed for the tested cases, not over a held bass note
- Fixed:
  - 8th kicks under a crash: 130, 150, 170 and 190 BPM give 1.0, 1.0, 1.0 and 0.99.
  - Jeremy unambiguous kick-stem recall: 0.97 (the opt-in test passes).
  - The viz-registered hits now dropped on Versatile, Jeremy and newton have a median kick-stem rise of 2.3 / 0.1 /
    3.5 dB, against 57 / 51 / 84 dB for the kept ones, so dropping them is justified (`real3.py`).
- Not fixed: the rock beat (kicks on 1, 1&, 3, 3&, 8th hats) over a bass note held for two beats.
  - 100-130 BPM: 1.0.
  - 140 BPM: R 0.625 (12 of the 16 '&' kicks lost).
  - 160 BPM: R 0.5 (all '&' kicks lost).
  - Without the bass note: 1.0.
- At 140 BPM the '&' kick's kick-band attack is x 0.37 with v_free 0, so the candidate is dropped as envelope-less
  (`v_ev <= 1e-4`). As a low-band step its excess over the held bass is 3.1 dB, below 3.5. At 160 BPM the low step is
  3 dB (`dbg_rock2.py`).
- Suggested fix: the same kick-band-based own attack as R3-B1. Keep weak episodes that have a clean low-band step
  instead of dropping them for v == 0.

## R2-M2: fixed only at the tested tempo
- Tight clicky kick on 16ths, 6 bars: 150 and 160 BPM give 96 / 96. 170 BPM (88 ms apart) gives 78 / 96. 180 BPM
  (83 ms) gives 3 / 96. 200 BPM gives 1 / 96.
- At 160 BPM under a crash every 2 s: 42 / 96. The roll rule needs a ≥ 15 dB ≥ 1 kHz click step, and the crash masks it.
- The fixture's longer kick at 160 BPM: 24 / 96.
- Metal double bass plays 16ths at 160-220 BPM, usually under cymbals.
- The roll rule (own step ≥ 6.5 dB, excess ≥ 3.5 dB, click ≥ 15 dB) is tuned to the one tested case (`probe_r3.py`).
- Suggested fix: as round 2 suggested, take dense-roll kicks from the 400 Hz low-band envelope (or a kick-band
  envelope), with thresholds relative to the local inter-onset level rather than fixed dB. Do not require the click when
  a cymbal wash is present.

## Other checks (no finding)
- 48 kHz, 96 kHz and mono give the same kick F1 as 44.1 kHz stereo (`probe_rates.py`).
- On the real songs (`realdyn.log`), dynamics keeps MEGAFAUNA's drops (96.1, 141.6) and Versatile's (51.72, 162.48),
  and Jeremy is segmented into 10 parts. Loudness is within 0.1 LU of ffmpeg on all four songs.
- Minor findings m16-m19 are in `docs/review/M1-r-dsp.md` (Round 3).

## Gate
`scripts\gate.ps1 M1`, log `out/_wip/r-dsp-m1-r3/gate.log` (run against `spectral/dsp.py` of 2026-11-09 00:21, the
current file):
- fixture PASS; ruff PASS; contract check PASS; validate PASS.
- unit FAIL, but not because of M1: spectral 29 passed, loudness 20 passed, dynamics 13 passed. The only failure is
  `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs`. It asserts that `mvh.stages.rhythm.run` is still a
  stub, and the rhythm module (M2) has since been implemented. That is for the integrator, not M1.
- review FAIL: 11 failed, 14 passed. These are exactly the failing tests listed above, with the numbers quoted in this
  report (fixture F1 0.864; groove 0.754 / 0.739 / 0.880; riff 0.889; 16ths 170/180/160-crash 0.897 / 0.061 / 0.609;
  rock over a held bass 140/160 0.769 / 0.667).
- The end-to-end analyze and determinism steps did not finish. The run was waiting for a heavy slot held by another
  agent when a power outage stopped the machine, and it was not re-run: the verdict does not depend on it.
