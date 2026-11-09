# r-adversary progress (W4 independent reviewer, lens R-ADVERSARY)

## Done
- [x] Read BUILD-STATUS, SEAMS, RUNS, ud1/ud2 reports.

## Next
- Read W3-completeness, PLAN §11, integrator-r2; inspect out/_wip/ud2-kick/<slug> (post-UD2 runs) and integrator folders.
- Perturbation runs into out/_wip/r-adversary/.

## Notes
- Latest real outputs post-UD2: out/_wip/ud2-kick/<slug> (integrator folders are pre-UD2).
- [x] 16:25 Perturbed synth inputs in out/_wip/r-adversary/inputs (gm12, gp12, sr48, mp3, mono, clip10 @17.3s, tempo90 (atempo 0.9), acap (fixture vocals stem), silence30, delay1234 (+1.234 s)).
- [x] 16:26 Launched 2 background queues: `powershell -File out/_wip/r-adversary/run_queue.ps1 -Names ...` (resumable: skips <name>.done.json).
  Queue A: synth_gm12,synth_mp3,synth_tempo90,synth_clip10,silence30. Queue B: synth_gp12,synth_sr48,synth_mono,synth_acap,synth_delay1234.
  After an outage: delete the half-written out/_wip/r-adversary/<name> folder? NO - analyze is resumable (cache); just relaunch the same commands.
- [x] 17:00 Findings so far (evidence scripts in out/_wip/r-adversary/):
  - W3 critic tests re-run on post-UD2 runs (copy in out/_wip/r-adversary/w3c, RUNS=ud2-kick): S16 handoffs (2.3 s two mouths), S17 grooves MF/VS,
    S18 feel, S19 Jeremy hats 37% -> all STILL REAL. m3 resolved (V3->V2 0.2 s from S06).
  - S16 detail (s16.py): L021 V1 'backing' span 48.52+1.97 s conf 0.68 but backing_vocals stem is -60..-73 dB except ~0.3 s burst at 48.5-48.8.
  - NEW major M3b: MEGAFAUNA vocal_phrases total 7.7 s vs vocals stem active (vocact.py) 54-88% in S08/S09/S12/S13 and lines 53-100%; brief vocals column 8-21%.
  - NEW minor M3a: meta/stems.json vocals.present=false (conf 0.30) on MF while range/lines/singer exist; brief stems row omits vocals.
  - NEW major M6b(UD1): do_not is all-or-nothing: tab-indented list or a trailing indented prose line -> every do_not rule becomes a note (ud1_probe.py);
    `do_not:` + blank line + `- item` -> silent note, no warning.
  - m4 worse: MEGAFAUNA manifest summary.stages = {} after UD2 (was 3 stages).
  - minor brief energy column hides 'peak' at 50% ties (energycheck.py; synth S05 drop shows 'medium').
  - MEGAFAUNA tempo 105 independently confirmed (tempo_indep.py on drop drums/kick/snare/mix).
  - MF drum-stem kick: 16% gaps <100 ms, outro S17 16 kicks vel med 0.13 grid 6%; flagged qa:kick_sources_disagree (UD2 behaves as decided).
- [x] 17:25 Tests written: tests/review/W4/adversary/{conftest.py, test_w4a_ud1_do_not.py, test_w4a_real_seams.py} (newest run per slug among $MVH_REVIEW_RUNS, ud2-kick, integrator).
  Also launched synth_kickmix (copy of ud2 synth, --param drums.kick_source=mix; full re-run because rc.3 bump changed keys): run_kickmix.ps1.
  Machine is loaded by r-platform-w4 runs (2 Newton det runs etc.), so perturbation runs are slow.
- [x] 17:50 NEW major (drums, UD2): with kick_source=mix the drums.kick curve still = drum-stem kicks (core.envelopes(hits) always);
  MF devrun (out/_wip/r-adversary/drums_mix_devrun.py): 177 agent kicks vs 316 curve peaks, 0.47/0.28 agreement. Test test_w4a_ud2_kick_curve.py.
  Helpers moved to tests/review/W4/adversary/w4a_support.py. 10 tests fail as intended, 1 control passes, ruff clean.
- minor: structure drop evidence 'kick 0.96->1.19/beat' on synth (truth 1.00/beat, agent kicks 32/32 beats) - internal onset rate labelled kick.
- 16:40 Dropped synth_mono, synth_delay1234 (skip markers <name>.done.json) because of slot contention.
- 17:00 docs/review/W4-adversary.md drafted with placeholders PERTURBATION_RESULTS and FINDINGS_TABLE (fill after runs).
- 17:00 gp12 partial: structure bridge start 25.0->27.0 & relabelled chorus, edm build 27.0 (truth 25.0); beats/drums intact; 43630 clipped samples, limited_master false.
- [x] 17:10 NEW major M2 (allin1+structure) gain sensitivity: gm12 labels verse/chorus/bridge/chorus -> inst/inst/build/drop (allin1 says 'intro' everywhere);
  gp12 bridge 25.0 -> 27.0 relabelled chorus, edm build 27.0. Test test_w4a_perturbations.py (skips until the runs finish their manifest).
- [x] gp12 done (analyze 0/validate 0, 2162 s): cmp_synth_gp12.json. Beats/drums/key/lyrics(B)/voices(2) fine; structure bridge 1 bar late;
  vocal style 'speech' (baseline singing), range conf 0.38. Clipping warned.
- [x] gm12 done (2412 s): labels flip (allin1 'intro' everywhere), piano stem absent at -12 dB (absolute threshold; minor), lyrics B, voices 2.
- [x] synth_kickmix done: manifest/brief/lib switch to mix correctly (86 kicks, fallback flag). UD2 fallback OK apart from drums.kick curve.
- gain tests: 3 fail as intended, control passes.
- dropped synth_clip10 (skip marker).
- [x] mp3 done (451 s): robust (n_samples exact, beats/sections/drums/lyrics same; hat P 0.83).
- [x] sr48 done: outro 52.5 (truth 50.5), dynamics 7 parts vs 5. tempo90 done: beats perfect, EDM roles BOTH lost, drop split by 'outro' at 47.2.
  Tests added to test_w4a_perturbations.py. Remaining: silence30 (queue A), synth_acap (queue B).
- [x] silence30 done: graceful (analyze 0/validate 0), but summary key 'C major' + bpm 120 virtual grid + 21 cues/11 counts on silence (flags present; minor).
- [x] synth_acap done: 13 invented agent kicks (fallback mix), no QA flag (agreement None), 16 grooves + 7 'drum' hit points; 'silence' section S03 over 4.8 s singing (minor). Tests added.
- NEXT: finalize docs/review/W4-adversary.md, report, structured output.
- [x] DONE: docs/review/W4-adversary.md final, docs/build/reports/r-adversary.md written, lyricscan 0 matches. 17 tests fail as intended, 4 controls pass.
