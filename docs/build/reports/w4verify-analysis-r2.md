# w4verify-analysis-r2: W4 independent verifier, analysis group (M1, M2, M3a, M3b, M4), round 2

Full review: docs/review/W4-verify-analysis.md (round-2 section on top). Progress log: docs/build/progress/w4verify-analysis-r2.md.
Numbers and lyric ids only.

## Verdict: fail

The three round-1 findings are fixed:
- **W4V-GAIN-REAL: fixed.**
- **W4V-GAIN-BEATS: fixed.**
- **W4V-KICKCURVE-CHOREO: fixed.** The round-1 test was too strict, and I have corrected it.

Fresh runs found one blocker, three majors and three minors (below).

## Round-1 findings
- **W4V-GAIN-REAL, W4V-GAIN-BEATS: fixed.**
  - Checked against the fixer's baselines on four pairs:
    - three fresh full analyses: MEGAFAUNA -20 dB, Versatile -12 dB, Jeremy -6 dB;
    - the fixer's re-analyses of MEGAFAUNA and Jeremy at -12 dB.
  - On every pair these are identical: section starts and labels, EDM roles, silences, feel, key, chords, beats and bars (F 1.000).
- **W4V-KICKCURVE-CHOREO: fixed.** The check ran with `kick_source = mix` on MEGAFAUNA, Versatile and Jeremy.
  - Groove kick steps on an agent kick: 0.98 / 1.00 / 1.00.
  - Every `drum` hit point without an agent kick has a stem snare of vel 0.65-1.0. That is a valid `drum` kind: UD2 rejected only
    the stem kick.

## New findings

| ID | Sev | Module | One line | Test |
|---|---|---|---|---|
| W4V2-HARMONY-NAN | blocker | M4 harmony | Crashes on synth at atempo 1.05 (2 ms trailing N segment after the last chroma frame, so an empty-slice mean gives a NaN conf and the JSON write raises). analyze rc 1, 12 stages not run. The bug predates W4-AN-9: it also fails with `analysis_lufs` null | test_w4va2_harmony_tail_crash.py |
| W4V2-GAIN-DRUMS | major | M3a separate_hq/drums | DrumSep runs on the master-level drum stem (normalisation off). The UD2 agent kick changes with level: Versatile -12 dB loses 6 strong kicks to toms; MEGAFAUNA gains 5 / 9 strong kicks at -12 / -20 dB; strong cymbals F 0.44 (Versatile) | test_w4va2_level_and_labels.py::test_w4va2_agent_kick_and_drum_hits_survive_a_gain_change |
| W4V2-GAIN-STEMACT | major | M3a stem_activity | Absolute `active_db` -45 dBFS. MEGAFAUNA drums_kick active 0.544 -> 0.406 at -12 dB; Versatile bass 0.856 -> 0.792 | ...::test_w4va2_stem_activity_survives_a_gain_change |
| W4V2-GAIN-VOCALS | major | M3b vocals | Absolute `level_floor_db` -55 dB. Vocal notes: MEGAFAUNA 33 -> 15 / 8 (-12 / -20 dB), Versatile 27 -> 13. Phrase coverage: Versatile 6.1 -> 2.1 s | ...::test_w4va2_vocal_notes_and_phrases_survive_a_gain_change |
| W4V2-GAIN-SPECTRAL | minor | M1 spectral | Absolute `gate_db` -46. Strong hits.mid / hits.high / onsets F 0.65-0.90 at -12 / -20 dB; hits.kick holds | ...::test_w4va2_spectral_onsets_and_hits_survive_a_gain_change |
| W4V2-JEREMY-HOOK-VERSE | minor | M2 structure | 176.12 s section (only lyric group T11, which is in 6 choruses) is now `verse` (W3: chorus) | ...::test_w4va2_a_section_holding_only_the_chorus_hook_is_not_a_verse |
| W4V2-FORMRULE-NARROW | minor | M2 structure | W4-AN-11(d) needs allin1 verse >= 0.25 (fitted to sr32's 0.36). At 22.05 kHz verse is 0.15 and the verse stays `chorus` | test_w4va_perturbations.py::test_w4va_synth_sections_survive_other_edits[synth_sr22] |

**Why the level dependence is not run-to-run noise:** a fresh synth_base equals the fixer's synth on every output. Restored to the
original level, the gain copies' ROFormer stems match at 33-36 dB SDR, but the DrumSep toms and crash only at 9-13 dB SDR. The
vocals, stem_activity and spectral gates are absolute dB constants.

## W3 open items (analysis group)
| Item | Status |
|---|---|
| S06 | Choreo now follows `kick_source`. The agent kick is still level dependent (W4V2-GAIN-DRUMS). |
| S17 | Passes (MEGAFAUNA 18 groove ids / 63 bars, Versatile 16 / 72). |
| S18 | Passes. |
| S19 | Passes (critic 18/18 on the fixer's folders). |
| m3 | Resolved (voice change 69.44 s vs section 69.64 s). |
| S16, Newton lyrics, m4, m5 | Outside this group. |

## Runs (out/_wip/w4verify-analysis-r2)
- **Fresh `--profile max` runs:**
  - analyze 0 / validate 0: megafauna_gm20, versatile_gm12, jeremy_gm6, synth_base, synth_sr22;
  - synth_tempo105: analyze 1 (the blocker).
- **How to run them:** `powershell -File out/_wip/w4verify-analysis-r2/run_queue.ps1 -NameList a,b`. It is resumable; done markers
  are in `logs/<name>.done.json`.
- **Tools:**
  - `cmp.py`: sections, EDM roles, F per event lane, silences, feel, grooves, chords;
  - `drumdiff.py`, `vocdiff.py`, `curvediff.py`;
  - `kickmix.py` (drums with kick_source=mix, then choreo);
  - `phase.py` (bar-phase evidence).

## Tests (tests/review/W4/verify-analysis; I own all of them)
- **Updated:**
  - `w4va_support.py`: defaults RUNS=out/_wip/w4verify-analysis-r2 and BASE=out/_wip/w4fix-analysis-r2; `GAIN_PAIRS`;
  - `test_w4va_perturbations.py`: gain pairs; synth_tempo105 and synth_sr22 added;
  - `test_w4va_kick_mix_choreo.py`: 3 songs, accepts a stem snare.
- **New:**
  - `test_w4va2_level_and_labels.py`;
  - `test_w4va2_harmony_tail_crash.py`;
  - `w4va_devchain.py`.
- **Final sweep** (`.venv/Scripts/python.exe -m pytest -q tests/review/W4/verify-analysis -m "slow or not slow"`, MVH_OFFLINE=1):
  22 failed, 40 passed, 1 skipped. Every failure is one of the findings above.
- **Other checks:**
  - unit tests of allin1, rhythm, dynamics, structure, choreo, harmony, loudness and drums: 201 pass;
  - ruff is clean;
  - W3 critic on the fixer's r2 folders: 18/18 pass.
