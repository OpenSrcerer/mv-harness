# critic-w3 progress
## Done
- (start) read BUILD-STATUS
## Next
- read PLAN, SPIKE, CONTRACT, SEAMS, integrator outputs; build matrix; write tests
- probes written: out/_wip/critic-w3/{probe,deep,phase,hat,overlap,lyricat,singer}.py (+ jsprobe.mjs/pyprobe.py parity); outputs *.txt there
- findings so far: grooves ids ~1 per bar on real songs + syncopation ~0 (M2 choreo); Jeremy hihat off-grid (M3a); rap line overlap 1.4 s -> two singers at hand-offs (M5 lyrics sustain); JS/Py parity OK on real folders
- R19 round-trip experiment: copied synth folder to out/_wip/critic-w3/rt-synth
- more findings: Newton feel 'normal' while 76% strong snares on beat 3 (half-time; Versatile 50%) -> M2 rhythm feel; licences OK in run.json+provenance (5 'unclear' sep/demucs, known); JS/Py parity OK; brief --section OK
- R19 round trip: rt_step.ps1 step1 (intent+authored copied from fixture) running in background; then step2 = overrides.json structure edit
- tests written (tests/review/W3/critic): conftest.py, w3c_support.py, test_w3c_grooves.py (W3C-1/2), test_w3c_feel.py (W3C-3), test_w3c_hats.py (W3C-4), test_w3c_handoffs.py (W3C-5). 14 fail as intended, 2 pass (controls). Run: scripts/run.ps1 python -m pytest -q tests/review/W3/critic -p no:cacheprovider
- docs/review/W3-completeness.md drafted (sections 1,2,4); section 3 placeholder waits for rt step2 (out/_wip/critic-w3/rt-step2.log); then run mvh frames on rt-synth
- R19 round trip DONE on rt-synth: works (only structure+downstream re-ran, label+move applied, meaning re-anchored 3 claims, no orphans) BUT the untouched 25.0 boundary moved to 29.0 -> W3C-6 (M2 structure DP re-optimises globally); test_w3c_override_locality.py (real-upstream variant fails, fixture variant passes)
- mvh frames on rt-synth OK (24_f1fps.csv 1356x40, no NaN); SKILL names it 24fps.csv (m7)
- DONE: docs/review/W3-completeness.md complete; tests 15 fail/3 pass; ruff clean; report docs/build/reports/critic-w3.md written. Next: StructuredOutput only.
