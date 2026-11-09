# w4fix-analysis: W4 fixer, analysis group (M1, M2, M3a, M3b, M4), round 1

Decisions: docs/contract/decisions/W4-analysis.md (W4-AN-1..8). Progress log: docs/build/progress/w4fix-analysis.md.
No lyric text anywhere below; numbers only.

## Findings and fixes

| Finding | Fix (stage, version) | Result on the re-analysed folders |
|---|---|---|
| W4A-GAIN | allin1 1.1.0: the htdemucs stems are brought into a [-16, -6] LUFS band by one gain (inside the band: unchanged); structure 1.3.1: the stop bar that ends a section is not counted in the DP phrase prior, the phrase-grid split looks past it, and a not-repeated "chorus" between two members of one chorus repeat group is the bridge | -12 dB and +12 dB (clipped): truth sections, labels and build 25.0 / drop 34.5 (before: all `intro` -> inst/inst/build/drop; bridge at 27.0 labelled chorus) |
| W4A-STABLE | dynamics 1.1.1: the 2-bar minimum compared with a quarter-bar margin (boundary assembly and short-part merge); structure: decay-tail dynamics starts are not section evidence, EDM drive uses kick coverage (kick-band peaks / beat capped at 1), a drop-cue margin for the song's top-drive section after a stop + impact, breakdowns need the kick to thin | 48 kHz: outro 50.5 (was 52.5); 0.9x tempo: build 27.8 / drop 38.3 found (were none); MP3 control unchanged |
| W4A-ACAP | spectral 1.4.1: a kick's 30-150 Hz peak must not be > 1 dB below the 300-3000 Hz (formant) peak; drums 1.3.0: a kickless separated stem + a mix that is not a kick track -> `kick_source = drums`, no agent kicks (a kick track -> mix + QA flag); choreo 1.2.0: no drum rows / grooves / drum hit points when the drums stage found nothing on a separated stem | a cappella: 0 agent kicks (mix 2 events, was 13), 0 grooves, 0 drum hit points (were 16 / 7) |
| W4A-KICKCURVE | drums: under `kick_source = mix` the `drums.kick` curve is built from hits.kick | MEGAFAUNA forced to mix: every agent kick has a curve peak and vice versa (test passes; was 0.47 / 0.28) |
| W4A-VOCPHR | vocals 1.2.0: inside an aligned lyric line whose active + loud stem time is < 50 % pitched, the stem energy is phrase material (`basis: pitch+energy`) | MEGAFAUNA: 9 phrases, 39.9 s; 99 % of the sung line time inside a phrase (was 19 %) |
| W4A-S17 / S17 | choreo: noisy-kit consolidation (>= 20 % one-bar grooves -> grooves of < 3 bars join the most similar groove of their repeat group, cosine >= 0.6) | MEGAFAUNA 48 -> 18 ids / 62 bars (0.29), Versatile 32 -> 17 / 80 (0.21); synth, Jeremy, Newton untouched (consolidation not triggered) |
| W4A-S18 / S18 | rhythm 1.1.1: half-time BACKBEAT vote from the mix (HPSS-percussive 1.5-8 kHz flux, bar-synchronous beat 3 vs 2 + 4, hysteresis, off-beat guard). No DAG change (decision W4-AN-6) | Newton feel half_time (shares half 0.85), was normal; Jeremy and synth stay normal; Versatile normal with local half-time runs (0.33); a cappella normal |
| W4A-S19 / S19 | drums: hihat bleed gate (`drums/hats.py`): a stem whose hat rows the mix high band confirms < 40 % keeps only confirmed hats or those rising >= 10 dB | Jeremy: 153 hats (vel >= 0.3), 75 % on the 16th grid (was 495, 37 %); only Jeremy triggers |
| m-d (minor) | structure: drop / breakdown evidence says `kick-band onsets x/beat` | |
| m-g (minor) | dynamics margin (above) | synth 44.1 / 48 kHz / -12 dB give the same arrangement parts |

Also checked and left alone (open items in the structured result): m-a, m-e, m-f, m-i, m-m, m5, tempo90's extra outro.

## Tests

New unit tests (all pass): tests/unit/allin1/test_level_band.py, tests/unit/structure/test_w4_stop_bar.py,
tests/unit/dynamics/test_w4_perturbations.py (synth mix at 44.1 / 48 kHz / -12 dB), tests/unit/spectral/test_w4_a_cappella.py
(the fixture's vocals stem: <= 2 kicks), tests/unit/drums/test_w4_hats_and_kick_curve.py, tests/unit/choreo/test_w4_grooves_and_no_drums.py,
tests/unit/rhythm/test_w4_backbeat.py, tests/unit/vocals/test_w4_phrase_mask.py. Updated: tests/unit/drums/test_kick_source.py
(`test_choose_source_without_stems_or_without_kicks`: a kickless separated stem with ONE mix event is now `drums`, by
design; two new cases).

Review tests on the re-analysed folders (current code, rc.3; out/_wip/w4fix-analysis/<name>):
- tests/review/W4/adversary/test_w4a_perturbations.py: 10/10 (W4FIX_RUNS redirect, see below)
- tests/review/W4/adversary/test_w4a_real_seams.py + test_w4a_ud2_kick_curve.py: 6/6 (MVH_REVIEW_RUNS)
- tests/review/W3/critic (all): 18/18 (redirect)

The review tests read fixed paths (`out/_wip/r-adversary/<name>`, `out/_wip/integrator/<slug>`), which hold rc.2 runs
made with the old code; this fixer did not overwrite other agents' folders. To verify:

```
# Git Bash, repo root
W=out/_wip/w4fix-analysis
MVH_REVIEW_RUNS="$(cygpath -w $W)" W4FIX_RUNS="$(cygpath -w $W)" PYTHONPATH=$W \
  .venv/Scripts/python.exe -m pytest -q -p redirect_plugin tests/review/W4/adversary/test_w4a_perturbations.py
MVH_REVIEW_RUNS="$(cygpath -w $W)" .venv/Scripts/python.exe -m pytest -q tests/review/W4/adversary/test_w4a_real_seams.py tests/review/W4/adversary/test_w4a_ud2_kick_curve.py
MVH_REVIEW_RUNS="$(cygpath -w $W)" W4FIX_RUNS="$(cygpath -w $W)" PYTHONPATH=$W \
  .venv/Scripts/python.exe -m pytest -q -p redirect_plugin tests/review/W3/critic
```
(run the two redirect sessions separately: with both conftests in one session the W4 constant is not patched.)
Or re-analyse the fixed folders (`mvh analyze out/_wip/r-adversary/<name>`, `mvh analyze out/_wip/integrator/<slug>`): all
are rc.2, so that is a full re-run each (45-85 min per real song with the slots shared).

Gates (logs in out/_wip/w4fix-analysis/logs/gate-*.log):
- M2 full: PASS (unit, review, ruff, contract, validate, e2e 255 s, lib-node, determinism 249 s).
- M1 -SkipE2E: PASS (the first run failed `test_jeremy_unambiguous_kicks_are_kept` at recall 0.949 with a 0 dB formant
  gate; the gate is now -1 dB and the recall is back).
- M3a -SkipE2E: PASS (with `MVH_REVIEW_M3A_SYNTH=out/_wip/w4fix-analysis/synth_m3a`; the first run timed out waiting for a
  heavy slot while 11 analyses ran).
- M3b -SkipE2E: PASS (the first run timed out on a heavy slot in a CLAP review test).
- M4: no code change.

## Re-analysed folders (no regression)

11 folders, three passes each (r1 full rc.3 run, r2 / r3 after later fixes), every pass analyze 0 / validate 0:
synth, megafauna, jeremy, versatile, newton-vs-nye (copies of out/_wip/ud2-kick/<slug>) and synth_gm12, synth_gp12,
synth_sr48, synth_tempo90, synth_acap, synth_mp3 (copies of out/_wip/r-adversary/<name>). Old (ud2-kick) vs new
(out/_wip/w4fix-analysis/regress_r3.txt):

| | beats / downbeats F (20 ms) | sections, labels | EDM roles | other changes |
|---|---|---|---|---|
| synth | 1.00 / 1.00 | identical | identical | dynamics +1 part (the 52.5 s decay tail); hits.kick 86 -> 85 (F1 vs truth 0.982 -> 0.988) |
| MEGAFAUNA | 1.00 / 1.00 | identical | identical | hits.kick 177 -> 162; grooves 48 -> 18 ids; vocal phrases 7.7 -> 39.9 s; half_time 0.05 share (global normal) |
| Jeremy | 1.00 / 1.00 | identical | none | dynamics 13 -> 15 parts; hits.kick 524 -> 510 (precision vs the drum-stem kick .958 -> .982); hats 975 -> 311 |
| Versatile | 1.00 / 1.00 | identical | identical | grooves 32 -> 17 ids; half_time 0.33 share (global normal) |
| Newton | 1.00 / 1.00 | identical | none | feel half_time; dynamics 9 -> 11 parts; vocal phrases 23 / 116 s -> 12 / 123 s (4 sparsely pitched rap lines filled from the stem energy) |

Lyrics grades, hit points and cue counts are unchanged on every song.

## Tools (out/_wip/w4fix-analysis)
devrun.py + dr.sh (a stage through run_stage on a folder's cached upstreams, chained, `--use-dev`, `--param`), run_song.ps1
(resumable re-analysis), summary.py, regress.py, groovelab.py (groove clustering variants), bbproto*.py (backbeat
prototypes), kickvoc.py / kickcmp.py / lvm_tp.py (kick formant evidence), hats.py, a1_gain_exp.py (allin1 level
experiments; logs a1_exp_*.log), redirect_plugin.py.
