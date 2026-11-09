# r-words-m5-r5 progress (W3 round-5 verify of M5)
- 0: started fresh (no prior r5 progress). Task: verify R4-1 fix, look for regressions, rerun on 2 real songs.
- 1: unit+review tests M5 pass (118, models skipped). R4-1 only partly fixed: recurring branch of _scan_labels skips the pronoun/verb check (probe_markers.py: 'I said to John:' x2 / Title Case 'She Said:' x2 -> deleted, hints). NEW major: voices ValueError when a hint exists only on short (<min_item_s) lines -> test_rw5_r5_short_hint_crash.py (2 fail, guard pass).
- 2: real runs launched: sh out/_wip/r-words-m5-r5/scripts/drive.sh newton-vs-nye jeremy (log out/_wip/r-words-m5-r5/drive.log, <slug>.DONE; rerun to resume). compare: scripts/compare.py <slugs>
- 3: R5-1 test test_rw5_r5_recurring_colon_lines.py (4 fail, guard pass). R5-2 test test_rw5_r5_short_hint_crash.py. minors: joint split of 'Tyler, The Creator' loses hint; Ann/Bob/All once -> markers sung; lone (x2) after block repeats only last line; integration tests still read pre-fix integrator folders.
- 4: Round 5 minors appended to docs/review/M5-r-words.md (r5-m1..m5). waiting for real runs (heavy slot).
- 5: real runs done (newton, jeremy rc=0).
- 6: DONE. compare identical to fixer-m5-r4 (newton B 4 voices, jeremy B 1 voice), leak scans clean. report docs/build/reports/r-words-m5-r5.md
