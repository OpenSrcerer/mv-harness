# fixer-m6b-r3 (W3 module fix, round 1)
## Done
- (start) read BUILD-STATUS, W2 findings for M6b (8 majors), fixer-m6b-r2 progress.
## Next
- read intent.py/docs.py/stage.py and the failing review tests; replace intent heuristics with one grammar.
- baseline: 18 review fails (all 8 findings), 123 pass. Old intent.py/docs.py copied to scratchpad (intent_old.py, docs_old.py).
- design: intent.py rewritten as ONE grammar: L1 viewer block, L2 template regions (YAML with hex/comment tolerance + per-key chunk fallback), L3 line-classified free text (anchored do-not headings, inline label = 1 rule, bare label + bullets = list).
- template keeps hints verbatim (review tests assert 'palette: []   # hex (#1b2a49)' and '{L005: C1+C2}' preconditions).
- MILESTONE 1: intent.py rewritten (grammar v2 docstring), docs.py template prefills motifs/symbolism/references/notes/section do_not + hex hint line, stage.py perspective.narrator/addressee field_sources + references/notes in meaning.json. tests/review/M6b + unit meaning/brief/frames: 141 pass, 12 skip (real).
- Next: property test tests/unit/meaning/test_intent_grammar.py, ad-hoc edge checks, RECIPES/SKILL perspective note, decisions M6b.md, gate, real songs.
- MILESTONE 2: tests/unit/meaning/test_intent_grammar.py (145 cases: round trip exact + fixed point, 4x5x5 template variants, untouched template, do-not table, tolerant line). docs: RECIPES/SKILL perspective field_sources, decisions/M6b.md "W3 round 1". ruff clean. review M6b + unit meaning/brief/frames/voices/viewer: 347 pass, 12 skip.
- Next: gate (scripts\gate.ps1 M6b, background + log), real songs vs integrator outputs.
- MILESTONE 3: real songs. `mvh analyze <copy> --only meaning,brief,frames --force ...` refuses: upstream 'structure' is stale in the integrator copies (M2 fixer changed its params: bar_jitter_frames, impact_snap_strength, short_section_margin), cascading to everything. Used DevRun (runs the real stage code via runner.child.run_stage) with out/_wip/integrator/<slug> as upstream instead: scratchpad/devrun_songs.py + cmp_songs.py. All 5 songs: meaning/brief/frames ok, 0 warnings; vs integrator only additive diffs (meaning.json +references +notes; interview.md +3 template lines; brief flags line = DevRun stubs carry no upstream fallbacks); frames 24 and 24000/1001 fps no NaN. Template round trip on each real song ok. Log: out/_wip/fixer-m6b-r3/devrun.log
- gate running in background -> out/_wip/fixer-m6b-r3/gate.log
- gate still in e2e (heavy slot contention) at 06:29
- MILESTONE 4 (DONE): gate exit 1, but every failure is outside M6b (contract unit test vocals deps + CONTRACT.md stale, ruff in structure/vocals, determinism from GPU stems). M6b unit/review PASS, e2e PASS. M6b deterministic given identical upstream (det_m6b.py). Report written: docs/build/reports/fixer-m6b-r3.md.
