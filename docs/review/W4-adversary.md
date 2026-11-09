# W4 R-ADVERSARY review (r-adversary, PLAN §11: try to refute "it works")

Reviewer: r-adversary (independent W4 reviewer). Date 2026-11-09. No lyric text appears here (synthetic fixture
lyrics are not printed either; word results are counts).

## Method
- **Latest real outputs.** `out/_wip/ud2-kick/<slug>`: the integrator's max folders re-analysed with the UD2 code.
  The integrator folders are pre-UD2. My scripts, logs and runs are in `out/_wip/r-adversary/`.
- **Independent ground truth.**
  - The synthetic song's generator truth (`tests/contract/synth/_truth/truth.json`).
  - The stems themselves: `stem_activity`, plus my own RMS and spectral-flux measurements through `mvh.io.audio.decode`.
  - Cross-tool agreement: key vs chords vs bass notes, tempo vs beat IOIs, lyric lines vs vocal phrases vs vocal-stem
    activity, the two kick timelines, drum hits vs the beat grid.
- **Perturbations** of the synthetic song. Each is `mvh analyze --profile max` offline into
  `out/_wip/r-adversary/<name>` (driver `run_queue.ps1`), compared to truth through a time map by `truthcmp2.py`
  (`cmp_<name>.json`). The variants are:
  - gain -12 dB and +12 dB (the +12 dB copy clips);
  - 48 kHz (soxr), MP3 192k (LAME), and a 10 s clip (17.3-27.3 s);
  - `atempo=0.9` (a time-stretch to 108 BPM), an a cappella (the fixture's own vocals stem), and 30 s of digital silence.
  - Dropped because the machine was saturated by r-platform's runs: mono and a 1.234 s delay.
  - The UD2 fallback was also exercised twice: `drums.kick_source=mix` on a copy of the synth folder (`synth_kickmix`),
    and the real drums stage run with `kick_source=mix` on MEGAFAUNA's cached upstreams (`drums_mix_devrun.py`).
- **UD1** was exercised through `parse_intent` with adversarial but ordinary typing (`ud1_probe.py`).
- **Tests.** The failing tests are in `tests/review/W4/adversary/`. The real-song tests read the newest max folder of
  each song: `$MVH_REVIEW_RUNS` first, then `out/_wip/ud2-kick`, then `out/_wip/integrator`.

## Perturbations of the synthetic song (truth comparison)

Each column is one `mvh analyze --profile max` run, offline. All finished with analyze 0 and validate 0.
- **Times:** gain, 48k and MP3 use the truth times as they are; the time-stretch scales them by 1/0.9.
- **Matching:** beats are matched within ±70 ms, drum hits within ±30 ms, section starts within ±0.5 s and words within ±0.15 s.
- **Source:** `out/_wip/r-adversary/cmp_<name>.json`.

| | baseline (ud2-kick/synth) | -12 dB | +12 dB (clips) | 48 kHz | MP3 192k | atempo 0.9 | a cappella | silence 30 s |
|---|---|---|---|---|---|---|---|---|
| BPM (truth 120 / 108) | 120.03 | 120.03 | 120.03 | 120.00 | 120.03 | 107.94 | 119.34 (conf 0.62) | 120 (virtual grid, `no_pulse`) |
| beats F / downbeats F | 1.00 / 0.98 | 1.00 / 0.98 | 1.00 / 0.98 | 1.00 / 0.98 | 1.00 / 0.98 | 1.00 / 0.98 | 0.55 / 0.18 | - |
| section starts F | 1.00 | 1.00 | **0.83** (bridge 25.0 -> 27.0) | **0.83** (outro 50.5 -> 52.5) | 1.00 | **0.77** (an extra outro inside the drop) | - | 1 section |
| section labels (truth intro verse chorus bridge chorus outro) | = truth | **intro inst inst build drop outro** | bridge -> **chorus** | = truth | = truth | bridge -> **chorus**, drop half -> **outro** | - | - |
| EDM build / drop (truth 25.0 / 34.5) | 25.0 / 34.5 | 25.0 / 34.5 | **27.0** / 34.5 | 25.0 / 34.5 | 25.0 / 34.5 | **none / none** | none | none |
| drum kick / snare / hat F | 1.00 / 0.99 / 0.93 | 1.00 / 0.98 / 0.91 | 1.00 / 1.00 / 0.94 | 1.00 / 0.98 / 0.93 | 1.00 / 0.97 / 0.88 | 0.92 / 0.99 / 0.71 (time-stretch artefacts) | no drum hits (correct) | 0 |
| agent kick source / count | drums 85 | drums 85 | drums 85 | drums 85 | drums 85 | drums 99 | **mix 13 (truth 0)** | mix 0 |
| key | A minor 0.52 | = | = | = | = | = (0.53) | A minor 0.30 | **C major** (`key:no_tonal_evidence`) |
| lyrics grade / words F | B / 0.91 | B / 0.91 | B / 0.91 | B / 0.91 | B / 0.91 | B / 0.91 | B / 0.93 | instrumental |
| vocal style / range conf | singing 0.53 | singing 0.50 | **speech** 0.38 | singing 0.53 | singing 0.53 | singing 0.54 | singing 0.52 | - |
| voices (truth 2) | 2 | 2 | 2 | 2 | 2 | 2 | 2 | skipped |
| stems | all present | **piano absent** (-54 dB, absolute threshold) | all | all | all | all | vocals | - |

**What holds.** Every run finished and validated.
- Beats, downbeats and tempo are perfect under gain, resampling, MP3 and time-stretch.
- MP3 decoding is gapless: `n_samples` is exact and the timing errors equal the baseline's.
- Kick, snare and toms are stable; the key is stable.
- Lyrics hold grade B with the same word F under every edit. The voice count is right under every edit.
- UD2's kick choice holds: drums everywhere, and `mix` on the a cappella and on silence.
- Silence degrades gracefully, with honest flags.

**What does not.**
- **Sections, labels and EDM roles move** under edits that keep the music the same: -12 dB, +12 dB, 48 kHz and 0.9x
  (W4A-GAIN, W4A-STABLE).
- **The a cappella invents an agent-facing kick timeline and drum structure** (W4A-ACAP).

Not run, for lack of machine time (r-platform held the slots): mono, the 10 s clip, and the 1.234 s delay. The
delay's timing question is answered by the MP3 run.

## UD1 and UD2: do they behave as decided?

**UD2 (kick source) mostly does.**
- One kick timeline is exposed: `song.kicks()` in the Python lib equals the `drum_hits` kick rows on MEGAFAUNA
  (342 = 342) and on the synth (85 = 85).
- `manifest.summary.kick_source` and `kick_agreement` equal `meta/drums.json` on all 5 songs.
- The brief's kick row and its per-section kick counts match my own counts.
- `qa:kick_sources_disagree` and the warning are raised on MEGAFAUNA only (0.46 / 0.25), as designed.
- hits.kick is precise on the synth: P 0.98, R 0.99 at 30 ms.

Two refutations:
- **The fallback leaves a second kick timeline (W4A-KICKCURVE, major).** When `kick_source = mix`, the `drums.kick`
  curve is still built from the drum-stem hits. RECIPES' frame-accurate kick recipe, the frames curve columns and
  choreo's accents read that curve.
- **The automatic choice keeps a noisy stem on MEGAFAUNA (minor, flagged).**
  - 16 % of the agent-facing kicks follow another kick within 100 ms; on the other songs it is 0 %.
  - The outro S17 has 16 kicks with a median vel of 0.13, 6 % of them on the 16th grid.
  - Inside the pulse regions, the drum-stem kick is on the 16th grid 57 % of the time (chance 25 %); hits.kick 52 %.
  - My own autocorrelation of the drop (drums, kick and snare stems and the mix) confirms the 105 BPM grid.
  - So neither timeline is clean. The QA flag tells agents so, which is the decided behaviour.

**UD1 (meaning input) holds for well-formed templates, but a typed hard rule can silently become a note
(W4A-UD1, major).** Free text never became a rule in any probe. The voices and meaning stages share one parser.

## Open W3 items: verified on the post-UD2 runs

| Item | Still real? | Evidence (post-UD2 runs) | Test |
|---|---|---|---|
| S06 kicks (UD2) | resolved as decided, with W4A-KICKCURVE in the fallback | see the UD2 section above | test_w4a_ud2_kick_curve.py |
| S16 backing-double mouths | **yes** | Newton L021: the BACKING span V1 (48.52 s + 1.97 s, conf 0.68) has 22 % backing_vocals stem support (one 0.59 s burst; my RMS: -60 to -73 dB elsewhere in the span). Two mouths stay open for 2.3 s | test_w4a_real_seams.py::..._backing_spans_... |
| S17 groove ids | **yes** | MEGAFAUNA 48 ids / 62 bars, Versatile 32 / 80. On MEGAFAUNA the kick/snare step rows alone give 61 distinct patterns in 62 bars, so exact-pattern clustering can't work on this transcription | ..._groove_ids_repeat_on_noisy_kits |
| S18 half-time feel | **yes** (needs the W4 decision) | Newton: 76 % of 113 strong snares on beat 3 at 138 BPM; `feel = normal` | ..._half_time_backbeat_... |
| S19 Jeremy hats | **yes** | 37 % of 495 hats (vel >= 0.3) on the 16th grid (chance 25 %). Independent cross-check: hits.high is 75 % on the grid, onsets.high 62 %, and the 68 hats confirmed by a hits.high event within 20 ms are 88 % on the grid. A hits.high confirmation would fix it | ..._jeremy_hats_... |
| m3 Newton S06 one bar late | **no** | V3->V2 at 69.44 s, S06 at 69.64 s (0.2 s) | - |
| m4 manifest at the cap | **yes, worse** | UD2 added `kick_source` / `kick_agreement`. MEGAFAUNA's `summary.stages` is now `{}` (all trimmed; it had 3 summaries before UD2); 11.4-11.6k characters everywhere | - |
| m5 licences | yes (unchanged) | run.json still lists them as unclear | - |
| Newton lyrics grade borderline | **yes** | grade C, G2 = 0.7479 vs 0.75 (a cliff of 0.002, with no hysteresis) | - |

## Findings

### Blockers
None.

### Majors (each has a failing test under `tests/review/W4/adversary/`)

| ID | Sev | Location (owner first) | Claim | Test |
|---|---|---|---|---|
| W4A-GAIN | major | M2: src/mvh/stages/allin1/__init__.py (level fed to allin1) + src/mvh/stages/structure/__init__.py (labels from allin1) | The section labels and grid depend on the master level. -12 dB (no clipping, all stems present): allin1 says `intro` for the whole song, and structure turns verse/chorus/bridge/chorus into inst/inst/build/drop. +12 dB (a hot, clipped master): the bridge and EDM build start one bar late (27.0 vs 25.0 s) and the bridge becomes chorus | test_w4a_perturbations.py::test_w4a_sections_survive_a_12db_gain_change, ::test_w4a_edm_build_start_survives_a_12db_gain_change |
| W4A-STABLE | major | M2: src/mvh/stages/structure/__init__.py (EDM roles: `drop_cue` / `at_peak` thresholds; section DP), fed by M1 dynamics | The same song at 0.9x tempo (beats still perfect) loses BOTH EDM roles, the drop section is split by an `outro` at 47.2 s, and the bridge is labelled chorus. A pure 48 kHz resample moves the outro one bar late (52.5 vs 50.5 s), because dynamics splits into 7 parts instead of 5 | ::test_w4a_edm_roles_survive_a_10pct_time_stretch, ::test_w4a_sections_survive_resampling_to_48k |
| W4A-ACAP | major | M1: src/mvh/stages/spectral (hits.kick on vocals), with M3a src/mvh/stages/drums/kick.py `choose_source` (agreement None -> low false) and M2 choreo (drum hit points / grooves without drums) | A cappella (truth 0 kicks): the fallback hands agents 13 kicks (kick_conf 0.68-1.00, each within 0.25 s of a sung word onset). There is no QA flag (`mix_in_drums` 0.0, `drums_in_mix` None -> `low: false`). The brief says "mix: 13 kicks". choreo makes 16 groove bars with kick/snare/hat rows and 7 `drum` hit points | ::test_w4a_a_cappella_has_no_agent_kicks, ::test_w4a_a_cappella_has_no_drum_hit_points |
| W4A-KICKCURVE | major | M3a: src/mvh/stages/drums/__init__.py `env = core.envelopes(hits)` (written for every kick_source) | Under the UD2 mix fallback, `drums.kick` (the RECIPES frame-accurate kick recipe, the frames `drums.kick` column, choreo accents) is still the drum-stem kick. MEGAFAUNA with kick_source=mix: 177 agent kicks against 316 curve peaks, agreeing only 0.47 / 0.28 at 30 ms. That is two kick timelines again (UD2.1) | test_w4a_ud2_kick_curve.py |
| W4A-UD1 | major | M6b: src/mvh/stages/meaning/intent.py `_NESTED` / `_load_region` / `_scan_unfenced` | The template's `do_not` (the ONLY hard constraints) is all-or-nothing. A tab-indented list, or one indented sentence after the list, demotes EVERY rule under it to a free-text note (warned only in meaning's warnings). `do_not:` + a blank line + `- item` (valid YAML) turns the rules into a note with NO warning | test_w4a_ud1_do_not.py (4 fail, 1 control passes) |
| W4A-VOCPHR | major | M3b: src/mvh/stages/vocals (vocal_phrases = voiced phrases of the lead) | S04 is only half fixed. MEGAFAUNA's vocal phrases cover 7.5 s of the 39.7 s of lyric-line time in which the vocals stem is active. The stem is active 54-88 % of S08/S09/S12/S13, and the lines cover 53-100 %. The brief's vocals column says 8-21 %, and the phrase and breath timing for the character is missing | test_w4a_real_seams.py::test_w4a_vocal_phrases_cover_the_sung_lines_megafauna |
| W4A-S16 | major | M5: src/mvh/stages/voices (backing span placement) | Newton's only BACKING span (V1 under V3, L021, 1.97 s, conf 0.68) has 22 % backing_vocals stem support. My RMS of the backing stem is -60 to -73 dB outside one 0.3-0.6 s burst. So two mouths are open for 2.1 s with no backing voice (the critic test still counts 2.3 s) | ::test_w4a_backing_spans_are_backed_by_the_backing_stem_newton |
| W4A-S17 | major | M2: src/mvh/stages/choreo (groove clustering), with M3a drums (kit transcription) | Still real after UD2: MEGAFAUNA has 48 ids for 62 bars, Versatile 32 for 80. On MEGAFAUNA the kick/snare step rows give 61 distinct patterns in 62 bars, so exact-step clustering cannot repeat. It needs a tolerant similarity (onset-envelope or accent-weighted) or a cleaner kit | ::test_w4a_groove_ids_repeat_on_noisy_kits |
| W4A-S18 | major | M2: src/mvh/stages/rhythm/fusion.py `feel_labels` (needs the W4 decision: a feel re-vote in choreo from drum_hits, or drums in rhythm's deps) | Still real: on Newton, 76 % of 113 strong snares land on beat 3 at 138 BPM, and `feel = normal` | ::test_w4a_half_time_backbeat_is_labelled_newton |
| W4A-S19 | major | M3a: src/mvh/stages/drums/core.py (hihat sub-stem) | Still real: 37 % of Jeremy's 495 hats with vel >= 0.3 are on the 16th grid (chance 25 %). Independent fix evidence: the 68 hats confirmed by a spectral hits.high event within 20 ms are 88 % on the grid (hits.high 75 %), so gate the hihat rows on hits.high / onsets.high | ::test_w4a_jeremy_hats_lock_to_the_grid |

### Minors (no test)

| ID | Location (owner first) | Claim / evidence |
|---|---|---|
| m-a | M3a: src/mvh/stages/stem_activity (`stems.vocals.present` vote) | MEGAFAUNA: meta/stems.json has vocals.present=false (conf 0.30), while vocal_range, 14 lines, one singer and visemes exist. The brief's stems row omits vocals (RUNS.md: "a stem marked absent is silence") |
| m-b | RUNTIME: src/mvh/runner/finalize.py `fit_manifest` | m4 got worse: after UD2 added kick_source / kick_agreement, MEGAFAUNA's `summary.stages` is `{}` (it had 3); every manifest is 11.4-11.6k characters |
| m-c | M6b: src/mvh/stages/brief/build.py `section_facts` (energy = dominant level) | A 50/50 tie hides the peak: the synth's drop section S05 shows `medium -22.4` although its first half is the song's only `peak`. Also MEGAFAUNA S16 and Jeremy S16 |
| m-d | M2: src/mvh/stages/structure/__init__.py `drop_cue` evidence | The brief and the drop moment say "kick 0.96->1.19/beat" (onset peaks per beat), but the truth and `song.kicks()` give 1.00/beat in the drop. Name it as an onset rate, or count the agent-facing kicks |
| m-e | M3b: src/mvh/stages/vocals (style) | +12 dB clipped master: vocal style `speech` (truth: singing), range conf 0.38 |
| m-f | M3a: src/mvh/stages/stem_activity (absolute -45 dBFS rule) | -12 dB: the piano stem is marked absent (median -54 dB). Presence should be relative to the mix |
| m-g | M1: src/mvh/stages/dynamics (novelty segmentation) | A 48 kHz resample changes the parts from 5 to 7 (42.5-56.5 s `medium` becomes `loud` + `soft`). That is the cause of W4A-STABLE's outro shift |
| m-h | RUNTIME / M4: manifest summary on silence | 30 s of digital silence: summary key `C major`, bpm 120, 11 eight-counts and 21 cues on a virtual grid. The flags (`no_pulse`, `key:no_tonal_evidence`) are present, but the summary values should be null |
| m-i | M2: structure on an a cappella | Section S03 (23.5-34.5 s) is labelled `silence` over 6 sung words (4.8 s of singing); the beat grid F is 0.55 |
| m-j | M5: src/mvh/stages/lyrics/grade.py | Newton is grade C on G2 = 0.7479 vs 0.75. A hard cliff with no hysteresis or "borderline" marker |
| m-k | M6b: intent.py region scanner | An untagged code fence containing `palette: red` / `do_not: blue` becomes template (do_not = blue). A whole template indented by 2 spaces, or `DO_NOT:`, silently becomes a note with no warning. Two answers to `tone:` keep the first with no warning |
| m-l | RUNTIME (integrator docs): docs/RUNS.md §7 kick row, docs/SEAMS.md S06 | Stale after UD2: RUNS.md still says "prefer drum_hits kicks with vel >= 0.5 ... W4 makes ...", and SEAMS lists S06 open |
| m-m | M3a: src/mvh/stages/drums/kick.py (MEGAFAUNA gate) | The agent-facing kick on MEGAFAUNA keeps 16 % of its kicks less than 100 ms after another (0 % on the other songs). The outro S17 has 16 kicks with a median vel of 0.13, 6 % on the grid. It is flagged (`qa:kick_sources_disagree`), as decided |
| m5 | M3a | Five model licences are still marked unclear (unchanged) |

## Reproduce
- Real-song probes: `out/_wip/r-adversary/{kickgrid,kicksec,crosscheck,energycheck,vocact,s16,libkick,tempo_indep}.py`
  (venv python, `MVH_FFMPEG` set for the audio ones).
- W3 critic tests on the post-UD2 runs: a copy is in `out/_wip/r-adversary/w3c` (RUNS = ud2-kick); 5 fail, 11 pass.
- Perturbations: `powershell -File out/_wip/r-adversary/run_queue.ps1 -NameList synth_gm12,...` (resumable), then
  `truthcmp2.py <run> [--scale 1.1111]`.
- UD2 fallback: `run_kickmix.ps1` (a whole run) and `drums_mix_devrun.py <folder>` (the drums stage alone on the cached upstreams).
- Tests: `scripts/run.ps1 python -m pytest -q tests/review/W4/adversary -p no:cacheprovider`. Results: 17 fail as intended
  and 4 controls pass (the plain do_not list, the unperturbed synth, MP3, and the second gain parameter of the build
  test).
