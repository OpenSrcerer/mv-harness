# r-words-m5-r4 progress (W3 verify of M5)
- started: no prior r4 progress.
- 1: drive.sh newton-vs-nye jeremy running (my driver, outputs out/_wip/r-words-m5-r4/<slug>/<stage>; rerun drive.sh to resume). pytest-all.log running.
- 2: NEW major R4-1 colon lyric lines -> speaker markers (test_rw5_r4_colon_lyric_lines.py 4 fail, guard pass). R3-1..R3-4 tests pass; fixes are general (probe_text.py). minor candidates: '*Chorus*', 'Chorus (repeat)', '1st Verse:', '[Verse 1 - Name]', 'Name (Verse 1):', 5-word names.
- 3: S07 fixed (fixer versatile mouth 0 frames >0.1). S03: D50-D53 judged sound (W0 VAD whisper 0 words after 218 s; G1 scoped 0.77 ~ W0 0.762). Waiting on heavy slots for my real runs (other agents hold both). Minor list drafted in head: header long tail, '(x2)' own line, S03 part-2 integration test unpassable by design.
- 4: Round 4 section appended to docs/review/M5-r-words.md (r4-m1..m5). waiting newton/jeremy real runs.
- 5: newton real run (my driver): B, G1 .8786 G2 .7537 offset -1.31, 4 voices, identical words to fixer run; pytest-all 113 pass, 3 fail = integration tests reading pre-fix integrator outputs. jeremy running.
- 6: jeremy real run: B (G1 .7705), 1 voice, last word 218.1 s, tail warning, identical to fixer; leak scans clean. Writing report.
- 7: DONE. report docs/build/reports/r-words-m5-r4.md
