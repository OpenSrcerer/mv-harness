# w4fix-analysis progress (W4 fixer, analysis group, round 1)

## Done
- Read BUILD-STATUS, SEAMS, W4 adversary tests, W3 critic tests.
- Copies of ud2-kick/<slug> (5 songs) and r-adversary/synth_* (6 perturbations) in out/_wip/w4fix-analysis/<name>.
  NOTE: contract is now 1.0.0-rc.3, all those folders are rc.2 -> a real `mvh analyze <folder>` re-runs EVERYTHING (separation too).
- Dev runner: out/_wip/w4fix-analysis/devrun.py (+ dr.sh wrapper): runs stages through run_stage on cached upstreams, chained,
  `--use-dev allin1` reuses earlier dev outputs; outputs in out/_wip/w4fix-analysis/dev/<tag>/<stage>. secs.py prints sections.
- W4A-GAIN: allin1 1.1.0 normalises the stems to -10 LUFS (param level_target_lufs; -10 keeps real songs ~unchanged,
  -14 changed Jeremy/MEGAFAUNA segments). Experiments: a1_gain_exp.py, logs a1_exp_*.log.
- structure: DP phrase prior ignores a single trailing silent bar (eff_len); phrase-grid split allowed past a trailing stop bar;
  'sandwiched' bridge rule (singleton chorus between two members of one chorus group -> bridge).
  synth/gm12/gp12/mp3 now truth sections + build 25 / drop 34.5.

## Next
- sr48 outro 52.5 (dynamics 7 parts), tempo90 (no EDM roles, outro cut), real-song structure regression check (running).
- then ACAP (spectral/drums/choreo), KICKCURVE (drums), S18 feel (rhythm, from mix snare band), S17 grooves, S19 hats, VOCPHR.
- (milestone 2) dynamics 1.1.0: short-part merge with a quarter-bar margin (decay tail kept consistently). structure 1.3.0:
  dyn_b ignores decay-tail part starts; drive uses kick coverage (kick_rate capped at 1, param drive_kick_cap); drop cue
  'top' margin (top-drive section after stop + strong impact, rise > 0); breakdown needs the kick to thin (cov <= prev - 0.2 or < 0.5).
  Dev results: synth/gm12/gp12/sr48/mp3 = truth sections + build 25 / drop 34.5; tempo90 build 27.8 / drop 38.3 (outro 47.2 still cuts
  the drop: allin1 says outro there). Real songs: EDM roles identical; Jeremy loses the 94.7 boundary (allin1); Versatile labeling
  allin1 -> structural (vc share 0.301 -> 0.294, threshold 0.3); Newton dynamics +1 part (154.9).
  TEMP debug prints in structure (MVH_DEBUG_STRUCTURE) must be removed.
- (milestone 3) spectral 1.4.0: kick_low_over_mid_db = 0 (30-150 Hz peak must not be below the 300-3000 Hz formant peak in 40 ms);
  acap 13 -> 1 kicks; real songs precision up (Jeremy 524->508, MEGAFAUNA 177->159, P@30ms .958->.986 / .345->.384), synth 86->84
  (F1 0.982 both). drums 1.3.0: choose_source(duration_s): kickless separated stem + few mix kicks -> source drums (no agent kicks);
  kickless stem + kick-track mix -> mix and agreement.min = mix_in_drums (QA flag); drums.kick curve from hits.kick under mix
  (mix_kick_hits, vel floor 0.2). test_w4a_ud2_kick_curve passes. choreo 1.2.0: empty drum_hits from a separated stem -> no
  drum rows / grooves / drum hit points (acap: 0 grooves, 8 stop hit points).
- (milestone 4) rhythm 1.1.0: backbeat feel vote (fusion.backbeat_feel on HPSS-percussive 1.5-8 kHz flux of the mix,
  bar-synchronous ratio beat3 / mean(beats 2,4), enter 1.5 / leave 1.3, min run 16 beats); meta/tempo.json additive "backbeat".
  Prototype (bbproto.py): Newton 1.83, Versatile 1.31, MEGAFAUNA 1.17, Jeremy 0.62, synth 0.64. Newton dev rhythm: feel half_time.
  choreo: consolidate_grooves (noisy kit: one-bar-groove share >= 0.2 -> clusters < 3 bars join the most similar groove of
  their repeat group, blurred vel cosine >= 0.6, kick/snare vel >= 0.3). Dev: MEGAFAUNA 18/62, Versatile 17/80, synth/Jeremy/
  Newton unchanged (not applied). groovelab.py = the variants lab.
  drums: hats.py hihat bleed gate (mix-confirmed share < 0.4 -> keep confirmed or rise >= 10 dB). Jeremy 495 -> 153 hats
  (vel>=.3) at 75 % on grid; other songs not gated.
- (milestone 5) vocals 1.2.0: in aligned lyric lines whose active+loud lead-stem time is < 50 % pitched, that energy is phrase
  material (vocal_phrases additive field basis = pitch | pitch+energy; pitch fields from the low-confidence f0 when no voiced
  frame). MEGAFAUNA dev: 9 phrases 39.9 s, sung-line coverage 0.19 -> 0.99. devrun.py now falls back to pre_key cache dirs.
- (milestone 6) allin1 switched to a loudness BAND [-16, -6] LUFS (real songs gain 0, synth +4.4 dB; -10 target moved
  MEGAFAUNA's 3/4 bar 44.6 -> 94.4 s). dynamics: min-gap quarter-bar margin also in assemble_k; novelty_margin param (off);
  provenance novelty_peaks. structure m-d evidence rename. Versions now: allin1 1.1.0, structure 1.3.1, dynamics 1.1.1,
  spectral 1.4.0, drums 1.3.0, choreo 1.2.0, rhythm 1.1.0, vocals 1.2.0. NOTE: cache keys have no code hash -> any later code
  change to a stage needs a version bump to re-run.
- Unit tests added: tests/unit/allin1/test_level_band.py, structure/test_w4_stop_bar.py, dynamics/test_w4_perturbations.py,
  spectral/test_w4_a_cappella.py, drums/test_w4_hats_and_kick_curve.py (+ test_kick_source.py updated), choreo/
  test_w4_grooves_and_no_drums.py, rhythm/test_w4_backbeat.py, vocals/test_w4_phrase_mask.py. All pass.
- docs/contract/decisions/W4-analysis.md written (W4-AN-1..8).
- Full runs r1 launched (run_song.ps1 -Name <n> -Tag r1; logs in out/_wip/w4fix-analysis/logs): synth, megafauna, jeremy,
  versatile, newton-vs-nye, synth_gm12, synth_gp12, synth_acap. Still to launch: synth_sr48, synth_tempo90, synth_mp3.
  After r1: run r2 (re-uses caches) so dynamics 1.1.1 / structure 1.3.1 edits apply everywhere.
- (milestone 7) spectral 1.4.1: kick_low_over_mid_db -1 (0 dB lost Jeremy's one true kick; M1 review recall test fell to
  0.949). Gate M1 -SkipE2E: unit PASS, review failed only on that test -> now passes. acap 2 kicks, synth F1 .988.
- Gates (-SkipE2E): M1 PASS after the -1 dB change (review test re-run alone); M2 PASS. M3a review timed out waiting for
  heavy slots (its r-ml conftest runs a synth separation; reuse with MVH_REVIEW_M3A_SYNTH=out/_wip/w4fix-analysis/synth once
  r1 is done). M3b gate pending. Verification plugin: out/_wip/w4fix-analysis/redirect_plugin.py (W4FIX_RUNS + MVH_REVIEW_RUNS).
- r1 done (analyze 0 / validate 0): newton, synth, synth_acap, gm12, gp12, sr48, tempo90, versatile. r2 launched for these 8
  (spectral 1.4.1, dynamics 1.1.1, structure 1.3.1). jeremy, megafauna, synth_mp3 r1 still running -> then r2.
- (milestone 8) rhythm 1.1.1: backbeat vote needs beat 3 >= 1.4 x the off-beat flux (synth_acap had half_time 0.18).
  r1 results all good (summary.py); perturbation tests 10/10 on my folders via redirect_plugin. r3 needed for everything
  after rhythm 1.1.1 (r2 runs in flight). Code freeze after this unless a test fails.
- r3 done (0/0) for gm12, gp12, mp3, sr48, tempo90, versatile; waiting for synth, acap, newton, jeremy, megafauna r3.
  Review tests on my folders (r1/r2 states): W3 critic hats/feel/grooves 12/12, W4 real seams 5/5, perturbations 10/10.
  Next: final review-test pass, M3a/M3b review re-run (heavy-slot timeouts), M2 full gate (e2e + determinism), report.
- r3 DONE on all 11 folders (analyze 0 / validate 0). Final state = current code.
- Final review tests on my folders: perturbations 10/10, W4 real seams + kick curve 6/6, W3 critic 18/18. Report written
  (docs/build/reports/w4fix-analysis.md). Gate M3a -SkipE2E PASS (MVH_REVIEW_M3A_SYNTH = out/_wip/w4fix-analysis/synth_m3a).
  Next: M3b gate (review), then M2 full gate (e2e + determinism).
- Gates -SkipE2E: M1 PASS, M2 PASS, M3a PASS, M3b PASS. M2 full gate (e2e + determinism) running -> logs/gate-M2-full.log.
- M2 full gate PASS (e2e + determinism). DONE: report final, structured result returned.
