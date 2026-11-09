# w4fix-analysis-r2 progress (W4 fixer, analysis group, round 2)

## Findings
- W4V-GAIN-REAL (allin1 level band + dynamics absolute silence cap), W4V-GAIN-BEATS (rhythm trackers level), W4V-KICKCURVE-CHOREO.

## Done
- Started; read verifier tests. Work dir out/_wip/w4fix-analysis-r2.

## Next
- read allin1/rhythm/dynamics/choreo code.
- (m1) loudness/level.py helper (ANALYSIS_LUFS -10, gain on stereo mix). allin1 1.2.0 level_target_lufs -10 (mix-measured);
  rhythm 1.2.0 analysis_lufs -10 (x scaled before trackers+DSP; tempo.json additive analysis_level); harmony 1.2.0 and
  structure 1.4.0 analysis_lufs -10; dynamics 1.2.0 silence relative only (rel 35 LU, cap None). Unit tests added, pass.
- Next: choreo kick_source=mix; then dev chains on megafauna/jeremy base vs gm12.
- (m2) choreo 1.3.0: kick_source=mix -> kick rows from hits.kick (mix_kick_rows, vel strength/p98 floor 0.2), meta/grooves.json
  additive kick_rows. Review test: grooves 0.99 on agent kicks; 2 of 7 'drum' hit points (160.12, 194.4) have no agent
  kick but a stem SNARE vel 0.91/1.0 at the same instant ('drum' = kick or snare >= 0.5) -> test too strict there.
- Dev tools: out/_wip/w4fix-analysis-r2/{devrun.py, dr.sh, cmp.py, hpcheck.py}; dev outputs in dev/<tag>/<stage>.
- (m3) rhythm decode_meter late_bias (param meter_late_bias 0.25): irregular bars placed as late as evidence allows
  (MEGAFAUNA's 3-beat bars flipped 91 s <-> 62 s on 4e-5 activation noise). Dev MEGAFAUNA base vs gm12: sections,
  beats, bars, silences, EDM identical. vs old base: intro phase moved (19.55->18.4 etc; 3-beat bars 44.6 -> 91-94.4;
  mix kicks on beat 1 in 0-45 s: 7 vs 4, so the new phase is at least as plausible). chain2.sh = rhythm..structure w/ dev allin1.
- (m4) rhythm backbeat_feel mid-band gate (backbeat_mid_min 1.25 on feats["snare"] 150-4000 Hz flux, per run) for N4.
  Unit tests: rhythm/test_w4_backbeat.py (+hats-only, +late-bias tie test). Code freeze for full runs.
- Full runs: 18 folders copied into out/_wip/w4fix-analysis-r2/<name> (base: 6 + adversary synth perturbations 5,
  verifier runs 7). run_queue.ps1 -NameList ... -Tag r1 (resumable), two lanes; logs in logs/<name>.r1.*
  Lane A: megafauna,megafauna_gm12,synth,synth_acap,synth_gm12,synth_gp12,synth_mp3,synth_base,synth_tempo110
  Lane B: jeremy,jeremy_gm12,versatile,newton-vs-nye,synth_sr48,synth_tempo90,synth_sr32,synth_tempo95,newton_acap
- (m5) Gate M1 -SkipE2E PASS. Full r1 runs megafauna, jeremy, *_gm12 done (0/0). With W4VA_RUNS=W4VA_BASE=out/_wip/w4fix-analysis-r2:
  real_song sections/edm/beat-grid gain tests 6/6 PASS.
- (m6) Gates -SkipE2E PASS: M1, M4, M2. 13/18 full runs done.
- (m7) all 18 full r1 runs done, analyze 0 / validate 0. Next: review sweep.
- (m8) r1 review sweep (W4VA_RUNS/BASE + W4FIX_RUNS + MVH_REVIEW_RUNS = r2 dir; redirect_plugin.py fixed to patch conftest
  plugins too; run with .venv python directly, PYTHONPATH=out/_wip/w4fix-analysis-r2): adversary+critic 39/39; verify fails:
  kick-choreo (snare hit points, test too strict), synth_sr32 verse->chorus (allin1 at -10), synth_tempo95 no EDM (top-drop
  rise +0.01 -> -0.01), newton_acap 2 empty groove bars < 145 s (grid moved; ghost hats 0.04/0.1).
  Fixes: structure 1.4.1 (drop_top_min_rise -0.25; verse_min_before_chorus rule), choreo 1.3.1 (groove_min_hit_vel 0.15).
  Dev check on all 18 folders: only the targeted cases change (versatile -8 ghost-only groove bars). Next: r2 runs (all 18).
- (m9) r2 runs 18/18 0/0. Review sweep r2: 60 pass, 1 skip, 1 fail (kick-choreo snare hit points, argued).
- (m10) report written (docs/build/reports/w4fix-analysis-r2.md). Waiting on M2 full gate (logs/gate-M2-full.log).
- (m11) M2 full gate PASS (e2e + determinism). DONE.
