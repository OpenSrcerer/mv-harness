# r-dsp-m1-r2: M1 Signal review, round 2 (lens R-DSP)

Independent reviewer, PLAN §11. This round checks the fixer-m1 fixes for round-1 findings B1, M1 and M2, then looks for
new blockers and majors. Every claim below was checked by running code. The scratch scripts and logs are in
`out/_wip/r-dsp-m1-r2/`. The failing tests are in `tests/review/M1/r-dsp/test_rdsp_r2_kicks.py`, with helpers appended to
`rdsp_m1_support.py`. Minor findings are in `docs/review/M1-r-dsp.md`, section "Round 2".

## Fix verification

| round-1 id | status | how it was checked |
|---|---|---|
| B1 kick doubling | **NOT FIXED** (reopened as B1-R2) | Round-1 tests pass. Kick-over-bass without hats is F1 1.0 for bass gains 0.3, 0.6 and 0.9, at 128 BPM and with one bass note per beat. Add closed hats and the doubling returns: 16th hats F1 0.72, off-beat hats F1 0.85, 16th hats without bass F1 0.85. The contract fixture song is at F1 0.880 (P 0.856, R 0.906), below PLAN §7's 0.95. The round-1 fixture test only asked for P ≥ 0.85 and R ≥ 0.9, which this barely clears. |
| M1 quiet-master gate | fixed | Piano and snare-plus-hats material: 0 kick events at 0, -12, -20 and -30 dBFS peak. Kicks keep R 1.0 down to -40 dBFS. The gate is now detected from the sample peak (`_kick_gate`). One minor remains: m13, the `viz` flag for quiet masters. |
| M2 drop hint after snap | fixed | A drop part is hinted 'drop' at grid offsets of 0.3, 0.5, 0.7, 0.95, 1.1, 1.3, 1.5 and 1.7 s. On Versatile the drop hints are [51.72, 162.48] (round 1: [162.48]). `Segment.t_event` is carried through `_merge`. The fix is real, not specific to the test. One minor remains: m15, `t_event` is not written. |

## Findings (blocker / major)

### B1-R2 (blocker): B1 is not fixed. Hats supply the "click evidence" and the kick doubling returns
- **Location**: `src/mvh/stages/spectral/stage.py` (`has_click` / `accept_weak` lambdas, `kick_score` with
  `kick_click_w` 1.0); `dsp.py:select_hit_events`, `click_rise_db`, `kick_confidence`.
- **Mechanism**: the fix tells kicks from bass beating by broadband (≥ 1 kHz) click evidence. A closed hat in the tail of
  a kick supplies exactly that click. The bass/kick beating, or the kick decay alone, at the hat's time then passes:
  - `has_click` is true, so the refractory does not drop it.
  - `kick_conf` is 0.8 to 1.0 (hat click plus kick decay), so the weak path accepts it.
  - The full-weight click step makes `rise_db` ≥ 6 dB.
- **Evidence**:
  - Kick-over-bass plus 16th hats: 78 events for 44 kicks, F1 0.721 (P 0.564). The extras sit +0.124 s and +0.249 s
    after each kick, exactly at the hats.
  - Off-beat hats (the house hat): F1 0.854.
  - 16th hats with no bass at all: F1 0.846. The extras have env 0.01, kick_conf 1.0 and viz false.
  - Contract fixture song: F1 0.880. Kicks with a hat 100 ms earlier are timed onto the hat (missed kicks at 11.9 and
    22.4 s, nearest event -0.101 / -0.099 s). Kicks under the ride are dropped by the refractory (18.0, 24.0 s).
- **Test**: `test_rdsp_r2_kicks.py::test_kick_events_with_hats_are_not_doubled[bass+16th-hats|bass+offbeat-hats|16th-hats-no-bass]`
  and `::test_kick_events_on_the_contract_fixture_song_meet_plan`. All four fail.
- **Suggested fix**: tell a kick from beating by the **low band's own attack**, not by broadband click:
  - Require the ≤ 400 Hz step (without the click term) to be large at the event.
  - Pass the existing `gate=` (the low band's own step contrast) to `refine_onset` for the kick. `select_hit_events`
    supports it, but the stage never passes it. This stops a hat from taking the timing.
  - Apply viz's one-hit-per-note re-arm (the 4 dB dip of the kick band since the last kick) to weak and refractory
    candidates.

### R2-M1 (major, regression from the B1 fix): the 0.30 s click refractory drops real kicks whose click is masked
- **Location**: `src/mvh/stages/spectral/dsp.py:select_hit_events` (refractory branch); `stage.py` params
  `kick_refractory_s` = 0.30 and `kick_click_db`.
- **Claim**: every hit that lacks a fresh ≥ 1 kHz click (rise ≥ 6 dB over the max of the 50 to 10 ms before it) and
  lands within 0.30 s of a kept event is dropped, strong viz hits included. Under a crash or ride wash, distorted guitars,
  or any busy top end, real 8th-note kicks have no fresh click.
- **Evidence**:
  - Synthetic, 8th-note fixture kicks with a crash struck every 2 s: at 130 BPM R 0.828 (F1 0.906); at 150 BPM R 0.891
    (F1 0.942). With `kick_refractory_s=0` both reach 1.0, and viz registers 60 of 64.
  - Jeremy: 528 unambiguous kicks from the DrumSep kick sub-stem (≥ 20 dB rise, within 6 dB of the stem's top). Current
    recall at ±30 ms is 0.733. Without the refractory it is 0.977, and precision only moves from 0.788 to 0.815. The 181
    dropped events have a median kick-stem rise of 33 dB at the stem's top level, 267 ms after the previous kept event,
    and 173 of them are viz=true.
  - The builder's own W0 acceptance test `tests/unit/spectral/test_spectral.py::test_real_song_kick_counts`
    (MVH_REAL_TESTS=1, viz-flag count within 10 % of the W0 offline reference) now **fails** on megafauna (280 vs 464),
    versatile (155 vs 208) and jeremy (451 vs 617). In round 1 the counts were 488, 211 and 622, which pass.
  - The `viz` flag no longer means "viz registers it". MEGAFAUNA has 280 viz=true events, while the real `audio.js`
    registers 495 to 504 hits.
- **Test**: `test_rdsp_r2_kicks.py::test_eighth_note_kicks_under_a_crash_are_kept[130.0|150.0]` (synthetic, fails) and
  `::test_jeremy_unambiguous_kicks_are_kept` (`@pytest.mark.real`, opt-in with MVH_REAL_TESTS=1, fails).
- **Suggested fix**:
  - Never drop viz-registered hits (`viz_hit`), since viz's re-arm already proves a new note.
  - Base the refractory on the low band's own attack rather than the click.
  - Keep the refractory short (about 120 ms, the round-1 suggestion), not 300 ms.
  - Re-run the real-song count test before closing.

### R2-M2 (major, pre-existing, not found in round 1): 16th-note double kicks at 160 BPM produce almost no events
- **Location**: `src/mvh/stages/spectral/dsp.py:hit_envelope` (`HIT_FLOOR`, centred median reference) and
  `select_hit_events` (`event_x_min` 0.3).
- **Evidence**:
  - Tight kicks (70 ms decay, with click) on 16ths at 160 BPM (94 ms apart): 3 events for 96 kicks (F1 0.061). The
    fixture kick gives 4.
  - At 140 BPM (107 ms) all 96 are found.
  - Debug: at 160 BPM only 4 attacks exceed `HIT_FLOOR`, so the ±8 s reference comes from the section edges and the roll
    kicks have x around 0.2, below `event_x_min`.
  - Independent of the refractory (the same result with it set to 0). viz itself also registers only 2, but PLAN §7
    applies to events, and the 400 Hz refinement envelopes resolve every kick.
  - Metal double-bass at 160 to 200 BPM is ordinary, and kick events are the main sync points for choreography.
- **Test**: `test_rdsp_r2_kicks.py::test_sixteenth_double_kicks_at_160_bpm` (fails).
- **Suggested fix**:
  - Fall back to the 400 Hz low-band envelope for kick events when the kick band's attacks fall below `HIT_FLOOR` while
    the low band shows clear steps.
  - Alternatively, compute the reference only from attacks of the same density regime.

## Gate

`scripts/gate.ps1 M1` was run (`out/_wip/r-dsp-m1-r2/gate.log`):

| step | result | cause |
|---|---|---|
| fixture | PASS | |
| unit | FAIL | `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs`: rhythm is no longer a stub. Another module, not M1. The spectral, loudness and dynamics unit tests pass. |
| review | FAIL | By design: only the new round-2 tests fail. The round-1 review tests pass. |
| ruff | FAIL | Other modules only: `sep/fit.py`, `stages/drums`, `stages/structure`. M1 and the review tests are clean. |
| contract | PASS | |
| validate | PASS | |
| e2e | PASS | spectral, loudness and dynamics ran for real, about 3 s each. |
| lib-node | PASS | |
| determinism | FAIL | 28 of 180 files differ: stems, drums, lyrics, lipsync, cues, `curves/core.f32` and others. No M1 events file is among them. Running spectral, loudness and dynamics twice in-process gives identical curves (`out/_wip/r-dsp-m1-r2/det.py`), so the `core.f32` difference comes from other producers. |

The builder's opt-in real-song test `tests/unit/spectral/test_spectral.py::test_real_song_kick_counts` is not part of
the gate. It fails on 3 of 4 songs (see R2-M1).

## Test status
- `tests/review/M1/r-dsp/` round-1 tests: 8 passed.
- `test_rdsp_r2_kicks.py`: 7 synthetic tests fail (3 hats cases, the fixture song, 2 crash cases, double kick). The
  Jeremy test fails when run with MVH_REAL_TESTS=1 and is skipped otherwise.
- ruff is clean on `tests/review/M1/r-dsp`.
