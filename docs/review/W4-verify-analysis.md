# W4 verification: analysis group (M1, M2, M3a, M3b, M4), round 2

Verifier: w4verify-analysis-r2. Fixer: w4fix-analysis-r2 (docs/build/reports/w4fix-analysis-r2.md, decisions W4-AN-9..11).
Numbers and lyric ids only. No lyric text appears here. Round 1 is kept below.

## Verdict

**fail.** The three round-1 findings are fixed. W4-AN-9 makes sections, labels, EDM roles, beats, bars, silences, feel and
chords invariant to the master level, on three songs at -6, -12 and -20 dB (Jeremy -6 dB: sections, beats, bars, silences, chords identical; vocal onset F 0.957). Under `kick_source = mix`, choreo follows the agent kick.

New findings:
- **blocker:** harmony crashes on a valid input (a NaN chord conf), and 12 downstream stages are not run.
- **three majors:** the fixed analysis level stops short of separate_hq/DrumSep, stem_activity and vocals. On a quieter copy
  of the same song, the UD2 agent kick, stem activity and vocal notes and phrases still change.
- **minors:**
  - spectral onsets and hits are level dependent;
  - Jeremy's hook section is labelled verse;
  - the new verse form rule W4-AN-11(d) is fitted to the sr32 case and fails at 22.05 kHz.

## Method

1. **Fixer folders.** I read the fixer's report, its decisions and the changed code:
   - `loudness/level.py`;
   - the level handling in allin1, rhythm, harmony and structure;
   - `dynamics` silence_rel_lu;
   - choreo's `mix_kick_rows` / `groove_min_hit_vel`;
   - rhythm's `decode_meter(late_bias)` / `backbeat_mid_min`;
   - structure's `drop_top_min_rise` / `verse_min_before_chorus`.

   I found no song-name or path special cases. Two of the new constants are fitted to one perturbation each (see W4V2-FORMRULE-NARROW).
   - Unit tests of the touched stages: 201 pass, 47 skip. ruff is clean.
   - The W3 critic on the fixer's r2 folders (redirect plugin): 18/18 pass. S17 grooves (MEGAFAUNA 18 ids / 63 bars, Versatile 16 / 72),
     S18 feel and S19 hats pass there.
2. **Fresh runs.** Seven fresh `mvh analyze --profile max` runs from audio, offline, into
   `out/_wip/w4verify-analysis-r2/<name>`, made by `run_queue.ps1` (resumable) from `inputs/` (ffmpeg, 24-bit):

   | Run | Input | analyze / validate |
   |---|---|---|
   | megafauna_gm20 | MEGAFAUNA `volume=-20dB` | 0 / 0 (1469 s) |
   | versatile_gm12 | Versatile `volume=-12dB` (the fixer never checked Versatile) | 0 / 0 (1231 s) |
   | jeremy_gm6 | Jeremy `volume=-6dB` | 0 / 0 (1288 s) |
   | synth_base | the synthetic truth flac | 0 / 0 (1463 s) |
   | synth_tempo105 | `atempo=1.05` (an edit the fixer never tuned on) | **1** / 0 (harmony crash) |
   | synth_sr22 | soxr resample to 22.05 kHz | 0 / 0 (493 s) |

   The fresh synth_base equals the fixer's synth on every compared output: sections, EDM roles, beats, bars, every drum, vocal notes and
   phrases, chords, grooves, and the stem activity curves. So a fresh separation is deterministic, and the differences below come from
   the level, not from run-to-run noise.
3. **Fixer re-analyses.** The fixer's re-analyses of round 1's -12 dB copies (`out/_wip/w4fix-analysis-r2/{megafauna,jeremy}_gm12`)
   were compared with its baselines.
4. **Kick fallback.** drums (`kick_source = mix`) and choreo were run on the cached upstreams of MEGAFAUNA, Versatile and Jeremy
   (`tests/review/W4/verify-analysis/w4va_devchain.py`).
5. **Regression scan.** The integrator's W3 folders were compared with the fixer's r2 folders (`out/_wip/w4verify-analysis-r2/cmp.py`).

## Round-1 findings

| ID | Result | Evidence |
|---|---|---|
| W4V-GAIN-REAL (major) | **Fixed** | Against the fixer's baseline: MEGAFAUNA -12 dB, MEGAFAUNA -20 dB (fresh), Versatile -12 dB (fresh) and Jeremy -12 dB have identical section starts and labels (17 / 17 / 18 / 18 sections), EDM roles, silences (MEGAFAUNA 38.87 s / 1.06 s at every level), feel segments, key and chords (agreement 1.000). `allin1.json.level` gain: +0.81 dB (original) vs +12.81 / +20.81 dB. |
| W4V-GAIN-BEATS (major) | **Fixed** | Beat F 1.000 and bar F 1.000 (70 ms) for all four pairs; tempo 105.134 / 130.279 / 107.236 at every level. |
| W4V-KICKCURVE-CHOREO (major) | **Fixed** (the round-1 test was too strict) | With `kick_source = mix`, `meta/grooves.json.kick_rows` = `hits.kick`. Groove kick steps on an agent kick: MEGAFAUNA 0.981, Versatile 1.000, Jeremy 1.000. Steps only on a rejected stem kick: 0.006 / 0 / 0. Every `drum` hit point without an agent kick (MEGAFAUNA 160.12 / 194.40 s, Versatile 100.62 s, Jeremy 19.47 / 126.01 / 147.60 / 154.28 s) has a drum-stem snare of vel 0.65-1.0 at the same instant. That snare is a valid `drum` kind; UD2 rejected only the stem kick. The test now accepts an agent kick or a stem snare of vel >= 0.5 and runs on three songs: 3/3 pass. |

## New findings

### W4V2-HARMONY-NAN (blocker, M4): harmony crashes on a valid song
- **Input:** synth at `atempo=1.05` (53.82 s).
- **Cause:** the chord decode ends with a 2 ms trailing `N` segment [53.820, 53.822), which starts after the last chroma frame
  (53.812 s). `chords.verify_segments` (src/mvh/stages/harmony/chords.py:218) takes `cf.energy[a:max(b, a + 1)].mean()` with
  a = b = frame count. The slice is empty, so the mean is NaN, the conf is NaN, and `ctx.writer.events("chords")` raises
  `ValueError: Out of range float values are not JSON compliant: nan`.
- **Effect:** harmony fails. structure, lyrics, mood, vocals, choreo, cues, voices, lipsync, meaning, brief and viewer are not run
  (analyze rc 1). The failure is deterministic: re-running cannot help, and no parameter avoids it.
- **Not caused by the round-2 level change:** harmony with `analysis_lufs = null` fails the same way on that cache. The bug was
  already there; a new perturbation exposed it.
- **Test:** `test_w4va2_harmony_tail_crash.py` (unit, synthetic chroma). End to end:
  `test_w4va_perturbations.py::test_w4va_synth_*_survive_other_edits[synth_tempo105]`.
- **Fix:** guard empty slices in `verify_segments` (and `aggregate`), and drop or merge sub-frame segments at the song end. A
  stage should also never write a non-finite conf.

### W4V2-GAIN-DRUMS (major, M3a separate_hq + drums): the UD2 agent kick and the strong drum hits follow the master level
- **Cause:** separate_hq runs audio-separator with normalisation off (`normalization_threshold` 100, `amplification_threshold` 0),
  so DrumSep sees the master-level drum stem. The ROFormer stems are level-stable: a gain copy restored by +12 dB matches the
  original at 35.6 dB SDR (lead vocals) and 32.4 dB (drums). DrumSep is not: Versatile's toms differ at 8.9 dB SDR, crash at 13.0 dB
  and kick at 25.9 dB.
- **UD2 agent-facing kick (`kick_source = drums`):**
  - Versatile -12 dB: 109 -> 102 kicks, F 0.957. 8 kicks lost, 6 of them with vel >= 0.5 (32.8-36.9 s, 144-155 s); at the same
    instants the copy has a tom (vel 0.4-1.0) or a snare instead.
  - MEGAFAUNA -12 dB: F 0.949, +5 strong kicks.
  - MEGAFAUNA -20 dB: F 0.922, +9 strong kicks.
- **Strong cymbals:** Versatile F 0.44 (2 lost, 6 added); MEGAFAUNA 9 lost / 14 added (-12 dB) and 9 / 16 (-20 dB).
- **Test:** `test_w4va2_level_and_labels.py::test_w4va2_agent_kick_and_drum_hits_survive_a_gain_change` (fails on
  megafauna_gm12, jeremy_gm12, megafauna_gm20 and versatile_gm12).
- **Fix:** run the separators on the analysis-level copy (the W4-AN-9 mix gain), then scale the stems back by the inverse gain, so
  the sum invariants and the dBFS measurements are unchanged.

### W4V2-GAIN-STEMACT (major, M3a stem_activity): "who plays when" follows the master level
- **Cause:** stem_activity gates on an absolute `active_db` of -45 dBFS. On a quieter copy, the stems drop below it.
- **Active share, original -> copy (frame agreement):**

  | Copy | Stem | Active share | Agreement |
  |---|---|---|---|
  | MEGAFAUNA -12 dB | drums_kick | 0.544 -> 0.406 | 0.863 |
  | MEGAFAUNA -12 dB | drums_snare | 0.599 -> 0.501 | 0.902 |
  | MEGAFAUNA -12 dB | crash | 0.181 -> 0.101 | 0.920 |
  | MEGAFAUNA -12 dB | vocals | 0.406 -> 0.338 | 0.932 |
  | Versatile -12 dB | bass | 0.856 -> 0.792 | 0.935 |
  | Versatile -12 dB | other | 0.897 -> 0.837 | 0.940 |
  | Jeremy -12 dB | crash | 0.438 -> 0.354 | 0.911 |

  The present flags did not flip.
- **Test:** `test_w4va2_stem_activity_survives_a_gain_change` (fails on all five pairs; Jeremy -6 dB only crash, agreement 0.962).
- **Fix:** make the threshold relative to the analysis level (measure on the W4-AN-9 scaled stems, or apply `active_db` after
  that gain).

### W4V2-GAIN-VOCALS (major, M3b vocals): vocal notes and phrases follow the master level
- **Cause:** the presence gate `loud = level > max(level_floor_db = -55, p99 - 35)` (src/mvh/stages/vocals/__init__.py:174)
  binds on the absolute -55 dB whenever the lead stem's p99 is below -20 dB:
  - MEGAFAUNA: p99 -53.3 dB (-65.3 at -12 dB);
  - Jeremy: p99 -12.5 dB (-24.5 at -12 dB).
- **Effect on sparse-vocal songs:**

  | Copy | notes.vocals (onset F) | Phrase coverage (IoU) |
  |---|---|---|
  | MEGAFAUNA -12 dB | 33 -> 15 (0.375) | 40.0 -> 31.2 s (0.779) |
  | MEGAFAUNA -20 dB | 33 -> 8 (0.244) | 40.0 -> 28.0 s (0.698) |
  | Versatile -12 dB | 27 -> 13 (0.600) | 10 -> 4 phrases, 6.1 -> 2.1 s (0.347) |

  The `vocal.voiced` share on Versatile falls from 0.025 to 0.009. Jeremy (a dense vocal) holds: onset F 0.932, IoU 0.951.
- **Test:** `test_w4va2_vocal_notes_and_phrases_survive_a_gain_change` (fails on megafauna_gm12, megafauna_gm20 and
  versatile_gm12).
- **Fix:** gate on the analysis-level copy (W4-AN-9 gain), or make the floor relative only.

### W4V2-GAIN-SPECTRAL (minor, M1 spectral): mix onsets and hits follow the master level
- **Cause:** the absolute `gate_db` of -46 dB, which `gate_margin_db` lowers only partly for quiet masters.
- **Strong events (strength >= 0.6), F at 30 ms against the original:**

  | Copy | hits.mid | hits.high | onsets.bass |
  |---|---|---|---|
  | MEGAFAUNA -12 dB | 248 -> 329 (F 0.856) | 0.820 | 0.764 |
  | MEGAFAUNA -20 dB | 0.766 | - | 0.646 |
  | Jeremy -12 dB | 238 -> 323 (F 0.848) | - | - |
  | Versatile -12 dB | - | - | 0.754 |

  hits.kick holds (F 0.997-1.0).
- **Severity:** minor, because these lanes are viz-parity signals and choreo uses them only on thin evidence.
- **Test:** `test_w4va2_spectral_onsets_and_hits_survive_a_gain_change`.

### W4V2-JEREMY-HOOK-VERSE (minor, M2 structure): a hook section is labelled verse
- **What changed:** at the fixed level, structure puts a boundary at 185.07 s (W3: 194.10 s). The 176.12-185.07 s piece becomes
  a singleton repeat group (F) and takes allin1's own label, verse (allin1's raw segment label at 176.1 s is 'verse' in every
  run; the W3 folders called it chorus through repeat group D).
- **Why it is wrong:** its only lead lyric line belongs to text group T11, which recurs in 6 chorus sections.
- **Test:** `test_w4va2_a_section_holding_only_the_chorus_hook_is_not_a_verse[jeremy]`. It passes on the integrator's and the
  round-1 folders.

### W4V2-FORMRULE-NARROW (minor, M2 structure): the W4-AN-11(d) verse rule is fitted to one case
- **The rule:** a singleton `chorus` right before the first chorus of a repeated group becomes `verse` only when allin1's verse
  probability is >= 0.25. synth_sr32 has 0.36.
- **Where it fails:** at 22.05 kHz, allin1 gives that section verse 0.15 / chorus 0.79, and it stays `chorus` (labels intro,
  chorus, chorus, bridge, chorus, outro). Section starts, EDM roles, beats and bars are all correct.
- **Test:** `test_w4va_perturbations.py::test_w4va_synth_sections_survive_other_edits[synth_sr22]`.
- **Fix:** rely on the form condition, which is strong on its own (two different chorus groups back to back, before the first
  chorus), rather than a probability threshold tuned to one case.

## W3 open items (my modules)
- **S06 kicks (UD2):**
  - choreo now follows `kick_source` (above);
  - MEGAFAUNA's stem kick passes the quality check (`kick_source = drums`, agreement 0.249 flagged `low`);
  - the agent kick is level dependent (W4V2-GAIN-DRUMS).
- **S17 grooves:** pass. MEGAFAUNA 18 ids / 63 bars, Versatile 16 / 72 (W3: 45 / 63 and 36 / 80).
- **S18 half-time:** pass. Newton 0-145 s; Versatile 82.6-108.4 s and 166.2-199.0 s. The spurious MEGAFAUNA 89-100 s and Versatile
  outro spans are gone (W4-AN-11b).
- **S19 Jeremy hats:** the critic test passes (hats 975 -> 311).
- **m3:** Newton's V3 -> V2 voice change is now at 69.44 s, against section 69.64 s (W3: 67.6 s). Resolved.
- **S16 backing mouths, the Newton lyrics grade, m4, m5:** outside the analysis group (M5 / M6b / platform), so not verified here.

## Observations (no finding)
- **MEGAFAUNA intro bar phase (W4-AN-11a):** against W3, bar F is 0.56: the 3-beat bar(s) moved from 44.6 s to 91-96 s. The 0-91 s
  intro has no strong drum hit, and allin1's own downbeats (16 in 0-91 s) fit neither grid. So which phase is right cannot be
  judged. The section starts moved by one beat (0.57 s).
- **Versatile labels:** they switched from allin1 mode to structural mode (drop / breakdown / break). This is stable across levels
  now (versatile_gm12 is identical); the EDM roles are unchanged.
- **Small level effects:** MEGAFAUNA impacts keep their strengths and deltas, but 3 of 22 move by 0.1-0.6 s at -20 dB. Faint drum
  hits (vel < 0.3) also differ by level.

## Tests (tests/review/W4/verify-analysis)
- **Defaults:**
  - `w4va_support.RUNS` = `out/_wip/w4verify-analysis-r2`;
  - `BASE` = `out/_wip/w4fix-analysis-r2`;
  - `run()` falls back to BASE for round 1's names.
- **Gain tests:** parametrized over `GAIN_PAIRS`: megafauna_gm12, jeremy_gm12, megafauna_gm20, versatile_gm12, jeremy_gm6.
- **Synth edits:** add synth_tempo105 and synth_sr22.
- **New files:**
  - `test_w4va2_level_and_labels.py`;
  - `test_w4va2_harmony_tail_crash.py`;
  - `w4va_devchain.py` (it runs real stages on cached upstreams).
- **Command:** `.venv/Scripts/python.exe -m pytest -q tests/review/W4/verify-analysis -m "slow or not slow"` (MVH_OFFLINE=1).

---

# W4 verification: analysis group (M1, M2, M3a, M3b, M4), round 1

Verifier: w4verify-analysis-r1. Fixer: w4fix-analysis (docs/build/reports/w4fix-analysis.md, decisions W4-AN-1..8).
Numbers only. No lyric text appears here.

## Method

1. Re-ran the fixer's review checks on its folders (`out/_wip/w4fix-analysis/<name>`, current code, rc.3):
   - W4 adversary perturbations: 10/10 pass;
   - real seams plus kick curve: 6/6 pass;
   - W3 critic: 18/18 pass.
   The unit tests of the eight touched stages pass (194), and ruff is clean.
2. Read the new code for test-specific hacks:
   - there are no song-name or path special cases; the songs are named only in comments;
   - the thresholds are per-song statistics (hat confirm share, singleton share, backbeat ratio).
   One structural problem: the synthetic song's stems (-20.4 LUFS) sit *below* the new allin1 level band [-16, -6] LUFS.
   So the baseline and the adversary's -12 dB copy both reach allin1 at exactly -16 LUFS: the W4A-GAIN test passes by
   construction. A real master sits inside the band and keeps its own level.
3. Seven fresh `mvh analyze --profile max` runs from audio, offline, into `out/_wip/w4verify-analysis-r1/<name>`. Every
   run finished with analyze 0 / validate 0. The inputs were made with ffmpeg (`inputs/`, `run_queue.ps1`):

   | Run | Input |
   |---|---|
   | synth_base | the truth flac, as is |
   | synth_tempo110 | `atempo=1.1` |
   | synth_tempo95 | `atempo=0.95` |
   | synth_sr32 | soxr resample to 32 kHz |
   | megafauna_gm12, jeremy_gm12 | `volume=-12dB`, 24-bit; no clipping |
   | newton_acap | the fixer's Newton `stems/vocals.flac`: a real rap a cappella with plosives |

4. The real drums stage with `kick_source = mix`, then choreo on its output, on the fixer's MEGAFAUNA cache
   (`devrun.py`, tag `meg_mix`).

## Verdicts on the addressed findings

| Finding | Verdict | Evidence |
|---|---|---|
| W4A-GAIN | **NOT FIXED on real songs** | MEGAFAUNA at -12 dB: allin1 sees the stems at -16 LUFS instead of -11. Its segments and labels change, and so do the final sections: 5 starts lost, 4 added, and a new `silence` section at 38.57 s. Jeremy at -12 dB: the 94.66 s boundary is lost, the bridge at 149.24 s becomes `chorus`, and the outro end moves. The fix holds on the synthetic song only because that song is below the band. |
| W4A-STABLE | fixed | The fixer's sr48 and tempo90 runs pass. New edits also pass: 1.1x and 0.95x tempo and 32 kHz each give the truth sections, labels and EDM roles. A fresh synth run equals the fixer's synth (same sections, EDM roles and event counts). |
| W4A-ACAP | fixed | The synthetic a cappella has 0 agent kicks, 0 grooves and 0 drum hit points. The real rap a cappella has 0 hits.kick (the formant gate holds on plosives) and 1 stem kick. Its drum hits, grooves and drum hit points start at 145 s, where the vocal stem carries the original's outro drums as bleed (17 of 27 hits coincide). Side effect, minor: see N3. |
| W4A-KICKCURVE | **partly fixed** | The drums.kick curve now follows hits.kick under `mix` (the test passes). But choreo ignores `kick_source`: under `mix`, 99 % of its groove kick steps follow the rejected stem kick (35 % follow an agent kick), and 5 of its 6 `drum` hit points have no agent kick within 30 ms. Finding N2. |
| W4A-VOCPHR | fixed | MEGAFAUNA has 9 phrases totalling 39.9 s, and 99 % of the sung line time is inside a phrase. Newton went from 23 phrases to 12 (25-33 s phrases over continuous rap; the lead stem has almost no dips there, so this is plausible). At -12 dB MEGAFAUNA has 7 phrases totalling 31.2 s: this is level-dependent too (part of N1). |
| W4A-S17 / S17 | fixed | Groove ids per bar: MEGAFAUNA 18/62 (15/62 at -12 dB), Versatile 17/80. The merged clusters are loose but plausible: MEGAFAUNA member-to-centroid cosine on the kick/snare steps has a mean of 0.82, a p10 of 0.64, and 7 % of the bars are below 0.5. Clean kits are not touched. |
| W4A-S18 / S18 | fixed (Newton) | Newton: feel half_time, 0.85. In the half-time span, 75 of 90 strong stem snares land on beat 3. Versatile's local runs: 24 of 28. New spurious spans are minor: see N4. |
| W4A-S19 / S19 | fixed | Jeremy hats (vel >= 0.3): 153, 0.745 of them on the 16th grid (0.772 at -12 dB). The dropped hats sit on the grid at chance level, so they were bleed. Only Jeremy is gated. |

## Findings (tests in tests/review/W4/verify-analysis/)

### N1 (major, M2 allin1 + M1 dynamics): W4A-GAIN is not fixed on real masters
- **Evidence.** The fixer's band keeps a real master at its own level (MEGAFAUNA stems -10.98 LUFS, gain 0). After a
  -12 dB edit they arrive at -22.98 LUFS and get +6.98 dB, so allin1 sees -16 LUFS, 5 dB below the original. Its
  segments change: inst 19.1 s becomes intro, inst 123.5 s becomes intro, a new boundary appears at 150.96 s, 185.25 s
  moves to 194.4 s, and a new outro appears at 217 s.
- **Final sections.**
  - MEGAFAUNA: starts 19.55, 37.76, 71.2, 80.26 and 185.26 are lost; 18.25, 38.57 (`silence`), 43.36 and 79.33 are added.
  - Jeremy: 94.66 is lost, the bridge at 149.24 is relabelled `chorus`, and the outro / silence ends move.
  - The EDM roles are unchanged on both songs.
- **Second mechanism (M1 dynamics).** `silence_cap_lufs = -45` is an absolute cap (src/mvh/stages/dynamics/__init__.py:48).
  On a loud master the cap binds: -45 LUFS is 39 LU below MEGAFAUNA's integrated level. At -12 dB the relative rule
  (-30 LU) binds instead. So the silence at 38.6 s grows from 1.28 to 2.95 s and becomes a section.
- **Tests.**
  - `test_w4va_perturbations.py::test_w4va_real_song_sections_survive_a_12db_gain_change[megafauna|jeremy]` fails.
  - The EDM-role variants pass.
- **Suggested fix.** Normalise the level (one fixed LUFS) before every level-dependent analysis: the allin1 input, and
  the dynamics silence cap (relative only, or measured on the normalised copy). The integrator could instead give the
  analysis models one loudness-normalised mix copy (a RUNTIME / ingest change). Then test on a real song, not only on the
  synthetic one.

### N1b (major, M2 rhythm): the beat and downbeat grid depends on the master level
- **Evidence.** MEGAFAUNA at -12 dB, against the original:
  - beat F 0.665 and downbeat F 0.60 at 70 ms; in the first 30 s, beat F is 0.22 (the intro grid moves from about
    122/105 BPM to 88 BPM);
  - the trackers change: beat_this from 162.2 to 200 BPM, madmom from 193.5 to 206.9 BPM;
  - they are bit-identical across three earlier runs of the original, so the change is not run-to-run noise.
  Jeremy at -12 dB: beat F 0.957, downbeat F 0.915 (intro and outro tempo segments).
  The adversary's "beats unchanged" holds only on the synthetic song.
- **Test.** `test_w4va_real_song_beat_grid_survives_a_12db_gain_change[megafauna|jeremy]` fails.
- **Suggested fix.** Feed the trackers (beat_this, madmom, librosa) a loudness-normalised copy, the same remedy as N1.

### N2 (major, M2 choreo, with M3a): under the UD2 mix fallback choreo still uses the rejected stem kick (W4A-KICKCURVE, partly fixed)
- **Evidence.** The real drums stage with `kick_source = mix`, then choreo, on MEGAFAUNA:
  - 162 agent kicks (hits.kick) and 342 stem kicks;
  - 212 groove kick steps: 99 % are within 60 ms of a stem kick, 35 % of an agent kick;
  - 5 of the 6 `drum` hit points have no agent kick within 30 ms.
  choreo reads the `drum_hits` kick rows (accents, grooves, hit points) and never reads `meta/drums.json` `kick_source`.
  No current max run uses `mix`, but any song whose stem kick fails the quality check would.
- **Test.** `test_w4va_kick_mix_choreo.py` (runs drums and choreo, about 15 s) fails.
- **Suggested fix.** In choreo, when `kick_source == mix`, replace the kick rows with hits.kick (strength-scaled vel)
  before the accents, grooves and hit points.

### N3 (minor, M2 allin1 → rhythm): the synthetic a cappella now gets a half_time feel
- **Evidence.** The fixer's own `synth_acap` has feel_shares half_time 0.177, with a half_time segment from 8.5 to 18.5 s.
  The backbeat vote gives 0 beats, so the half_time comes from the tracker feel. The pre-fix run had normal 1.0.
  Cause: the band raises the quiet a cappella's stems by +6.5 dB, and allin1 then finds 9 beats at 60.9 BPM.
  The fixer's report says "a cappella normal".
- **Test.** `test_w4va_a_cappella_feel_is_not_half_time[fixer_synth_acap]` fails; Newton's real a cappella passes.

### N4 (minor, M2 rhythm): spurious half-time spans with no snare backbeat
- **Evidence.**
  - MEGAFAUNA, 89.3-99.5 s, a new span (the ud2-kick run had none): 3 strong stem snares, all on beats 2 and 4. The mix
    snare band (hits.mid) has none on beat 3 either.
  - Versatile, 211.8-227.5 s (the outro): no kick or snare at all, only 13 hats.
- **Test.** `test_w4va_real_seams.py::test_w4va_half_time_spans_have_a_beat3_backbeat[megafauna|versatile]` fails; Newton passes.
- **Suggested fix.** Require snare-band onsets in the window (a minimum flux or onset count at beat 3) before a run starts.

## Still-open W3 items (checked, as asked)
- **S17, S18, S19:** fixed. See the table above, with the minors N4.
- **S06 kicks (UD2):** MEGAFAUNA keeps `kick_source = drums` with `qa:kick_sources_disagree` (agreement 0.25). That is by
  UD2 design (the drums agent's quality gate), outside this group's fixes.
- **S16, m3-m5, the Newton lyrics grade:** not in this group's scope (M5).
