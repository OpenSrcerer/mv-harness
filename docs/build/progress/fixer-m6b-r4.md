# fixer-m6b-r4 (W3 module fix, round 2)
## Done
- read BUILD-STATUS, fixer-m6b-r3 progress+report, r-words-m6b-r4 report.
- baseline: R3 findings all fixed by r3. 14 review fails = r-words R4-1 (key lists), R4-2 (do-not recall), R4-3 (interview copy).
## Next
- read tests test_rw4_*.py, M6b-r-words.md round 4 minors (m16-m18), intent.py grammar; fix in grammar.
- MILESTONE 1: intent.py grammar v3: _list_answer (key + bullets, R4-1), do-not heading vocabulary + bulleted labels (R4-2),
  rule 0 interview echo (_IV_QUESTIONS/_IV_ECHO; question lines -> headings, R4-3), palette heading class, TEMPLATE_HINTS cut
  whatever spacing (m17). tests/review/M6b + unit meaning/brief/frames: 300 pass, 12 skip.
## Next
- probes for edge cases; grammar docstring v3; property test additions; m18 brief notes line; m16 RECIPES isDraft; decisions; gate; real songs.
- MILESTONE 2: grammar docstring v3; dynamic question tails end at their fixed closing text (inline answers kept);
  brief.md 'User notes ...' line (m18); RECIPES isDraft === 'draft' (m16); SKILL §3 notes/references; new
  tests/unit/meaning/test_intent_grammar_v3.py (~120 cases). Running wider test set (M5/voices/viewer) in background.
## Next
- decisions/M6b.md 'W3 round 2'; real songs via DevRun (scratchpad scripts of r3: out/_wip/fixer-m6b-r3 / scratchpad devrun_songs.py); gate.
- MILESTONE 3: decisions/M6b.md "W3 round 2" written. `mvh analyze <copy> --only ...` still refuses (upstream stale since
  05:10 integrator run), so real songs via DevRun: scratchpad m6b_r4_devrun.py -> out/_wip/fixer-m6b-r4/dev/<slug>, log
  out/_wip/fixer-m6b-r4/devrun.log. Gate running in background -> out/_wip/fixer-m6b-r4/gate.log (+ gate.exit).
## Next
- compare dev/<slug>/baseline vs integrator (scratchpad cmp_songs.py) and vs r3 dev baseline; report.
- MILESTONE 4: real songs (DevRun) all 5: stages ok, 0 warnings, frames 0 NaN, template round trip ok, interview Q&A copy ok,
  untouched interview copy -> pending with no user fields. No-intent baseline is identical to r3's on all 5 songs, and vs the
  integrator the diffs are additive only (references/notes, 3 template lines, provenance keys). Waiting on the gate.
- gate: fixture/review/ruff/validate PASS; unit FAIL only tests/unit/contract (2, not M6b); contract FAIL (CONTRACT.md stale); e2e waiting on heavy slot. 420 pass / 12 skip M6b. Report draft written.
- DONE: gate exit 1 (only non-M6b steps: contract unit x2, CONTRACT.md stale, upstream determinism); M6b det with identical upstream OK. Report written docs/build/reports/fixer-m6b-r4.md.
