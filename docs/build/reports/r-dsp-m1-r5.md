# r-dsp-m1-r5: R-DSP review round 5 of M1 Signal (W3 verify after fixer-m1-r4)

Verdict: **fail**. 0 blockers, 4 majors (3 re-raised from round 4, 1 new regression). Minors m25-m28 are in
docs/review/M1-r-dsp.md "Round 5".

## What I ran
- Review M1 suite plus the M1 unit tests (before my tests): 117 passed, 12 skipped, 1 xfailed (3 min 42 s). The round-4
  tests (`test_rdsp_r4_kicks.py`) all pass.
- Variants around every round-4 finding (`out/_wip/r-dsp-m1-r5/probe_vars.py bass|duck|quiet`, `probe_bed.py`,
  `probe_quiet3.py`), with evidence dumps per truth kick (`dbg.py`).
- Kick-free textures for the new routes (`probe_fp.py`, `fp_routes.py`).
- Re-ran spectral, loudness and dynamics on copies of the integrator's MEGAFAUNA and Jeremy folders
  (`out/_wip/r-dsp-m1-r5/<slug>`, `rerun.ps1`). hits.kick for MEGAFAUNA is byte-identical to fixer-m1-r4's output. Dynamics
  and loudness are the same as the fixer's.
- Real-song analyses: `mega_ev.py` (mix evidence at the missed strong DrumSep kicks) and `kick_prec.py` (stem evidence at
  every hits.kick event).
- Edge cases: `out/_wip/r-dsp-m1-r4/probe_edges.py` (22.05/48/96 kHz, mono, a kick at t = 0, silence, noise): all pass.
- `tests/integration/M1` (S06): still fails. It reads the integrator's pre-fix folder, so it fails at 0.42.

## Findings (blocker / major)
Every one has a failing test in `tests/review/M1/r-dsp/test_rdsp_r5_kicks.py` (signals in `rdsp_r5_signals.py`). All
11 cases fail for the stated reason. ruff is clean.

### R5-M1 (major; R4-M1 not fixed): the new 808 and click routes pass only at the tested point
- **Location:** `src/mvh/stages/spectral/dsp.py` `kick_route`, the "808" route (`s808_glide` 1.2) and the "click" route
  (`cb_click_db` 15).
- **Evidence:** the round-4 mix (4-on-the-floor, 8th hats, held bass):

  | case | F1 |
  |---|---|
  | TR-808, bass 0.5, 120 BPM (the tested point) | 0.968 |
  | TR-808, bass 0.5, 100 BPM | 0.809 |
  | TR-808, bass 0.5, 140 BPM | 0.567 (R 0.40) |
  | acoustic, bass 0.7 (named in the R4 evidence) | 0.829 (R 0.71) |
  | acoustic, bass 1.0 | 0.545 |
  | acoustic, bass 0.5 + a lead chord 19 dB below the kick | R 0.58 |
  | fixture kick (sweep route), bass 0.5 + the same lead chord | 1.0 |

  - The 808 misses read a pitch drop of 1.04-1.12 (below 1.2) and are centred at 61-65 Hz (below the body route's 68 Hz).
    Their kick_conf is 0.64-0.69.
  - The click route needs a 15 dB click over the 50-10 ms before the kick. Only the empty 1.5-5 kHz band of the synthetic
    mixes gives that: 20-60 dB there, against 1-5 dB at real kicks.
- **Test:** `test_r4_kick_designs_over_a_held_bass_at_other_tempos_and_levels[tr808-100bpm-bass0.5, tr808-140bpm-bass0.5,
  acoustic-120bpm-bass0.7]` and `test_acoustic_kick_over_a_held_bass_with_a_quiet_lead_chord`.

### R5-M2 (major; R4-M2 / seam S06 not fixed): the duck route needs a click that real drops do not have
- **Location:** `dsp.py` `kick_route` "duck" route (`duck_click_db` 15, `glide_strong` 1.6), and M1-S13 / CR-M1-6.
- **Evidence, synthetic:** the round-4 duck mix passes alone (F1 1.0). With the same quiet lead chord:
  - TR-909 kick: R 0.04;
  - fixture kick: R 0.67.

  A clickless TR-808 kick under the duck scores R 0.02 even without the chord.
- **Evidence, real songs:** the duck route fires once on MEGAFAUNA and the click route 3 times (`manifest.json` hits.kick
  routes). On Jeremy, Versatile and Newton both fire 0-1 times.
  - MEGAFAUNA's strong DrumSep kicks (vel >= 0.5, n = 165) matched by hits.kick: 0.22 (0.21 in round 4).
  - At the 129 misses, mix evidence p10/50/90:
    - attack: -1.9 / 2.0 / 7.1 dB;
    - click: -2.6 / 1.2 / 4.7 dB;
    - low_ex: -1.4 / 0.4 / 2.4 dB.
  - The misses fall at 100-220 s (the drops).
- **Consumer rule:** M1-S13 now says to cut on drum_hits vel >= 0.5 rows. That is right, but its fallback ("plus
  hits.kick with kick_conf >= 0.5 and no row within 30 ms") adds about 116 non-kick events on MEGAFAUNA (m27).
- **Test:** `test_ducked_sub_with_a_quiet_lead_chord[tr909, fixture]`.

### R5-M3 (major; new, regression from fixer-m1-r4): the click route turns kick-free low onsets into kicks
- **Location:** `dsp.py` `kick_route` "click" route: click >= 15, attack >= 3.5, low_ex >= 3, body_ex >= 4.5,
  body_add >= 3, with no pitch-drop or decay condition.
- **Evidence:** kick-free mixes at 124 BPM, 12 bars:

  | mix | false kicks | from the click route |
  |---|---|---|
  | a pluck (filter-envelope) bass on every 8th with a closed hat on each note | 50 | 38 (12 by sweep) |
  | low piano chords on each beat (left hand A2) | 21 of 48 chords | all |
  | a snare on 2 and 4 that starts a new held bass note | 7 of 24 snares | all |

  - A low-band onset with any 1.5-5 kHz transient satisfies the route.
  - The round-1 kick-free tests (a piano at A3-E4, snare + hats) have no low-band onset, so they still pass.
- **Test:** `test_no_kicks_on_kick_free_low_onsets_with_a_click[pluck_hats, piano_low, snare_bass]` (bound <= 2, as in
  `test_rdsp_kick_events`).

### R5-M4 (major; R4-M3 half fixed): quiet-section kicks still judged against the song's median kick
- **Location:** `dsp.py` `select_kick_events`, step 4: `ev.body_db >= gref - rel_db or ev.conf() >= quiet_conf`
  (`kick_quiet_conf` 0.7).
- **Evidence:** a quiet intro (bars 0-3 at -14 / -20 dB, the rest at full level):

  | kick | intro recall | loud part | intro recall with kick_quiet_conf = 0 |
  |---|---|---|---|
  | fixture / 909 (sweep route, conf ~1) | 16 / 16 | 1.0 | 16 / 16 |
  | TR-808, -20 dB, no bass | 0.75 | 1.0 | 1.0 |
  | acoustic over a bass, -14 dB | 0.875 | 1.0 | 1.0 |
  | TR-808 over a bass, -14 dB | 0.25 | 0.917 | 0.81 |

  The 808 and click routes give kick_conf 0.4-0.69, so their kicks in a quiet section are dropped.
- **Test:** `test_quiet_intro_kicks_of_other_designs_are_kept[tr808-intro-20dB, acoustic-over-bass-intro-14dB]`.

## Suggested fixes (for the fixer)
- **Click evidence:** measure it against the band's local background (a click-to-background ratio, or a spectral-flux
  step above the band's running median), not against the 50-10 ms before. Add a sustained bright bed
  (`rdsp_r5_signals.with_bed`) to the unit mixes so that thresholds are not tuned on an empty band.
- **Click route:** require kick evidence a pluck, a piano or a snare-plus-bass lacks:
  - a pitch drop >= 1.1;
  - or a 30-80 Hz rise at least as large as the 150-400 Hz rise;
  - or a decay of the added energy, measured after subtracting the pre-onset power, as GlideMeter does.
- **808 route:** do not hang on one 1.2 pitch-drop threshold. Use the added-energy decay (pre-onset power subtracted)
  and a 50-90 Hz body step, and test it at 90-150 BPM.
- **Quiet sections:** drop the song-global `gref` condition, or make it local (the median body of the accepted kicks
  within +-8 s).
- **Sidechained drops:** accept that the mix alone cannot see them. Keep M1-S13 / CR-M1-6 (drum_hits strong rows),
  but restrict its hits.kick fallback (m27).

## Other checks
- **Earlier minors:**
  - m20 fixed: a kick at t = 0 is found.
  - m23 fixed: role_score <= 1 in every rerun.
  - m22 still open: 43 Jeremy hits.kick are snares by the stems.
  - m24 still open: the S06 test reads the pre-fix folder.
- **Dynamics:**
  - MEGAFAUNA has 12 parts, with drop hints at 96.1 s (1.0) and 141.8 s (0.918). The weak 28.7 s hint is gone; allin1
    and edm_roles have no drop there.
  - Jeremy has 13 parts and keeps its 19.5 s drop. Its outro fade is flagged as breakdown 1.0 (m26).
- **Loudness:** meta identical to the fixer's and the integrator's on both reruns.
