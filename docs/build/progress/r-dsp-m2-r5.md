# r-dsp-m2-r5 progress (independent reviewer round 5, M2 Rhythm, lens R-DSP, W3 verify)
## Done
- started; target: verify F7-r4 (fixer-m2-r4: phrase_layout() in structure, remainder-first pickup by global section-start grid support).
## Next
- run review/unit/integration tests; rerun 2+ real songs; probe phrase_layout heuristic (positional bias?).
- tests: review M2/r-dsp default 75p/13s (with unit), -m real 6 passed (F7-r4 test passes). tests/integration/M2: 2 fail ONLY because integrator outputs (05:10) are stale (pre-r3 fix).
- F7-r4: Jeremy fixed (counts 21.80 grid). Code read: phrase_layout() is a GLOBAL vote of all other section starts -> position-biased, can't tell pickup from trailing extra bar.
- PROBE p_grid.py (synth fixture): adding a user boundary at 42.5 s (split last chorus) flips the BRIDGE (25.0) phrasing to 1+4 -> bridge counts 25.0/4p, 27.0/8, 31.0/7p vs truth 25.0/8, 29.0/7p, 32.5/4p. => NEW MAJOR F8-r5 (non-local phrase grid). Writing test tests/review/M2/r-dsp/test_phrase_grid_nonlocal.py
- real reruns running in bg: out/_wip/r-dsp-m2-r5/all.log -> out/_wip/r-dsp-m2-r5/real/<slug>{,_det}
- test_phrase_grid_nonlocal.py: 1 fail (stated reason), precondition passes (10 s).
- real reruns all 5 songs: identical to fixer-m2-r4 re-run + deterministic (probes/cmp.py). Jeremy F7-r4 FIXED (E005 19.47 partial, E006 21.80...).
- review doc Round 5 appended (r5-m1..m4). NEXT: report + StructuredOutput.
- report written docs/build/reports/r-dsp-m2-r5.md. DONE except StructuredOutput.
