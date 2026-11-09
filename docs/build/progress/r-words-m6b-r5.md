# r-words-m6b-r5 progress
Round 5 review of M6b (meaning/brief/frames), lens R-WORDS.
## Done
- started; read r4 progress
## Next
- run R4 tests + all M6b review/unit/integration tests; inspect intent.py fixes
- M1: 420 pass/12 skip (review+unit M6b). R4-1 fixed (q3.py, many shapes ok), R4-3 fixed (q4.py on synth + 4 real fixtures: untouched -> pending, Q&A under/same-line ok).
  R4-2 listed cases pass, but variants still notes (q1.py: 'Avoid at all costs', 9-token heading, "What I'd never", 'No-nos', 'Hard limits'), no warning.
- NEW: (A) '**Story:**' / '**Never show:**' / '**Palette:**' (colon inside bold) -> value '*' (logline '*', do_not ['*']), real content lost (q2.py, q6.py) regression vs old.
  (B) voice-first answers 'V1 = C1 The Keeper' not parsed by meaning (notes / summary) while voices.intent maps them (q5.py).
  (C) text appended to copied interview voice bullet '- **V1**: ... -> C1 The Keeper' silently dropped by _IV_ECHO (q5.py 'append').
- real songs DevRun jeremy/newton/megafauna OK (real.log): 0 warnings, 0 lyric 9-gram hits, diffs vs integrator notes/references only.
## Next
- write tests test_rw5_*.py, minors, report
- M2: failing tests written, ruff clean: test_rw5_bold_colon_labels.py (R5-1, 9 fail), test_rw5_voice_answers.py (R5-2 4 fail, R5-3 4 fail incl. open questions sub-bullet q8.py), test_rw5_do_not_headings.py (R5-4, 6 fail).
## Next
- lifecycle probe on real song via DevRun with intent.md (hash unchanged, line_singers -> lines.tsv), minors, report
- M3: lifecycle on newton (life.py): intent unchanged, L005 C1+C2, do_not ['*'] confirmed in brief. m19 appended to review doc Round 5.
- DONE: report docs/build/reports/r-words-m6b-r5.md; 23 R5 fails, 420 pass. StructuredOutput next.
