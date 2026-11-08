# r-words-m5-r2 progress (round 2 reviewer, M5 Words, lens R-WORDS)

## Done
- started fresh; round-1 artifacts: out/_wip/r-words-m5/scripts, tests/review/M5/r-words/*

## Next
- verify fixes A, A2, B, C, D, E (code read + run tests + probe beyond tests); then hunt regressions

## Commands
## Gotchas
- 1: round-1 tests: 15 passed (fixes claimed for A,A2,B,C,D,E). batch1.sh running (synth-lines/txt/shifts, real jeremy/newton)
  -> out/_wip/r-words-m5-r2/*.log, status in batch1.status. scripts copied to out/_wip/r-words-m5-r2/scripts
- B NOT FIXED: _file_labelled treats LRC ID tags ([ar:],[ti:],[length:],[offset:]) as speaker headers -> labelled;
  also "[Guitar Solo]"/"[Sax Break]" headers become speaker hints. test_rw5_r2_speaker_labels.py (5 fail, 1 guard pass)
- NEW major: _asr_repair moves A's last word onto B's first word (LCS pairs a missed repeated word), no neighbour clip,
  crossings counted before repair. test_rw5_r2_asr_repair_duplicates.py (1 fail, 1 guard pass)
- NONLYRIC over-broad ("see you next", whole-segment "bye bye bye") -> candidate minor; 0 drops on real jeremy/newton ASR caches
- TODO: group-window floor t0 >= prev group end - 0.15 clamps early-sung group-first lines (probe on real + synthetic)
## Commands
- MVH_SKIP_MODELS=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/review/M5/r-words/<file>
- bash out/_wip/r-words-m5-r2/scripts/batch1.sh (background)
- 2: A verified on synth (line-only LRC + shifts +2.5/-4.0: median 20 ms, max 0.46, no crossings, offsets ok). A2 ok (MIN_CTX_S floor).
  NEW major (C regression): NONLYRIC drops sung lines mid-song ("see you in the next life", "please share", "bye bye bye")
  -> test_rw5_r2_hallucination_overreach.py (4 fail, 3 guard pass)
  seam clamp probe: pure probe_seam_clamp2.py (distinct text, group-first line sung 0.5 s early -> group garbage, no flag);
  real jeremy only line 38 differs (probe_seam_jeremy.log). batch2.sh running synth-jit-{seam,mid,seam7} (LRC jitter +0.5 at L009 seam)
- 3: batch1+2 done. A/D fixed on jeremy (0 crossing word starts; L037 no duplicate). seam clamp: synth jitter runs fine
  (crossing repair rescues) -> minor only. NEW majors: newton grade B->C (G2 .683, G4 .198) caused by MIN_CTX_S=6
  (probe_ctx2_newton-vs-nye.log: timing vs ASR unchanged, scores shift; SPIKE gate calibrated on 2 s) ->
  test_rw5_r2_newton_gate_regression.py (real). Jeremy voices 1->4 (k-estimate fragile; voices code unchanged) ->
  test_rw5_r2_voices_jeremy_split.py (real). Next: run real tests to confirm fail, ruff, minors doc, report.
- 4: DONE. real tests fail as intended (newton G2 .694 G4 .186; jeremy 4 voices). ruff clean. minors appended to
  docs/review/M5-r-words.md (Round 2, r2-m1..m5); report docs/build/reports/r-words-m5-r2.md. Structured summary returned.
