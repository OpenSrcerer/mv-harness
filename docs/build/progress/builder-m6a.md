# builder-m6a progress (M6a Viewer): DONE except gate e2e/determinism (queued behind heavy slots)
Report: docs/build/reports/builder-m6a.md ; decisions: docs/contract/decisions/M6a.md
## Done
- stage (data.py, bundle.py, __init__.py), server.py, cli.py (mvh view), intent_block.py, assets/viewer/*, tests/unit/viewer (51 py + 12 node)
- browser-verified on synth + 4 real fixtures; edit round trip; ruff clean on owned files
## Commands
- py: MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python ...
- folder from fixture: python tests/unit/viewer/build_view.py real-jeremy out/_wip/builder-m6a/fx-real-jeremy ; then mvh view <folder> --no-open
## Gotchas
- Browser pane refuses file:// ; use ?inline=1 on the served page to force the file:// code path
- bash+node -e string escaping of backslashes/$ is fragile: use the Edit tool
