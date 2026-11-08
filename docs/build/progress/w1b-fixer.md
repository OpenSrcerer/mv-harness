# w1b-fixer progress

Run: `$env:MVH_RUN_OFFLINE=1; powershell -NoProfile -File scripts/run.ps1 python -m pytest -q <path>` (Git Bash: same via powershell.exe).

## Done
- Platform findings (all 9 tests/review/w1b/platform pass): separator dir (env scripts + _child_env/sepworker set, doctor FAIL),
  publish by copy (hard link only >= 8 MiB) + damaged-cache check on hit + PermissionError handling in publish/unpublish,
  status uses MVH_THREADS/--threads and diff_inputs prints `a -> b`, HF snapshot re-link + verify, safe jsonschema messages
  (contract/schemas.safe_message), slug collision (cli._unique_slug).

## Next
- Contract findings F1 (cue ties), F2 (singer lines.tsv), F3 (notes vs vocals output claims), F4 (vizState fr), F5 (allAt)
- Update golden vectors, CONTRACT decisions D37+, schemas regenerate (mvh.contract.gen), unit tests, ruff, gate W1b
- contract F1-F5 done, ruff clean (noqa E501 on contract files), CONTRACT D37-D46. Next: full unit run, node tests, gate W1b, report
- gate W1b exit 0 (all PASS). Fixture manifest trimmed per D34 (tests/synth/song/folder.py). DONE; report in docs/build/reports/w1b-fixer.md
