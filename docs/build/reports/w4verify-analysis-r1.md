# w4verify-analysis-r1: W4 verifier, analysis group, round 1

The full review is in docs/review/W4-verify-analysis.md. The progress log is docs/build/progress/w4verify-analysis-r1.md.
Numbers only; no lyric text.

## Result
- **Fixed:** W4A-STABLE, W4A-ACAP, W4A-VOCPHR, W4A-S17 / S17, W4A-S18 / S18 (on Newton) and W4A-S19 / S19. The fixer's
  review tests pass on its folders. My new edits also pass on the synthetic song (1.1x and 0.95x tempo, 32 kHz), and so
  do a fresh synth run and a real rap a cappella.
- **NOT FIXED: W4A-GAIN (N1, major).** The new allin1 level band [-16, -6] LUFS leaves the synthetic song's input the same
  only because the synth is below the band. Real masters are inside the band: at -12 dB, MEGAFAUNA loses 5 section
  starts, gains 4, and gets a new `silence` section, partly from the absolute -45 LUFS cap on dynamics silences. Jeremy
  loses a boundary and its bridge becomes chorus.
- **New major N1b:** the rhythm beat and downbeat grid is level-dependent on real songs. MEGAFAUNA at -12 dB: beat F
  0.665, downbeat F 0.60; beat_this and madmom change BPM.
- **Partly fixed: W4A-KICKCURVE (N2, major).** The curve is fixed, but under `kick_source = mix` choreo still builds its
  grooves, accents and drum hit points from the rejected stem kick.
- **Minors:**
  - N3: the synthetic a cappella has a half_time feel of 0.177, via the allin1 band;
  - N4: spurious half-time spans with no snare backbeat (MEGAFAUNA 89-100 s, Versatile's outro).

## Tests (tests/review/W4/verify-analysis/; 8 fail, 15 pass)
- test_w4va_perturbations.py:
  - real-song -12 dB sections: N1, fails for megafauna and jeremy;
  - beat grid: N1b, fails for megafauna and jeremy;
  - EDM roles at -12 dB: pass;
  - synth edits, real a cappella, reproduce: pass;
  - a cappella feel: N3, fails for fixer_synth_acap.
- test_w4va_kick_mix_choreo.py: N2, fails (runs the real drums and choreo stages, about 15 s, `slow`).
- test_w4va_real_seams.py: N4, fails for megafauna and versatile; passes for newton.
The tests skip when the run folders are absent. `W4VA_RUNS` and `W4VA_BASE` redirect them.

## Runs (out/_wip/w4verify-analysis-r1; resumable: `run_queue.ps1 -NameList ...`)

| Run | Seconds | analyze / validate |
|---|---|---|
| synth_base | 1224 | 0 / 0 |
| megafauna_gm12 | 1491 | 0 / 0 |
| newton_acap | 1281 | 0 / 0 |
| jeremy_gm12 | 1360 | 0 / 0 |
| synth_tempo110 | 628 | 0 / 0 |
| synth_sr32 | 415 | 0 / 0 |
| synth_tempo95 | 327 | 0 / 0 |

Tools:
- probe.py: per-folder numbers (sections, EDM roles, feel, snares by feel, grid shares, grooves, phrases, hit points);
- breaths.py: lead-stem dips inside long phrases;
- devrun.py: run_stage chaining on cached upstreams; outputs in dev/<tag>.
