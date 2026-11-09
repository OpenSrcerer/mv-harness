# r-dsp-m1-r4: R-DSP round 4 (W3 verify) of M1 Signal, after fixer-m1-r3

Verdict: **fail**. The four earlier R-DSP kick findings are fixed. S06 is not resolved, and the new kick selector has two
new majors.

## Runs
- Review suite plus the M1 unit tests (`tests/review/M1/r-dsp`, `tests/unit/{spectral,loudness,dynamics}`): 99 passed,
  12 skipped. The new round-4 tests are `tests/review/M1/r-dsp/test_rdsp_r4_kicks.py`: 6 fail as intended.
- Real songs:
  - `rerun.ps1` re-ran MEGAFAUNA in `out/_wip/r-dsp-m1-r4/megafauna`. hits.kick and meta/dynamics.json are byte-identical to
    the fixer's run, so the result is reproducible.
  - The newton re-run was stopped after its spectral step, while waiting for a heavy slot.
  - `dyn_harness.py` (in-process, using the integrator's bars) ran on MEGAFAUNA and newton. Loudness, impacts, silences and
    stops are identical to the integrator's.
  - MEGAFAUNA loses the weak 28.7 s drop hint (score 0.74). This is not a finding: allin1 / edm_roles have no drop there,
    and the impact is only 1.7 LU.
- Loudness and dynamics code are unchanged since W2 (file times 03:47).

## Earlier findings
| id | status | how verified |
|---|---|---|
| B1-R2 | fixed | fixture song F1 0.98; the review tests pass |
| R3-B1 | fixed | groove default / seed 3 / four-on-the-floor, and the 16th riff, pass; the unit bar is back at 0.95 |
| R2-M1 | fixed | rock pairs over a held bass at 120, 140, 160 and 170 BPM: 1.0 |
| R2-M2 | fixed | 16ths at 160-220 BPM (tight kick, with or without a crash) 1.0; the fixture kick at 180 BPM under a crash: 0.927 (minor m21) |
| S06 | **not fixed** | R4-M2 below |

## Majors (failing tests in tests/review/M1/r-dsp/test_rdsp_r4_kicks.py)
- **R4-M1. Kick designs other than the fixture's over a held bass note.**
  - The rules were tuned on one synthetic kick (tests/synth/dsp.kick).
  - Over the kicks_over_bass texture (bass 0.5): acoustic F1 0.588 (R 0.417); TR-808 F1 0.551 (R 0.396). Eight 808
    events land 11-21 ms *before* the kick.
  - With bass 0.7: acoustic R 0.083.
  - Without the bass, every design scores 1.0. The fixture, 909, distorted, low-tuned and trap-808 kicks pass with the bass.
  - Cause:
    - the body route's `decay >= 8 dB` and `f_early >= 68 Hz` are measured on the total band, and the held bass cannot
      decay;
    - the sweep route needs a sweep that starts above ~150 Hz.
  - Evidence at the misses: acoustic attack 4-9 dB, click 24 dB, body_ex 7-9 dB, decay 4-5 dB.
- **R4-M2 (S06 re-raised). Sidechain-ducked sub bass (EDM drops).**
  - The `adds low-band energy` rule rejects obvious kicks (attack 7.4 dB, glide 2.2, click 48.6 dB) because the duck
    removes as much low energy as the kick adds (low_ex -3.4 / body_ex -2.5 / body_add -1.5 dB).
  - Synthetic results: fixture kick F1 0.667 at bass 0.7 and 0.0 at bass 1.0; 909 F1 0.118.
  - MEGAFAUNA: strong DrumSep kicks (vel >= 0.5, n = 165) are matched by hits.kick at 0.21 (0.27 before the fix).
    - At the 131 misses, the drums stem rises 11.4 dB in 30-150 Hz while the bass stem falls 8 dB, so the mix is flat.
    - The misses are mostly at 140-220 s (the drops).
  - So the M1-S13 precedence rule "cut on hits.kick" is wrong exactly where it matters. The fixer's "hat bleed"
    explanation covers only the low-velocity DrumSep rows.
- **R4-M3. Quiet sections lose all kicks.**
  - `kick_rel_db = 12` is relative to the global median kick body.
  - A 4-bar intro at -14 dB: 0 / 16 kicks (16 / 16 with `kick_rel_db = 60`).
  - A fade-out: bars at -12 dB 2/4, at -18 dB 0/4.
  - The pre-fix viz path used a centred ±8 s reference. This rule is new, so it is a regression.

Suggested fixes:
- Measure body / decay / f_early on the energy the onset **adds** (GlideMeter already subtracts the pre-onset power).
- Accept a strong swept attack or a strong click with a low-band burst even when the net low-band energy does not rise (the sidechain case).
- Make the faint-thump filter local (±8 s median, as the hit reference).
- Add these signals to the unit tests.

## Minors
m20-m24, in docs/review/M1-r-dsp.md (Round 4):
- m20: a kick at t = 0 is never a candidate.
- m21: the fixture kick in 16ths at 180 BPM under a crash scores F1 0.927.
- m22: on Jeremy, 10 % of hits.kick are snares (kick_conf 0.61 passes M1-S13's 0.5 cut).
- m23: dynamics `role_score` reaches 1.2, against the declared 0..1 (newton, Versatile).
- m24: the S06 integration test reads stale integrator output.

## Probes
All are in `out/_wip/r-dsp-m1-r4/`:
- kick designs and signals: `kinds.py`, `probe_kinds*.py`, `dbg_kinds.py`, `dbg808.py`;
- quiet sections: `probe_quiet*.py`;
- sidechain: `probe_duck.py`, `dbg_duck.py`;
- edge cases and rolls: `probe_edges.py`, `probe_rolls.py`, `dbg_t0.py`;
- real songs: `s06.py`, `mega_strong.py`, `jeremy_snare.py`, `dyn_harness.py`.
