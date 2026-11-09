# fixer-m1-r2 progress
- Baseline measured (scratch scripts in session scratchpad). Plan: replace kick event selection (select_kick_events in dsp.py) by
  low-band own-attack evidence: low step LS>=7 dB, excess (post-peak minus previous 60 ms max of low env) >= 4.5 dB, plus low-step
  candidates outside viz episodes needing click >= 20 dB. Drop refractory/click-weight params. Then real-song counts, gate, report.
- Implemented dsp.select_kick_events (viz episodes timed on low-band step via refine gate; refractory 0.2 s needs own attack ls>=6.5 & ex>=3.5;
  step-only candidates need click>=20). Params in spectral/__init__.py. Synthetic: hats/crash/double OK; fixture song stuck ~0.84 (bass-line onsets vs kicks).
  Real stems (Jeremy recall .97). Next: fixture attempts if cheap, update unit tests (tests/unit/spectral), run gate, write report + M1 decisions.
- Added pitch-drop evidence (dsp.kick_glide, glide_signal): weak hits need it; low-band steps with click+strong drop are kicks; roll rule for
  step-only candidates; refractory 0.2 s needs the low band's own attack. Synthetic: hats 0.99, crash 1.0, doubles 1.0, kicks_over_bass 0.99;
  fixture song stuck ~0.86 (bass-note onsets with hats), groove-with-bass recall 0.8. Real: Jeremy stem recall .97.
  Next: fix unit tests that encode old behaviour, run gate, report.
- gate run: M1 review 14/16 (2 fixture-song kick tests fail), unit contract + determinism fail from other modules. Report written.
