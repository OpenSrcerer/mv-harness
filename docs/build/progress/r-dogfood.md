# r-dogfood progress
- [start] read SKILL.md, RECIPES, brief of integrator/newton-vs-nye. Chosen folder: out/_wip/ud2-kick/newton-vs-nye (post-UD2: lib has kicks(), summary.kick_source=drums). integrator/ folder is PRE-UD2 (SKILL documents song.kicks() but its lib lacks it).
- window: 84-104 s (S06->S07->S08, singer C2->C4, hit H007 at 93.99).
- sketch/song copied (patched meaning S06-S08 by hand: mvh meaning cannot run on rc.2 folder under rc.3 code, AND it deleted curves/ in the copy: RUNTIME finding F-del). Next: write sketch/index.html, serve, screenshots.
- sketch built (index.html), python http.server has no Range => au.currentTime seek to 84 fails (audio starts at 0). rangeserver.py on :8766. kick onset median offset +1.8ms vs browser-decoded mix.flac (OK); preview.opus aligned 0 ms. NEXT: re-verify play with 8766, screenshot 5 times, then MEGAFAUNA if time, then write findings+tests+review md+report.
- [DONE] sketch verified (newton + megafauna), tests in tests/review/W4/dogfood (4 fail as intended), docs/review/W4-dogfood.md and docs/build/reports/r-dogfood.md written. Only the structured summary remains.
