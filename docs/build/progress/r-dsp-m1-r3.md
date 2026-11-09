# r-dsp-m1-r3 progress (round 3 reviewer, M1 Signal, lens R-DSP)

## Done
- started; prior material: docs/build/progress/r-dsp-m1-r2.md, tests/review/M1/r-dsp/test_rdsp_r2_kicks.py.

## Next
- verify B1-R2, R2-M1, R2-M2 (read code); regressions; new findings.

## Milestone 1 (verification; probes in out/_wip/r-dsp-m1-r3/)
- review suite: 14 pass, 2 fail (fixture-song kick tests r1 + r2): F1 0.864 (P .835 R .894), worse than r2 0.880.
- root cause on fixture: bass-NOTE onsets (truth notes.bass, 100 ms before kicks, hat on top) are emitted as kicks (viz True)
  and the kick after them is dropped by the 0.2 s refractory (ex < 3.5 over the sustained bass). dbg_fix.py.
- kick_glide separates: fixture kicks median 1.88, bass onsets 0.48-0.8 (one 1.61). Docstring promises glide_song + refractory
  override; NOT implemented. probe_glide_song.py / probe_glide_combo.py: veto helps straight bass (0.88->0.98) not fixture.
- NEW regression: builder groove() with bass: F1 0.754 (R .73 P .78), seed3 .739, straight 4otf+offbeat bass .88 (P .786);
  unit-test bar lowered 0.85->0.7 by fixer. Bass-note extras have kick_conf 1.0. probe_groove*.py
- R2-M2 narrow: dbl 150 ok, 170 R .81, 180 3/96, 200 1/96, 160 fixture-kick 24/96, 160 under crash 42/96 (probe_r3.py).
- 16th bass riff under 4otf: 1 bass onset per bar (G1 jump) emitted as kick, F1 .889 (probe_r3.py).
- R2-M1: crash 130/150 pass; real3.py: dropped viz hits on versatile/jeremy/newton have ~0 kick-stem rise (justified); megafauna inconclusive.
## Next
- run opt-in real tests (bg), write failing tests tests/review/M1/r-dsp/test_rdsp_r3_kicks.py, quick look at loudness/dynamics regressions.

## Milestone 2 (tests written)
- tests/review/M1/r-dsp/test_rdsp_r3_kicks.py (+ bass_riff_kicks in rdsp_m1_support.py): 9 FAIL as intended
  (groove x3, 16th riff, dbl 170/180/160-crash, rock 8ths over held bass 140/160). ruff clean.
- real opt-in tests (Jeremy stem recall, real counts with fixer's loosened bar) PASS; realdyn.log: megafauna drops 96.1/141.6 (+28.7), dynamics ok.
- rates: 48/96 kHz and mono same as 44.1. 8ths under crash 170/190 ok.
## Next
- minors to docs/review/M1-r-dsp.md (Round 3), report, StructuredOutput. (gate optional, run in bg)

## Milestone 3
- Round 3 minors m16-m19 appended to docs/review/M1-r-dsp.md; report docs/build/reports/r-dsp-m1-r3.md written (gate section pending).
- gate running in bg: out/_wip/r-dsp-m1-r3/gate.log (unit contract fails on rhythm stub test: other module).
## Next
- finish gate section of report, StructuredOutput.

## Milestone 4 (after power-outage restart)
- gate.log read: e2e/determinism interrupted (heavy-slot wait, then outage); review failures 11 = intended set; unit contract
  failure is the rhythm stub test (M2). Report gate section written. DONE: only StructuredOutput remained.
