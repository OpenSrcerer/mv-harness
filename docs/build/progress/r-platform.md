# r-platform progress (W1b independent review, Windows platform lens)

## Status: DONE (review + report written)
- Review: docs/review/w1b-r-platform.md ; report: docs/build/reports/r-platform.md
- Tests: tests/review/w1b/platform/ (8 failing by design: B1, M1-M6 (M4 has 2); 1 passing regression: jobobject)
- Verified: unicode CLI w/o UTF-8 mode, 48k/mp3/mono/Versatile ingest, determinism (same + second folder), Job Object kill,
  sep worker imports/variants, locks compat, doctor, gate exit 1 on failure.

## If resuming
Nothing left. To re-check: MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/review/w1b/platform
Expected now: 8 failed, 1 passed (until the fixer lands).

## Gotchas
- don't name scratch scripts after stdlib modules (concurrent.py broke an import)
- Runner API needs absolute song_dir
- In PowerShell 5.1 don't append 2>&1 to native commands
