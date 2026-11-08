# r-platform-m6a progress
- started 2026-11-08; reading PLAN/SPIKE/CONTRACT
- built viewer folders: out/_wip/r-platform-m6a/{synth,real-newton-vs-nye,real-megafauna,"ünï cødé ☃ song"} via tests/unit/viewer/build_view.py
- served unicode folder with mvh view (works). FINDING A: Play does not start rAF loop -> playhead frozen until mouse hovers a lane (verified in browser)
- candidate: 8.3 short name CACHE~1 bypasses hidden-folder filter (8.3 names enabled on C:)
- candidate: NaN/Infinity accepted by POST; U+2028/NEL in intent values truncates/injects on parse (splitlines)
- candidate: invalid overrides.json on disk read as {} then overwritten on save (data loss)
- file:// testing: Claude_Browser cannot open large file:// pages (size cap, data: snapshot). Use headless Edge:
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu --no-first-run --user-data-dir=<out/_wip/r-platform-m6a/edge-prof> --enable-logging=stderr --v=0 --virtual-time-budget=8000 --dump-dom file:///...
- FINDING B: absent optional lipsync/visemes.json -> vocal lane 'lane error' + console error (x-novis)
- FINDING C: absent events/singing.json -> fatal page (x-nosing); real-megafauna/newton fixtures fatal under file://
- build helper: out/_wip/r-platform-m6a/build_excl.py <out> <exclude...>
- DONE. Tests: tests/review/M6a/r-platform/ (10 failing cases: 4 browser via headless Edge+CDP, 6 server). ruff clean.
- Minors: docs/review/M6a-r-platform.md. Report: docs/build/reports/r-platform-m6a.md. Servers stopped (ports 50652, 60572 killed); no headless Edge left.
- RESUMED 2026-11-08 (after fixer-m6a): re-ran tests/review/M6a/r-platform -> 10 passed (all 7 majors fixed in current code). Minors not re-checked.
