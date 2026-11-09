# w4verify-analysis-r1 progress (independent verifier of w4fix-analysis, round 1)

## Done
- (m0) started; read fixer report/progress.

## Next
- read decisions W4-analysis.md, SEAMS, BUILD-STATUS; inspect fixer code for test hacks; re-run on real songs.
- (m1) Inputs made with ffmpeg in out/_wip/w4verify-analysis-r1/inputs: synth_base (truth flac), synth_tempo110 (atempo 1.1),
  synth_tempo95, synth_sr32 (soxr 32k), megafauna_gm12, jeremy_gm12 (volume -12dB, s32), newton_acap (fixer's newton stems/vocals.flac).
  Launched 3 lanes (21:45): `powershell -File out/_wip/w4verify-analysis-r1/run_queue.ps1 -NameList ...` (resumable; done markers in logs/<n>.done.json)
  laneA synth_base,synth_tempo110,synth_sr32,synth_tempo95; laneB megafauna_gm12; laneC newton_acap,jeremy_gm12.
  After an outage: relaunch the same lanes (finished names are skipped; an unfinished folder re-uses the stage cache).
- (m2) Review tests on fixer folders via redirect: perturbations 10/10, real seams+kick curve 6/6, W3 critic 18/18. Unit tests of the
  8 stages 194 pass; ruff clean. probe.py (numbers per folder) -> probe_fixer.jsonl. Observations so far:
  * synth gain fix is structural luck: synth stems -20.4 LUFS < band -> gm12 and baseline both land at -16 (identical input). Real
    songs are inside the band, so -12 dB on MEGAFAUNA (-6.1 -> -18.1 -> -16) changes allin1's level by 10 dB: megafauna_gm12 probe.
  * synth_acap feel_shares half_time 0.177 (tracker-based, backbeat 0 beats); r-adversary acap was normal 1.0 -> minor regression.
  * MEGAFAUNA new local half_time run 89.3-99.5 s, strong drum snares there on 2/4 only (3 hits) -> weak evidence, minor.
  * Newton vocal phrases 23 -> 12 (31/33/25 s phrases); lead stem has few dips there -> plausibly continuous rap, not a finding.
- (m3) tests/review/W4/verify-analysis/{w4va_support.py,test_w4va_perturbations.py} written (skip until runs finish).
  allin1 on megafauna_gm12: stems -22.98 LUFS, gain +6.98 -> -16 (baseline -10.98, gain 0): allin1 segments/labels differ
  (inst@19.1->intro, inst@123.5->intro, new 150.96, 185.25->194.4, outro 217). Final sections pending.
- (m4) NEW finding (KICKCURVE partial): under kick_source=mix choreo still reads drum_hits stem kicks (grooves 99% stem / 35% agent,
  5/6 drum hit points off the agent kick). Test tests/review/W4/verify-analysis/test_w4va_kick_mix_choreo.py (runs drums+choreo).
  Tool: out/_wip/w4verify-analysis-r1/devrun.py (copy of fixer's; outputs dev/<tag>; run with .venv python, MVH_OFFLINE=1).
  synth_acap half_time 0.177 explained: allin1 level band +6.5 dB -> allin1 finds 9 beats @60.9 -> tracker feel. minor.
- (m5) synth_base done (1224 s, 0/0): probe identical to fixer synth; truth sections+EDM pass; reproduce test pass.
- (m6) newton_acap done (0/0): 1 agent kick, hits.kick 0 (formant gate OK on rap), feel normal/double; drum hits only in the outro bleed (>=145 s, 17/27 coincide with original drums) -> ACAP holds on a real a cappella; drum-structure test limited to <145 s (passes).
- (m7) megafauna_gm12 done (1491 s, 0/0). W4A-GAIN NOT FIXED on a real song: sections 5 starts lost / 4 added, a new 'silence'
  section 38.57 (dynamics silence 2.95 s vs 1.28 s), beat F 0.665 / downbeat F 0.60 vs original (intro 0-30 s F 0.22; beat_this
  162->200, madmom 194->207; trackers bit-stable across 3 earlier runs). EDM roles unchanged. Tests added
  (test_w4va_real_song_*_12db). Remaining: jeremy_gm12, synth_tempo110, synth_sr32, synth_tempo95 (lanes A and C running).
- (m8) test_w4va_real_seams.py: spurious half_time spans w/o snare backbeat: MEGAFAUNA 89.3-99.5 (0 on 3, 3 on 2/4), Versatile 211.8-227.5 (no kick/snare). minor. Waiting jeremy_gm12 (allin1), synth_tempo110 (harmony).
- (m9) synth_tempo110 done (628 s, 0/0): truth sections+labels+EDM roles OK. dynamics silence cap: silence_cap_lufs -45 absolute (src/mvh/stages/dynamics/__init__.py:48) explains MEGAFAUNA -12 dB longer silence (2.95 vs 1.28 s) -> 'silence' section.
- (m10) synth_sr32 done (415 s, 0/0): truth OK.
- (m11) ALL RUNS DONE (0/0 each): jeremy_gm12 1360 s, synth_tempo95 327 s. Verifier tests: 8 failed / 15 passed.
  jeremy -12 dB: section 94.66 lost, bridge@149.24 -> chorus, outro/silence end changed; beat F 0.957, downbeat F 0.915.
  synth tempo95/tempo110/sr32/base: truth OK. Next: write docs/review/W4-verify-analysis.md + report, return structured result.
- (m12) DONE: docs/review/W4-verify-analysis.md and docs/build/reports/w4verify-analysis-r1.md written; structured result returned.
