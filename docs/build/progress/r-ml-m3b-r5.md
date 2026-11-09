# r-ml-m3b-r5 progress
- started: read r4 progress, review doc, build status
- next: verify r4-1 / r4-2 fixes in src/mvh/stages/vocals/__init__.py, run tests, then regressions on real songs
- 09:55 code read. r4-1 fix: _lyric_mask skips timing_source interpolated/lrclib_line/user_line/none and conf <= 0.02 (not the 0.3 suggested).
  r4-2 fix: untagged lyric frames inherit the tagger's dominant style (incl. speech) -> suspect MEGAFAUNA (tagger speech) loses its range.
- integrator megafauna still stale (05:10). Copied r4 megafauna+newton to out/_wip/r-ml-m3b-r5; --only vocals refused (rhythm, lyrics stale);
  bg run_all.ps1 (spectral..lyrics,vocals) -> <slug>.up.log, run_all.status
- 10:10 r4-1 partial: lyrics word conf floor is 0.1 (core._word_conf), so line conf >= ~0.06 always -> vocals' conf<=0.02 filter is dead.
  All real lines are timing_source ctc (conf 0.09..1.0). CTC forced alignment of supplied text on a voiceless stem -> ctc lines, gate opens.
  Building end-to-end evidence: out/_wip/r-ml-m3b-r5/karaoke (synthetic saw lead + user lyrics.txt), full analyze in bg -> karaoke/run.log
- 10:40 r4 tests: both PASS with MVH_REAL=1. unit vocals 18 pass.
- karaoke e2e: lyrics on a voiceless song with user text -> 7 ctc lines conf 0.12-0.30 + 1 stable_ts 0.72, grade D, 34.5 s coverage;
  vocals present false only because the separator put the saw lead in "other" (RMVPE voiced 0.1 s). Lines open the gate though.
- megafauna r5 rerun: present true but RANGE NULL (spoken_pitch 6.96 s, style speech) vs r4 E3-E4 alto -> REGRESSION from r4-2 fix (inherit speech).
  newton identical (72.12 s rap, notes.mid same). megafauna notes.mid same.
- next: write 2 failing tests (lyric ctc gate on voiceless; megafauna speech inherit range loss), review doc, report
- 11:00 NEW tests written + FAIL as stated: test_vocals_ctc_lines_on_voiceless_song.py (present True 27.1 s, 58 notes),
  test_vocals_inherited_speech_drops_range.py (range null, 23.2 s spoken). ruff clean. next: seams, review doc, report
- 11:15 DONE: review doc Round 5, report docs/build/reports/r-ml-m3b-r5.md written; StructuredOutput next
