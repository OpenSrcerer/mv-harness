# ffix-gain progress
## Done
- read W4-verify-analysis GAIN findings, W4-AN-9, tests test_w4va2_level_and_labels.py
## Next
- inspect hq_worker / separate_hq DrumSep call; drums, stem_activity, vocals, spectral gates
## Milestone 1 (code written, untested)
- src/mvh/sep/level.py (numpy/scipy BS.1770 for the sep env), hq_worker: DrumSep on sw_drums x analysis gain, outputs x 1/gain
  (param drumsep_analysis_lufs, default -10; summary.settings.drumsep_analysis_level)
- drums 1.4.0 (stems x mix gain; level_db back to dBFS), stem_activity 1.1.0 (active_db - gain_db), vocals 1.3.0 (lead x gain,
  mean_db back), spectral 1.5.0 (events from analysis-level pass, curves absolute). All via param analysis_lufs (-10).
- NOTE cache key has no code hash: separate_hq change needs a version bump by the integrator (CR).
## Next: unit tests; verify with copies of w4fix-analysis-r2/{megafauna,versatile} + gain copies, --force those stages
## Milestone 2: unit tests green (owned dirs 165 pass); spectral kick lane kept at master level (a cappella regression otherwise)
- verification folders copied to out/_wip/ffix-gain/<name>; queue: powershell -File out\_wip\ffix-gain\run_queue.ps1 -NameList a,b
  (analyze <folder> --force separate_hq; logs in out/_wip/ffix-gain/logs)
- review tests: W4VA_RUNS=W4VA_BASE=out/_wip/ffix-gain
- decisions written: docs/contract/decisions/F-gain.md; queue + gates (M1,M3a,M3b -SkipE2E, logs/gate-*.log) running in background
- synth_base/synth_gm12 re-run: 4/4 gain tests pass (cmp_gain.py); stem active_db -55.4 / -67.4 dBFS
- DrumSep sub-stem SDR base vs gm12 restored: new 62-81 dB (old 11-47 dB). out/_wip/ffix-gain/sdr.py
## Milestone 3
- M1 gate PASSED (-SkipE2E). M3a review: 2 fails on synth (final crash 52.5 s dropped as dull bleed: hat stem typical
  brightness +1.5 dB with DrumSep at analysis level; 48k cymbal F1 0.647). Fix: core.drumsep_hits crash_like exemption
  from dull_bleed (rise >= 24 dB, decay < 6 dB, < 18 dB under the kick, no snare). Crash restored; unit drums green.
- TODO after queue: re-run `--force drums` on all 7 folders (drums code changed mid-queue), rerun M3a gate, cmp_gain.
- M3b gate PASSED. megafauna pair (after --force drums): drums/stemact/spectral PASS; vocals notes F 0.885 (was 0.375) but
  phrase IoU 0.788: cause = lyrics alignment differs by level (base lines at 106.7-116 s move in the copy; lyrics is M5,
  not owned) -> change request. Phrases after 119.8 s identical.
- versatile pair: drums/stemact/spectral PASS; vocals FAIL because pick_lead_stem (instruments/lead.py) p95 over non-zero
  frames flips with FLAC quantisation at -12 dB. F-gain-6: new rule loud_frame_gap_db (lead vs vocals energy in the vocals
  stem's loudest 10 % frames; MEGAFAUNA 40 dB -> vocals, Versatile 1.5 dB -> lead). instruments 1.1.1, vocals 1.3.1.
- M3a gate rerun: 48k synth cymbal F1 0.686 (< 0.7) still failing; 44.1k crash test now passes.
- 48k synth cymbal F1 0.686: 6 quiet rides (vel 0.47, under snares, 17.5-24.5 s) — DrumSep at +10 dB puts them weaker in
  the ride stem (-44..-58 dB, rise 7-10 dB) and the leak gate drops them. Not fixable in the gate rules without risk; kept
  as an open issue (the synth mix at -20 LUFS is unnaturally quiet; real masters ~-10 LUFS see the old DrumSep level).
## Milestone 4
- r2 queue done (instruments 1.1.1 / vocals 1.3.1). cmp_gain: synth, megafauna -12/-20, versatile -12: drums, stem activity,
  spectral PASS everywhere; vocals PASS synth + versatile; megafauna vocals phrase IoU 0.788 only because lyric lines differ:
  swap_lyrics.py (vocals on the copy with base lyrics) -> phrases IoU 1.000, notes F 1.000. Lyrics = CR-F-gain-2.
- next: final gates M3a, M3b -SkipE2E (logs/gate-*-final.log), report.
## Done
- final gates: M1 PASSED, M3b PASSED, M3a FAILED review only on test_r2_drums_separated_synth_48k (cymbal 0.686). Report written.
