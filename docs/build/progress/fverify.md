# fverify progress

- started: read fixer reports
- queued out/_wip/fverify/run_queue.ps1 -NameList jeremy,newton-vs-nye (copies of w4fix-analysis-r2, --force separate_hq); logs in out/_wip/fverify/logs
- downloaded songs/test-cc/olddog-rescue-me.mp3 (CC BY 3.0), recorded in docs/build/test-tracks.md
- findings so far: M3a 48k cymbal regression (0.686, gate 0.7); synth 44.1k cymbal 0.895->0.778; spectral onset test bar lowered 0.7->0.6 for default; separate_hq still 1.0.0 (CR-F-gain-1); megafauna vocal phrase IoU 0.788 (lyrics); Versatile vocal phrases 10->6 (lead pick F-gain-6)
- wrote tests/review/F/verify (fv_support, test_fv_separate_hq_cache, test_fv_spectral_onset_recall, test_fv_gain_real_runs): 6 failing as intended, ruff clean
- small fixer: verify-words/verify-platform/platform non-real 30 passed; W4VP-8 frames status still open in finalize.py (minor)
- next: wait jeremy/newton re-runs + rescue-me, compare, write docs/review/F-verify.md and report
- jeremy re-run done (rc 0, validate 0): hook 176.1 chorus, 220.7-288 outro, drums/onsets small drift; rescue-me done: 6/14 chorus kept, minor oddity outro@131.1 then chorus@140.3 (3.7 s)
- drafted docs/review/F-verify.md (F-V1..F-V7); waiting for newton-vs-nye re-run to fill its line, then report
- DONE: newton re-run compared; review doc + report written
