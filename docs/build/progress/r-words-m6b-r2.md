# r-words-m6b-r2 progress (round-2 reviewer, M6b, lens R-WORDS)

## Done
- Started 2026-11-08. Round-1 artefacts: docs/build/progress/r-words-m6b.md, tests/review/M6b/r-words/, docs/review/M6b-r-words.md.

## Next
- Run tests/review/M6b/{r-words,r-contract}; read the fixes; probe for real fix vs hack; look for regressions.
- 2026-11-08: all 16 round-1 review tests (r-words + r-contract) pass. Code read: intent.py, stage.py, singing.py, cites.py, brief/build.py, docs.py yaml_template, RECIPES.
- Probes in out/_wip/r-words-m6b-r2/ (probe_f4_instr, probe_f4_real, probe_f3_regress, probe_dn_forms, probe_char_fill, probe_unfenced_mixed):
  * F4 NOT fixed for songs with no characters (instrumental / no voices: real-megafauna, real-versatile): template prefills lead_backing: lead -> status user
  * F3 (r-words) only for '#' headings: '**Never show**' bold label (interview's own format) -> rule lost + chorus feel; 'Never show: X' -> logline
  * r-contract F3 partial: unfenced template + appended markdown -> YAML fails -> '{name' chars, comment feels, template do_not lost (warning now)
  * REGRESSION of F3 fix: free text whose first line is lowercase 'palette:' etc parsed as whole YAML -> '#hex' colours cut as comments, section notes dropped, no warning
  * F1 residual: draft name/description filled into user character -> meaning.json provenance user, brief unlabelled; template then prefills draft name
  * r-contract F2 residual: RECIPES/SKILL still say provenance.status marks drafts; field_sources not mentioned anywhere in skill/
- Next: write failing tests tests/review/M6b/r-words/test_rw2_*.py, minors (curly apostrophe bypass of cut_lyric_runs, zoom '(draft)' on audio facts)
- Tests written and verified failing for the stated reasons (12 fail; ruff clean): tests/review/M6b/r-words/test_rw2_intent_reopened.py (8), test_rw2_draft_labels.py (4)
- Minors m11-m13 appended to docs/review/M6b-r-words.md (Round 2). M6b unit tests: 84 passed, 12 skipped.
- Next: report docs/build/reports/r-words-m6b-r2.md, StructuredOutput
- Report written: docs/build/reports/r-words-m6b-r2.md (verdict fail, N1-N6 major). DONE after StructuredOutput.
