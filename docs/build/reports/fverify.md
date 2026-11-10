# fverify report (final fix pass verifier)

Full findings: docs/review/F-verify.md. Failing tests: tests/review/F/verify/ (6 failing by design; ruff clean).

- ffix-form: pass. Generic rules, reproduced on a fresh Jeremy and Newton re-run, and checked on an independent CC BY pop
  song (songs/test-cc/olddog-rescue-me.mp3, docs/build/test-tracks.md): chorus kept there. One cosmetic oddity (F-V7).
- ffix-small: pass-with-fixes. Target tests pass (30); ruff clean now. W4VP-8 (frames status) still open (F-V6, minor).
- ffix-gain: fail. Invariance holds for real reasons, but:
  F-V1 separate_hq still 1.0.0 (cache keeps master-level DrumSep); F-V2 default onset recall 0.77 -> 0.64 with the unit
  bar lowered 0.7 -> 0.6; F-V3 synthetic cymbal F1 0.895 -> 0.778 (44.1 kHz) and 48 kHz below the 0.7 gate (was passing);
  F-V4 MEGAFAUNA gain vocal phrases IoU 0.788 (lyrics, CR-F-gain-2). F-V5 Versatile vocal content loss (minor).

Runs: out/_wip/fverify/{jeremy,newton-vs-nye,rescue-me}; scripts run_queue.ps1, run_new.ps1, cmp.py, synthf1.py.
