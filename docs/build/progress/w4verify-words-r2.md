# w4verify-words-r2 progress (independent verifier of w4fix-words-r2, round 2)

## Done
- started; read fixer report docs/build/reports/w4fix-words-r2.md and r1 verifier progress.

## Next
- read intent.py (_load_region, _scan_unfenced, _COL0_ITEM); run r1 tests; probe edge cases; re-drive words stages on synth + 2 real songs.
## Milestone 1
- only src/mvh/stages/meaning/intent.py changed since r1 (VWU1-a: order + _LIST_KEYS branch; VWU1-b: _COL0_ITEM).
- driver copy out/_wip/w4verify-words-r2/scripts/drive.sh (resumable, <slug>.DONE); drive_intent.sh <tag> <intent.md> drives meaning,brief on synth with a probe intent (VW_TAG / VW_SONG_DIR).
- background drive started: synth newton-vs-nye jeremy (log out/_wip/w4verify-words-r2/drive.log)
## Milestone 2: parser probes (out/_wip/w4verify-words-r2/probes/p1.py)
- VWU1-a FIXED for the reported shapes (stray before/after, two strays, nested, tab-indented, symbolism/themes/palette/motifs/refs; notes kept; map keys mixed keep both).
- VWU1-b FIXED (-<TAB> col0, blank lines, CRLF, two tabs, unclosed fence, symbolism).
- NOT fully fixed (major): broken item ('- "No text...' unclosed quote / '- [x') + stray 'Also: fog' line -> do_not == ['Also: fog...'] only (line 541 `sub if sub else subl` still reachable when every '- ' item failed).
- minor: '* rule' / '• rule' / '– rule' / '-NBSP rule' col0 under do_not: silently notes (0 warnings, unparsed []).
- minor: indented stray under a col0 item or deeper under an item takes that rule into the note (warned).
- foreign major: tests/unit/brief/test_skill.py::test_contract_copy_is_current FAILS: docs/CONTRACT.md edited 19:46 (W4VP-1, platform) and skill copy not re-synced -> M6b gate unit step fails.
- words unit+brief+verify tests: 853 pass, 1 fail (above).
## Milestone 3: tests written
- tests/review/W4/verify-words/test_w4vw_r2_ud1.py (VWR2-1 x4, VWR2-2 x4, VWR2-3 x2 fail; control passes), test_w4vw_r2_skill_copy.py (VWR2-4 fails). r1 file 6/6 pass. ruff clean.
## Milestone 4: drives
- synth driven: NEW == FIX(w4fix-words-r2) byte/JSON-identical all 18 files; vs INT only schema_version, intent_unparsed (additive), backing_unbacked_lines (r1 voices fix), interview/request/schema text.
- compare: run.ps1 python out/_wip/w4verify-words-r2/scripts/cmp.py <slug> [tag]
- intent probes chain (drive_intent.log): _ctrl, _vwr21 (fixture + unclosed quote + stray: first item still parses so the fix applies), _vwu1a; then _vwr21s (single broken rule + stray) to run.
- VWR2-1 needs EVERY '- ' item to fail -> rate minor.
- newton driven: NEW == FIX all 20 files; vs INT = the r1 S16 voices fix (spans 55->54, backing span gone) + schema_version/intent_unparsed. synth_ctrl (fixture intent): user yaml+text, 2 do_not, 0 unparsed, 0 open q.
- review/unit: M6b+m6b+adversary UD1+contract/frames/viewer 288 pass; M5+voices/lipsync/lyrics 138 pass.
- jeremy driven: NEW == FIX all 16 files; vs INT schema_version/intent_unparsed/backing_unbacked_lines only.
- e2e probes (probes/e2e.py): _vwr21s (single broken rule + stray) -> meaning.json/brief do_not == the fog wish (VWR2-1 confirmed).
## DONE: docs/review/W4-verify-words.md (r2 on top of r1), docs/build/reports/w4verify-words-r2.md written; structured output returned.
