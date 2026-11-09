# r-words-m6b-r4 progress
Round 4 review of M6b (meaning/brief/frames), lens R-WORDS.
## Done
- started; read r3 progress, BUILD-STATUS
## Next
- run R3 tests (r-words + r-contract), inspect fixes in intent.py/docs.py/stage.py
- M1: all M6b review+unit tests pass. intent.py rewritten (grammar v2). Old parser copy in out/_wip/r-words-m6b-r4/oldmod/intent_old.py for comparisons.
- Verified fixed (probes p4 hex variants, perspective fs): R3-1..R3-5 contract, R3-1..R3-3 words (hex flow/block/col0/short; template prefill motifs/symbolism/section do_not).
- NEW candidates: (A) lc 'characters:'/'sections:'/'line_singers:' + bullets silently dropped (regression; old parsed) p3.py;
  (B) do-not headings 'What I don't want'/'Avoid these'/'Things I never want to see' -> notes (regression), bullet '- Never show: x' -> notes; notes not in brief.md (p2.py);
  (C) copying interview.md Q&A-style: harness preamble -> user logline/summary, 'night blue' hint -> user palette, Q9 answer lost (p1c.py, p5.py).
- Real songs jeremy + newton-vs-nye via DevRun (real.py): ok, 0 lyric 9-gram hits, singer 'C3+C1' format, diffs vs integrator only notes/references.
## Next
- write failing tests test_rw4_*.py, minors, report.
- M2: failing tests written + verified (14 fail, ruff clean): test_rw4_key_lists.py (R4-1), test_rw4_do_not_recall.py (R4-2), test_rw4_interview_copy.py (R4-3).
- Minors m17, m18 appended to docs/review/M6b-r-words.md (Round 4). m14/m15 fixed, m16 still open.
- Next: report docs/build/reports/r-words-m6b-r4.md, StructuredOutput.
- DONE: report written docs/build/reports/r-words-m6b-r4.md; StructuredOutput next.
