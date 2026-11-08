# builder-m4 progress (harmony, mood)

## Done
- 2026-11-08: read PLAN §5/§7/§12, SPIKE, CONTRACT, catalogue; stubs inspected.

## Next
- explore lv-chordia API, write harmony (chroma, key ensemble, chords), mood (numpy mel + ONNX heads), tests, real-song runs, report.

## Commands that worked
- (fill in)

## Gotchas
- skey keyMap order starts "A Major, Bb Major ..." use config.json keyMap, not C-based order.
- musicnn patch 187 fr (2.99 s) hop 93 (1.49 s); effnet patch 128 (2.05 s) hop 62 (0.99 s); mel at 16 kHz n_fft 512 hop 256.

## 2026-11-08 milestone 1
- harmony stage implemented (src/mvh/stages/harmony/{__init__,core,chroma,chords,keys,theory}.py): chords 100% label accuracy on synth (10 ms grid), key A minor (relative ambiguity flagged, conf 0.52), real songs ok. Dev loop: out/_wip/builder-m4/dev_h.py <slug> <fixture dir> <audio> (uses cached lv-chordia from tests/.cache/real/<slug>/chords).
- Stage run helper: powershell -File out/_wip/builder-m4/run.ps1 -Song <audio> -Out <dir> -Only <closure> [-Fixture tests/contract/real-<slug>]
- harmony closure: ingest,spectral,separate_fast,allin1,rhythm,harmony; mood closure adds loudness,dynamics,structure
## Next: mood stage, unit tests (tests/unit/harmony, tests/unit/mood), real-song runs, decisions M4.md, report

## 2026-11-08 milestone 2
- mood stage implemented (src/mvh/stages/mood/{__init__,core,frontend}.py), runs OK on synth through runner.
- tests written: tests/unit/harmony/{conftest,test_theory,test_chroma,test_chords,test_keys,test_synth_song}.py, tests/unit/mood/{conftest,test_frontend,test_core}.py; generators tests/synth/m4/__init__.py. Run: scripts/run.ps1 python -m pytest -q -p no:cacheprovider tests/unit/harmony tests/unit/mood (harmony ~70 s, mood ~20 s).
- NEXT: ruff, real-song runs of both stages (4 songs + synth via runner; fixtures tests/contract/real-<slug>), M4.md decisions, gate, report.

## 2026-11-08 milestone 3
- ruff clean on owned paths (E501 noqa header). docs/contract/decisions/M4.md written. real-song tests written (tests/unit/*/test_*_real_songs.py).
- Real-song runs via runner: out/_wip/builder-m4/<slug> (log out/_wip/builder-m4/runall_harmony.log); script out/_wip/builder-m4/runall.ps1 [-Only ...] [-FxPrefix out\_wip\builder-m4\fx-] [-Songs ...]. Heavy slots are contended (waits of 10+ min); real rhythm 500 s.
- megafauna harmony 27 s (validate OK), versatile done; jeremy/newton/synth in progress.
- mood on real songs needs dynamics fixtures (absent): overlay fixtures made by out/_wip/builder-m4/mkfx.py -> out/_wip/builder-m4/fx-<slug> (use -FxPrefix), mood closure: ingest,spectral,separate_fast,allin1,rhythm,loudness,dynamics,harmony,structure,mood
- NEXT: finish runs, mood runs, gate M4, report docs/build/reports/builder-m4.md, StructuredOutput.
- 21:02 all 5 songs run for harmony+mood; running gate M4 (log out/_wip/builder-m4/gate.log)
- 21:25 unit rerun (--timeout=3600) log out/_wip/builder-m4/unit2.log; first gate stopped at unrelated contract test test_stub_files_are_stubs (rhythm stub replaced by M2). Remaining: confirm unit pass, run gate steps, report.
- 21:5x unit 87 passed, ruff checked, report written. DONE.
