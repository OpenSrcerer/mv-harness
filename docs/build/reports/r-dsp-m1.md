# r-dsp-m1: independent R-DSP review of M1 Signal (spectral, loudness, dynamics)

Reviewer: r-dsp-m1 (PLAN §11, lens R-DSP). Inputs were the code and the spec. I formed my findings before reading the
builder's report, and used that report afterwards only to cross-check (it records neither the fixture-song kick score
nor the kick-free or Versatile cases).
Verdict: **fail**. There is 1 blocker and 2 majors, each with a failing test under `tests/review/M1/r-dsp/`, plus 12
minor findings in `docs/review/M1-r-dsp.md`.

## What I ran
- Builder unit tests: `pytest tests/unit/{spectral,loudness,dynamics}` gives 60 passed and 12 skipped (the real-song tests are opt-in).
- The fixture song (`tests/contract/synth`) through the three stages, using the builder's in-process FakeCtx harness
  with the fixture's bars, scored against `_truth/truth.json`: `out/_wip/r-dsp-m1/run_synth.py`.
- **An independent viz reference.** `tests/review/M1/r-dsp/viz_causal.cjs` runs the real `viz/js/audio.js`
  `AudioEngine.update()` under Node, frame by frame, at a chosen fps. It is fed the causal AnalyserNode data a
  browser would deliver (last 2048 samples of 0.5(L+R), Web Audio Blackman, |X|/N, 20 log10) from
  `rdsp_m1_support.analyser_frames`. It counts the hits viz registers (`sinceHit == 0`) and its onsets.
- The four real songs with the real-<slug> fixture bars as rhythm input, plus real viz at 60 and 100 fps:
  `out/_wip/r-dsp-m1/real.py`, log in `out/_wip/r-dsp-m1/real.log` (numbers only, no lyrics).
- EBU Tech 3341 cases #5, #9, #12 and #15 to #19, and Tech 3342 case #4 (beyond the builder's #1 to #4 and #1 to #3).
- Edge cases from `tests/synth/primitives.edge_case` through `mvh analyze --only ingest,spectral,loudness` (mono, 48 kHz,
  MP3, corrupt FLAC, 10 s, unicode path). Dynamics was also run on 0.5 to 3 s inputs.
- Gate: `scripts/gate.ps1 M1`. Result in the last section.

## What holds up
- **The viz port is faithful.** Against real viz at 100 fps on the fixture song, `bands.*_viz` and `bands.level`
  correlate at 0.989 to 0.995 with the expected 1-frame causal offset, and the hit envelopes at 0.90 to 0.95 (after the
  documented lag shift). The bass, mid and high flux-onset counts are within 3 % of viz at 100 fps. Note that viz's own
  onset counts depend on fps; the offline port equals viz at 100 fps. Time alignment is centred and correct: a step at
  5.0 s reads -3.0 dB at frame 500. `test_rdsp_viz_parity.py` (passing) keeps this as a regression guard.
- **Loudness.** EBU 3341 #1 to #5, #9 and #12 are within 0.06 LU. EBU 3342 #4 gives 15.00 LU. Integrated loudness is
  within 0.08 LU of ffmpeg on all four real songs, and the LRA matches ffmpeg to 0.1 LU.
- **Kick timing on true kicks.** Median error is -1.25 ms on the fixture song. Isolated one-shots score F1 0.99.
- **MEGAFAUNA finds its drops**: drop hints at 96.1 s (after the silence) and 141.6 s, where the bass rises from about
  -20 to -12.5 dB and the level goes up 2 to 3 LU. Jeremy gets 11 parts (the prototype found 3).

## Blocker and major findings

### B1 (blocker): hits.kick doubles most kicks when a bass note sounds with them
- **Location:** `src/mvh/stages/spectral/dsp.py` `select_hit_events` (weak path), `kick_confidence`, `dedupe_s=0.04`.
  Also `stage.py` `accept_weak`.
- **Claim:** PLAN §7 requires kick events with F1 ≥ 0.95 at ±10 ms. That fails on the most common pop/EDM texture, a
  sustained bass note under four-on-the-floor kicks, and on the contract fixture song itself.
- **Mechanism:** the weak-hit path (x ≥ 0.3, a ≥ 6 dB step) turns the kick-plus-bass beating 40 to 160 ms after each kick
  into a second "kick". `kick_confidence()` is evaluated inside the previous kick's click and decay, so it reads 1.0,
  and the 40 ms de-duplication is shorter than a kick. Many of these events carry `env` ≈ 0, meaning the curve shows no
  flash there.
- **Evidence:**

  | Case | Kick events | True kicks | Real viz hits | Score at ±10 ms |
  |---|---|---|---|---|
  | Kicks over a bass note (fixture kick, fixture gains) | 119 | 44 | ~55 | F1 0.54 (P 0.37, R 1.0) |
  | Same, bass 12 dB lower | 81 | 44 | — | P 0.54 |
  | Contract fixture song | 143 | 85 | — | P 0.55, R 0.93 |
  | Versatile (real song) | 350 | — | 212-227 | — |

  On the fixture song, 33 of the 58 extra events sit 20 to 200 ms after a real kick. The duplicates also move the
  fixture's decay tail Y001 start by 109 ms. The builder's tests miss this: they put bass notes off the kicks and
  assert only recall.
- **Tests:** `tests/review/M1/r-dsp/test_rdsp_kick_events.py::test_kick_events_over_a_bass_note_that_starts_with_the_kick`,
  `::test_kick_events_quiet_bass_note_still_doubles`, `::test_kick_events_on_the_contract_fixture_song`.
- **Suggested fix:**
  - Make a weak kick-band hit inherit viz's one-hit-per-note logic: require the 4 dB re-arm dip since the previous kick
    event, or a refractory gap of about 120 ms unless it is a stronger attack.
  - Evaluate `kick_confidence` relative to the level just before the candidate, not inside the previous kick's tail.
  - Drop events whose envelope value is 0.

### M1 (major): kick-free songs get a kick event on every piano note or snare
- **Location:** `spectral/stage.py` `_kick_gate` (decision M1-S4 'quiet-master' rule).
- **Claim:** the gate is `max(p95 - 30, min(-46, p95 - 20))`. It reads a normal-level song with no kick-band energy as a
  "quiet master" and drops the gate to about -90 dB. Every low-mid transient then becomes a kick event flagged
  `viz: true`, although viz itself registers 0.
- **Evidence:** a piano part (A3-E4) at -1 dBFS peak gives 37 kick events. Snares and hats give 18. Real viz gives 0
  for both. With PLAN §5's own gate `max(-46, p95 - 30)` (param `gate_margin_db=-1000`) the stage also gives 0 for both.
  All six CLI edge-case clips (at -23 LUFS) warn 'quiet master (-92 dB)'.
- **Test:** `test_rdsp_kick_events.py::test_no_kick_events_on_kick_free_material[piano|snare_hats]`.
- **Suggested fix:** decide "quiet master" from the song's overall level (sample peak or integrated loudness), not from
  the kick band. Keep PLAN's `max(-46, p95 - 30)` when the song is at a normal level, and compute the `viz` flag with
  viz's own -46 dB gate.

### M2 (major): a drop's role hint is lost when its impact boundary snaps to a mis-phased downbeat
- **Location:** `dynamics/stage.py` `segment_song` (impact boundaries snap within half a bar) and `role_hints` (an
  impact counts only within 0.6 s of the part start).
- **Claim:** SPIKE reports that the downbeat phase is wrong on 2 of 4 songs. When the grid is off by less than half a
  bar, the major impact that created a boundary ends up up to half a bar away from it, and the drop hint disappears.
- **Evidence:**
  - Real: Versatile's main drop impact at 50.96 s (bass -83 → -6 dB, +18 LU, `major: true`) snaps to the fixture
    downbeat at 51.72 s, and that part is hinted 'build'. Only the second drop (162.5 s) is hinted.
  - Synthetic: a breakdown into a drop at 28.0 s. With an in-phase grid the stage returns `drop` at 28.0. With the
    grid 0.9 s off, the part starts at 28.9 s with no hint, although the impact is found at 27.999 s.
- **Test:** `tests/review/M1/r-dsp/test_rdsp_dynamics.py::test_drop_hint_survives_the_downbeat_snap[0.9]` (`[0.0]`
  passes).
- **Suggested fix:** carry the boundary's source (its kind and the impact) into the Segment and credit that impact in
  `role_hints` regardless of the snap distance. Optionally snap major impacts only within a beat, and record
  `t_event` next to the snapped `t`.

## Minor findings (details in docs/review/M1-r-dsp.md)
| ID | Finding |
|---|---|
| m1 | Own true peak overshoots on EBU 3341 #17 and #18: -5.62 and -5.32 dBTP where -6.0 ±0.2 is expected (ffmpeg gives -6.0 and -5.9). PLAN says ffmpeg gives the true peak. |
| m2 | `hits.mid` and `hits.high` produce 2-4x the hits viz registers. On the fixture: hits.mid F1 0.37, hits.high F1 0.65. |
| m3 | Fixture impacts: P 2/5, R 2/3 (misses the chorus impact at 17.0). |
| m4 | The fixture build (25-32.5 s) is not separated, there is a false build hint at 5-9 s, and Jeremy gets a 96.8 s part. |
| m5 | A 'silence' part can report rel_lu of -11 LU (MEGAFAUNA, 94.6 s). |
| m6 | Dynamics crashes on inputs of 2 s or less. |
| m7 | CR-M1-1 (allin1 fallback unreachable) is confirmed. |
| m8 | vizState onsets equal viz at 100 fps, not 60 fps (needs documenting). |
| m9 | The contract's spectrum128 round-vs-truncate wording (≤ 1 LSB). |
| m10 | Blackman STFT band leakage in the physical dB bands. |
| m11 | Mono reads 3 LU below stereo (BS.1770; document it). |
| m12 | A misleading 'quiet master' warning on normal songs. |

## Files (all owned by r-dsp-m1)
- `tests/review/M1/r-dsp/conftest.py`, `rdsp_m1_support.py` (causal analyser frames, Node driver, signals, F1),
  `viz_causal.cjs` (real viz under Node).
- `test_rdsp_kick_events.py` (B1, M1: 5 failing), `test_rdsp_dynamics.py` (M2: 1 failing, 1 passing control),
  `test_rdsp_viz_parity.py` (passing guard). The suite runs in about 40 s and is ruff-clean.
- `docs/review/M1-r-dsp.md` (minor findings), `docs/build/progress/r-dsp-m1.md`, scratch in `out/_wip/r-dsp-m1/`.

## Gate
Steps reached at hand-off: unit FAIL (only `tests/unit/contract::test_stub_files_are_stubs`, not M1; spectral, loudness and dynamics pass), review FAIL (the intended r-dsp failures), ruff FAIL (other modules' tests, e.g. M3b; `tests/review/M1` is clean), contract PASS, validate PASS. The e2e and determinism steps were still running (other modules' heavy stages queued for slots); log in `out/_wip/r-dsp-m1/gate1.log`.
