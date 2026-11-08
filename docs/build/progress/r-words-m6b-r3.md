# r-words-m6b-r3 progress (round-3 reviewer, M6b, lens R-WORDS)

## Done
- Started 2026-11-09. All tests/review/M6b (r-words + r-contract) and M6b unit tests pass: 123 passed, 12 skipped.

## Next
- Read the fixes in intent.py, docs.py, singing.py, stage.py, brief/build.py, skill/, frames/cli.py; check each is real, not a test hack; probe regressions.
- Probes in out/_wip/r-words-m6b-r3/ (p1_untouched .. p5_dn). Verified fixed: R2-1/N1 (untouched template on synth/no-voices/no-lyrics/4 real fixtures, fenced+unfenced, with/without draft: status unchanged), R2-4/N5 (characters[].field_sources, brief '(draft name + description)', template prefills intent only), R2-5/N6 (SKILL/RECIPES field_sources), R2-6 (frames cli checks status always).
- NEW candidates: (1) template drops user's section do_not, motifs, symbolism on re-paste (p3); (2) unquoted hex in template palette -> fenced: everything lost incl. do_not, warning says 'free text used'; unfenced: logline+do_not lost, comment example #1b2a49 becomes user colour (p4); (3) do-not over-capture: heading 'never-ending' story -> story becomes do_not; 'Avoid: x' + blank + bullets -> section notes become do_not (regression of N2 fix) (p5)
- Failing tests written and verified (9 fail, ruff clean): tests/review/M6b/r-words/test_rw3_template_roundtrip.py (R3-1), test_rw3_template_hex.py (R3-2), test_rw3_do_not_overcapture.py (R3-3).
- Minors m14-m16 appended to docs/review/M6b-r-words.md (Round 3).
- Gate (background, log out/_wip/r-words-m6b-r3/gate.log): unit FAIL only from tests/unit/contract test_stub_files_are_stubs (rhythm now implemented; not M6b); review/ruff/contract/validate PASS.
- Next: report docs/build/reports/r-words-m6b-r3.md, StructuredOutput.
- Report written: docs/build/reports/r-words-m6b-r3.md (verdict fail, R3-1..R3-3 major). Gate e2e analyze left waiting on a heavy slot (not needed for these findings). DONE after StructuredOutput.
