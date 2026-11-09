# w4verify-analysis-r2 progress (independent verifier of w4fix-analysis-r2, round 2)

## Done
- (m0) started; read fixer r2 report and r1 verifier progress.

## Next
- read decisions W4-AN-9..11, fixer code diffs; look for test hacks; launch real-song runs.
- (m1) inputs in out/_wip/w4verify-analysis-r2/inputs: megafauna_gm20 (-20 dB), versatile_gm12, jeremy_gm6, synth_base (truth flac).
  Launched 23:24 (resumable; skip names with logs/<n>.done.json):
  `powershell -File out/_wip/w4verify-analysis-r2/run_queue.ps1 -NameList <names>`: laneA megafauna_gm20; laneB versatile_gm12; laneC synth_base,jeremy_gm6.
  Baselines to compare against: out/_wip/w4fix-analysis-r2/<slug> (fixer r2) and out/_wip/integrator/<slug>.
- (m2) fixer r2 gm12 vs base (its own folders): identical sections/beats/bars/EDM/silences; drum_hits level-dependent (MEG snare 536 vs 475,
  mostly vel<0.5; cymbals 9/14 strong differ) -> minor note. Tools: out/_wip/w4verify-analysis-r2/{cmp.py,drumdiff.py,kickmix.py}.
- (m3) KICKCURVE-CHOREO verified on megafauna, versatile, jeremy (drums kick_source=mix + choreo, dev/mix_<slug>): grooves 0.98/1.0/1.0 on
  agent kicks, 0-0.6 % stem-only; every drum hit point without an agent kick has a stem SNARE >= 0.65 -> FIXED (r1 test too strict).
  Helper tests/review/W4/verify-analysis/w4va_devchain.py written.
- (m4) tests updated: w4va_support defaults RUNS=out/_wip/w4verify-analysis-r2, BASE=out/_wip/w4fix-analysis-r2 (run() falls back to BASE);
  perturbation gain tests parametrized over GAIN_PAIRS (fixer gm12 x2 + my gm20/versatile_gm12/jeremy_gm6); kick-choreo test
  rewritten (agent kick OR stem snare>=0.5; 3 songs): 3 passed.
- (m5) W3 critic on fixer r2 folders (redirect plugin): 18/18 pass (S17 grooves, S18 feel, S19 hats fixed there).
  integrator vs fixer-r2: MEG intro bar phase moved (bar F 0.56; drumless 0-91 s, allin1 downbeats fit neither grid -> not judgeable);
  Jeremy 176.12 s section chorus->verse though it holds the chorus hook line (lyric text group T11 / repeat LG03, in every chorus) -> minor;
  Versatile label mode flip allin1->structural (EDM roles same) -> note only.
- (m6) unit tests allin1/rhythm/dynamics/structure/choreo/harmony/loudness/drums 201 pass 47 skip; ruff clean.
  NEW candidate: vocals (M3b) level-dependent: absolute level_floor_db -55 (vocals/__init__.py:174) ; fixer MEG gm12 vs base:
  notes.vocals 33 -> 15 (onset F 0.375), phrase coverage 40.0 -> 31.2 s. Jeremy notes F 0.93. Tool vocdiff.py. Confirm on my runs.
- (m7) tests/review/W4/verify-analysis/test_w4va2_level_and_labels.py written (vocals gain; chorus-hook-as-verse). GAIN_PAIRS moved to
  w4va_support. Non-slow sweep: 25 pass, 2 fail (vocals megafauna_gm12; jeremy hook verse), 13 skip (my runs pending).
  Hook test passes on integrator (W3) folders -> regression of the fixed level.
- (m8) m3 (Newton voice change vs S06): voice change now 69.44 vs section 69.64 (was 67.6) -> resolved by M5 changes. Jeremy 176.12: allin1
  raw label was 'verse' in every run; integrator/r1 labelled chorus via repeat group D; r2's new 185.07 boundary makes 176.12 a singleton.
- (m9) early (stage cache) check: megafauna_gm20 and versatile_gm12 sections+labels identical to fixer base, beats F 1.0, bars F 1.0
  -> GAIN-REAL and GAIN-BEATS hold on fresh runs at other gains/songs. Waiting for full runs (vocals, choreo, dynamics).
- (m10) laneD launched: synth_tempo105 (atempo 1.05), synth_sr22 (soxr 22050) to probe the tuned structure rules (W4-AN-11 c/d).
- (m11) versatile_gm12 DONE (1230 s, 0/0): sections/labels/EDM/beats/bars/silences/feel/chords identical. NOT level-invariant:
  vocal_phrases 10->4 (cover 6.1->2.1 s), notes.vocals 27->13 (F 0.60); drum-stem kick (agent kick, kick_source drums) 109->102,
  8 lost incl 6 vel>=0.5 -> at -12 dB DrumSep routes them to tom/snare (level-dependent separation input); cymbal F 0.44.
  Candidate findings W4V2-GAIN-VOCALS (M3b), W4V2-GAIN-DRUMS (M3a separate_hq/drums).
- (m12) Mechanisms: vocals level_floor_db -55 abs; stem_activity active_db -45 dBFS abs; separate_hq normalization off -> DrumSep sees
  master level (Versatile toms SDR 8.9 dB, crash 13 dB between base and +12 dB-restored gm12; lead vocals 35.6 dB = same stems).
  Tests added to test_w4va2_level_and_labels.py: stem_activity gain, agent kick/drum hits gain. Current: 9 fail / 4 pass / 6 skip.
  Need: fresh synth_base vs fixer synth (determinism of fresh separation), megafauna_gm20, jeremy_gm6, synth_tempo105/sr22.
- (m13) synth_base DONE 0/0. synth_tempo105: analyze rc 1: harmony crash NaN (2 ms trailing N seg past last chroma frame; chords.py:218
  empty-slice mean). Pre-existing (fails with analysis_lufs null too). Test test_w4va2_harmony_tail_crash.py (unit, fails).
- (m14) fresh synth_base == fixer synth on every compared output (stems separation deterministic) -> gain diffs are level, not noise.
- (m15) megafauna_gm20 DONE 0/0: sections/labels/EDM/beats/bars/silences/feel/chords identical (GAIN fixes hold at -20 dB).
  Still level-dependent: notes.vocals 33->8, phrase cover 40->28 s; drum-stem kick +9 strong (agent kick F 0.92); cymbal strong 9/16.
- (m16) spectral (M1) onsets/hits level-dependent too (abs gate_db -46): MEG gm12 strong hits.mid 248->329 (F 0.856), gm20 F 0.65-0.86.
  Test test_w4va2_spectral_onsets_and_hits_survive_a_gain_change added. Planned severities: VOCALS/STEMACT/DRUMS major, SPECTRAL minor,
  HARMONY-NAN blocker (crash, rc 1), JEREMY-HOOK-VERSE minor. Waiting jeremy_gm6, synth_sr22.
- (m17) synth_sr22 DONE 0/0: verse at 9.0 s labelled chorus (allin1 verse 0.15 < verse_min_before_chorus 0.25): W4-AN-11(d) is fitted
  to sr32 (verse 0.36) -> minor W4V2-FORMRULE-NARROW, test test_w4va_synth_sections_survive_other_edits[synth_sr22]. EDM roles OK.
  Remaining: jeremy_gm6. Next: write docs/review/W4-verify-analysis.md (round 2 section on top) and report.
- (m18) review draft at out/_wip/w4verify-analysis-r2/review_r2.md (to be prepended to docs/review/W4-verify-analysis.md; r1 doc
  backed up as out/_wip/w4verify-analysis-r2/W4-verify-analysis.r1.md). Waiting jeremy_gm6 to fill its numbers.
- (m19) jeremy_gm6 DONE 0/0 (sections/beats/bars identical; vocals OK; crash activity 0.962, 3 strong cymbals added).
  Final sweep tests/review/W4/verify-analysis: 22 failed / 40 passed / 1 skipped (all failures = my findings).
  docs/review/W4-verify-analysis.md now has the round-2 section on top of round 1. Next: report + structured output.
- (m20) DONE: report docs/build/reports/w4verify-analysis-r2.md written; structured result returned.
