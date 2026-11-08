# builder-m3b progress (M3b: notes, vocals, instruments)

## Done
- Implemented instruments (ced.py, clap.py, vocab.py, fuse.py), notes (bp.py, post.py, midi.py), vocals (pitch.py).
- tests/synth/m3b/: stem_overlay.py (real-song fixture overlay + reference stem_activity + spectral placeholders into
  out/_wip/builder-m3b/fx/<slug>), fxctx.py (direct Ctx using the runner's StageWriter), direct.py (run stages directly,
  heavy slot), synthrun.py (cached synthetic run for tests), scoring.py, report.py.
- Unit tests in tests/unit/{instruments,notes,vocals}; pure tests pass.
- Measured on synth: bass note F1 0.907 (onset 50 ms), BASS_LINE 0.903; piano 0.985 (basic-pitch) / 0.977 (CRNN forced);
  vocal p2/p98 within 0.22 st; lowest G3 / highest A4 exact; raw pitch acc 0.996.

- Real-song direct run DONE (18:03; logs/direct3.log, direct/timings.json): all 4 songs ok for all 3 stages.
- Decisions doc docs/contract/decisions/M3b.md written (I-M3b-1..11, additive fields).

- 21:15 unit tests pass (35 + 4 real skipped), ruff fixed. Added human-correction params notes.piano_mode,
  vocals.present, vocals.style (+ tests/unit/vocals/test_m3b_hooks.py); decisions I-M3b-12 + CR-M3b-1..4.
- Gate run 1 (logs/gate1.log): tests/unit/contract::test_stub_files_are_stubs fails (asserts rhythm is a stub; M2
  replaced it) -> not ours, open issue for the integrator.

## Next (resumed 21:00)
- Re-run unit tests (notes synth in_key check was failing at 17:43), ruff, gate M3b, report.

## Commands that work
- Git Bash: `export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python -m tests.synth.m3b.direct instruments,notes,vocals synth`
- Long runs: use run_in_background (a `&` job dies when the Bash call returns).
- `python -m tests.synth.m3b.report out/_wip/builder-m3b/direct/<slug>` summary without lyrics.

## Gotchas
- CED ONNX output is already a probability (no sigmoid). Real fixtures lack stem_activity, instruments, spectral events.
- Other modules replace upstream stubs live: runner `--only` runs fail when deps go stale; use the direct harness.
- vocals cannot read lyrics (not a dep). notes cannot read instruments: the piano gate runs CED itself.
- CED tags low sung verses as Speech: range stats use all voiced frames unless the lead is rap/speech-dominant.
- 21:50 gate1: unit notes/vocals/instruments all pass (11 / 14+4 skipped / 13; hooks tests included), ruff, contract,
  validate PASS; contract unit folder FAILS only on test_stub_files_are_stubs (rhythm no longer a stub). e2e running.
- Report drafted at docs/build/reports/builder-m3b.md (fill in gate result at the end).
- 22:45 gate1 finished: all M3b checks PASS (e2e 567 s, determinism PASS); only contract::test_stub_files_are_stubs fails
  (not ours). Real-song tests 4/4 passed (logs/real1.log). Report complete. DONE.
