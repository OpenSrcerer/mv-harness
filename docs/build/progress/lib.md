# lib (W1b helper libraries) - checkpoint log

## Status: DONE (report: docs/build/reports/lib.md)
- [x] Read PLAN, SPIKE, CONTRACT (sections 1-4, 9, D1-D28), conventions.py, golden.py, viz/js/audio.js
- [x] src/mvh/assets/mvh.js, mvh.d.ts (strict tsc 6.0.3 check: 0 diagnostics), mvh_load.py, mvh.glsl
- [x] golden copy + addendum (src/mvh/assets/golden/, docs/contract/golden-addendum.md, tests/unit/lib/make_addendum.py)
- [x] tests: node --test tests/unit/lib/ -> 30/30; pytest tests/unit/lib tests/unit/contract -> 112 passed
- [x] parity JS vs Python: temp song (lib_synth_song.py) + tests/contract/synth (ran: .done.json present)
- [x] ruff clean on owned files; report written

## Design decisions
See docs/contract/golden-addendum.md (vizState rules and constants, lyricAt arrays, meaningAt merge, texture NaN fill).

## Commands that work
- JS: `node --test tests/unit/lib/` (Git Bash, from repo root)
- Py: PowerShell `Set-Location <repo>; . .\scripts\mvh-env.ps1 -Offline; uv run --frozen --no-sync python -m pytest -q tests/unit/lib`
- Addendum: `uv run --frozen --no-sync python tests/unit/lib/make_addendum.py [--check]`

## Gotchas
- Do not edit md files through PowerShell Set-Content (it mangled UTF-8); use the Write tool.
- In Git Bash never put a stdin-reading command (e.g. `cat > f`) before a heredoc: it hangs.
- pytest: tests/unit/lib has no __init__.py; do not import from conftest (other conftest.py files exist).
- ruff format exploded some literals in mvh_load.py; fine, but long docstrings still need manual wrapping (110 cols).
