# r-words-m6b progress (independent reviewer, M6b meaning/brief/frames, lens R-WORDS)

## Done
- Read PLAN §4/§5/§7/§8/§10/§12, SPIKE, CONTRACT §§1-4,6-7,12-14, M6b decisions, meaning stage code.

## Next
- Run meaning/brief on synth + real fixtures, probe lifecycle/anchoring/privacy, write failing tests under tests/review/M6b/r-words/.

## Commands that work
- PowerShell: `. .\scripts\mvh-env.ps1 -Offline; uv run --frozen --no-sync mvh analyze ...` (python -m mvh does not work; use the `mvh` entry point)
- Git Bash: `.venv/Scripts/python.exe out/_wip/r-words-m6b/probeN.py` works for pure build() probes (DictSource from tests/unit/meaning/conftest.py)
- Full synth analyze started in background -> out/_wip/r-words-m6b/synth (log synth-analyze.log); real stages wait for heavy slots (slow)

## Findings so far (verified by probes in out/_wip/r-words-m6b/)
- MAJOR brief shows draft logline/palette/section feel unlabelled when meaning status is user (probe1)
- MAJOR stale voices proposal merges a voice into a user character mapped elsewhere (YAML template; probe3)
- MAJOR do-not bullets 'Chorus: never show X' become the section's user feel (probe5)
- MAJOR? draft cite id / occurrence line_id text echoed into warnings (NF5) (probe2 E)
- minor: D38 lead order by time not voice number (probe4); free-text S-id notes cannot re-anchor
- Wrote failing tests tests/review/M6b/r-words/test_rw_{brief_draft_provenance,voice_mapping,intent_parsing,draft_privacy}.py (10 fail for the stated reasons; ruff clean)
- Minor findings written to docs/review/M6b-r-words.md (m1-m10)
- probe9 (DevRun, real runner child): draft cite text lands in cache/meaning/_mvh/done.json; brief S03 row shows a do-not rule as feel
- Next: wait for synth analyze (blocked on heavy slots) to check run.json/stdout warnings and frames; then write report
- Report written: docs/build/reports/r-words-m6b.md (verdict pass-with-fixes, 6 majors F1-F6, 10 minors)
- Remaining: confirm the background synth analyze (or stop it), then StructuredOutput
- Resumed 2026-11-08 23:15: synth analyze log idle since 17:53 (stopped, as the report says); re-ran tests/review/M6b/r-words: 10 failed for the stated reasons. DONE; StructuredOutput returned.
