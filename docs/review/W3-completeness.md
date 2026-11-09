# W3 completeness matrix (critic-w3, R-CONTRACT lens: "the video agent")

Reviewer: critic-w3 (W3 completeness critic, PLAN §11/§12). Date 2026-11-09.

**Method.** I acted as an agent building a choreographed, character-driven art-piece video (Remotion / three.js / Blender /
ComfyUI). I used only the integrator's max-profile output folders `out/_wip/integrator/<slug>/` (contract 1.0.0-rc.2,
made before the W3 module fixers ran), `skill/mv-harness/SKILL.md` and `RECIPES.md`, and the folder's own `lib/`.
- Probes (numbers only, no lyric text) are in `out/_wip/critic-w3/`:
  - `probe.py` measures every requirement on every song;
  - `deep.py`, `phase.py` and `hat.py` check whether beats line up with the drums;
  - `overlap.py`, `singer.py` and `lyricat.py` check singers and lip-sync;
  - `jsprobe.mjs` and `pyprobe.py` compare the JS and Python loaders on real folders;
  - `rt_step.ps1` runs the override round trip on a copy of the synthetic folder (`rt-synth/`).
- Failing tests for the new findings are in `tests/review/W3/critic/`. Run them with
  `scripts/run.ps1 python -m pytest -q tests/review/W3/critic -p no:cacheprovider`: 15 fail as intended and 3 controls pass.
- Seams already open in `docs/SEAMS.md` (S03 to S09) are listed where they apply. I did not file them again.

Songs: **MF** = MEGAFAUNA (217 s, electronic), **VS** = Versatile (228 s, instrumental electronic), **JR** = Jeremy
(317 s, grunge, one singer), **NN** = Newton vs Nye (170 s, rap battle, announcer + 3 rappers), **SY** = synthetic
(56.5 s, scored against `_truth`).

Legend: OK = present and plausible; ~ = present, with a caveat; X = missing, wrong or unusable (it is a finding).

## 1. Requirements R1-R20

| Req (priority) | Producing stage (owner) | Tests that cover it | Present and plausible in each real song (numbers) | Usable by a choreography / character agent | Licence recorded |
|---|---|---|---|---|---|
| R1 Tempo & beats (Must) | rhythm (M2) | unit/rhythm/* (fusion, stage, real_songs), review/M2, integration/M2 | MF ~: 105.1 BPM, conf 0.75, `tempo_trackers_disagree`; no pulse from 29.8 to 95.6 s; drum kicks with vel >= 0.3 sit within 1/32 beat of a 16th position 72 % of the time (snares 77 %), so the grid holds at the 16th level. VS OK: 130.2 BPM, conf 0.96; 95 % of kicks on the 16th grid. JR OK: 107.15 BPM, conf 0.97, all 4 trackers agree; kicks 91 % and snares 90 % on the grid; snares land 95 % on beats 2+4; a 3/4 bar in the free-time intro. NN ~: 138.0 BPM, conf 0.94; kicks 98 % on the grid, but **76 % of the strong snares land on beat 3** (a half-time backbeat) while the feel is labelled `normal` (**W3C-3**); VS shows the same pattern (50 % on 3). SY OK: beats F1 1.00, downbeats 0.98 | ~ count/beatPhase/barPhase are fine; the feel label misleads the dance pulse on half-time songs (W3C-3) | OK: beat_this, madmom (CC-BY-NC-SA) and allin1 are in run.json and provenance |
| R2 Structure (Must) | structure (M2) | unit/structure/*, review/M2 (F4-r3, F6-r3 open), integration/M2 (S05, S09) | Sections tile the song (gap 0) on all songs. NN OK: 3 of the 4 voice changes fall within 0.7 s of a section start; V3->V2 at 67.6 s falls 2.1 s (about 1 bar) before S06 (minor m3). JR ~: 20 sections, 12 of them labelled chorus (C/D pairs repeat, plus 5 outro "chorus" sections with label conf 0.4-0.7); verse#1 starts one bar after the band entry (S05, open). MF ~: build 123.5 s, then a drop from 141.8 s lasting 34.3 s; the loud plateau runs to 217 s (M2 F6-r3, open). VS OK: drops at 84.9 and 162.5 s, breakdowns at 129.2 and 144.0 s, matching the dynamics peaks. SY ~: intro labelled verse (S09) | ~ The labels are coarse; repeat_group and edm_roles are the useful handles | n/a (allin1 MIT) |
| R3 Spectral bands (Must) | spectral (M1) | unit/spectral/*, review/M1 (2 blockers + 2 majors open: kick events) | All 5 songs have bands.{bass,mid,high} (+ _db, _viz), 7 fine bands (+ _db), spectrum128.u8, hits.{kick,mid,high} (+ _raw), and onsets per band (JR: 1127/414/595). No NaN. `hits.kick` and the DrumSep kick disagree on MF (42 % / 23 %, S06, open) | ~ Two kick timelines and no stated precedence (S06) | n/a (DSP) |
| R4 Loud & quiet (Must) | loudness, dynamics (M1) | unit/loudness, unit/dynamics, review/M1 | OK. Integrated loudness: MF -10.8 LUFS (LRA 17.9), VS -6.1 (LRA 14.3, true peak +3.9 dBTP, 13,369 clipped samples, matching SPIKE's +4.1), JR -7.0 (LRA 6.5, `limited_master`), NN -10.1 (LRA 3.5). Dynamics segments: MF 11, VS 14, JR 10, NN 9. Impacts: JR 1 (19.47 s, the band entry), NN 20, MF 22. Silences sit at the edges and in MF's breaks. Stops: 0 on the real songs, 2 on SY (= truth) | OK `dyn.intensity`, `loud.short_term` and `events('dynamics')` | n/a |
| R5 Stems (Must; drum sub-stems Should) | separate_hq, stem_activity (M3a) | unit/separate_hq, unit/stem_activity, review/M3a, integration/M3a | OK on all songs: 9 stems plus 6 drum sub-stems, all ROCm, none degraded, lead/backing split; sum error -28 to -30 dB. A float `.wav` twin is written next to stems with \|x\|>1 (JR: 7 of them), as documented | OK | OK, but 5 entries are marked unclear or unverified (sep.mdx23c-drumsep, mel-roformer karaoke and vocals, htdemucs weights): a known SPIKE gap (minor m5) |
| R6 Instruments (Must) | instruments (M3b) | unit/instruments/*, review/M3b | ~ 1 Hz curves for 32 instruments, segments and a summary. JR: guitar, bass, distorted guitar, drums, voice (plausible for grunge). VS: bass, drums, synth 59 %, drum_machine (plausible). MF: guitar 37 %, synth 3 % (no ground truth; SPIKE mentions synth leads, so the result is doubtful). The CLAP synth subtypes are present as relative curves. The open vocabulary works through `params.vocabulary` (none in these runs) | ~ Use it as a coarse cue | OK (CED, CLAP Apache-2.0) |
| R7 Notes (Must) | notes; notes.vocals from vocals (M3b) | unit/notes/*, unit/vocals | OK. JR: bass 1073, guitar 2668, other 94, piano 0 (no piano), vocals 588. `notes.mid` has a tempo-map track (JR: 556 set_tempo, 3 time signatures) plus one track per source; vocals go to `vocals.mid` (D6). Density and range per source are in notes.json. SY: `fallback:piano:basic_pitch`, degraded | OK `events('notes.bass')` | OK |
| R8 Drum hits (Must) | drums (M3a) | unit/drums, review/M3a (R3-1 ride/crash open) | NN, VS and SY OK (kick 98/95/81 % on the 16th grid). **JR: 988 hats; only 37 % of the strong ones are on the 16th grid (chance 25 %, kick 91 %, snare 90 %)**: the hat class is mostly not hi-hat strokes (**W3C-4**). MF ~ (hats 61 %, kicks 72 %) | X for hats on rock (W3C-4); it also corrupts the groove hat row | OK |
| R9 Vocal range (Must) | vocals (M3b) | unit/vocals/*, integration/M3b (S04) | JR OK: E3-C#5, tessitura A3-A4, tenor, conf 0.87, 42 phrases, 588 notes, singing 72 % / speech 28 %. NN ~: style rap; the sung range is null by design; spoken_pitch is given; pitch01 works. SY OK: G3-A4 (truth range ok). **MF X: present=false, 0 phrases, 0 notes, although 14 lines, 1 voice and 177 visemes exist (S04, open)**. VS OK: present=false (instrumental) | ~ `vocalAt` never returns NaN (checked) | OK (RMVPE MIT, SwiftF0) |
| R10 Harmony (Must) | harmony (M4) | unit/harmony/*, review/M4 (R3-M1 open) | Chord starts lie on beats (96-100 %). Keys: JR A minor (A major for 0-122 s at conf 0.5, `parallel_ambiguity`), NN A minor (`fifth_ambiguity`), VS A minor, MF A min -> D maj -> D min (`models_disagree`), SY A minor (= truth). NN: a 14.2 s "N" (no chord) covers exactly section S04; unverified | ~ The key flags are honest | OK (S-KEY NC weights noted) |
| R11 Lyrics (Must) | lyrics (M5) | unit/lyrics/*, review/M5 (4 majors open), integration/M5 (S03) | NN OK: LRCLIB, offset -1.31 s applied, grade B, 53 lines / 479 words, 98.5 % of the words inside vocal phrases. **JR: grade D for a correct synced text; 64 s of vocal phrases after 217 s have no lines (S03, open)**. MF: embedded text, grade D, ASR no-VAD. VS: instrumental, no lines (correct). All exports exist (lrc, vtt, srt, ass), and `lines.tsv` has the documented columns. **NN: the last word of a line runs up to 1.5 s into the next line (47 of 53 pairs; W3C-5)** | ~ `lyricAt` picks the newest line (checked: 0 of 44 overlaps gave the stale line); the overlap still breaks singers (R16) | OK (MMS_FA CC-BY-NC, whisper MIT) |
| R12 Identity (Must; AcoustID Should) | ingest (RUNTIME), identity (M5) | unit/identity, unit/ingest | OK from the tags on all 4 songs (title, artist, album, year). Offline run: no MusicBrainz, AcoustID has no key, `credits: []` everywhere, by the run conditions. Cover art and a 6-colour palette exist for every song | OK palette in meta/source.json, the manifest and the brief | n/a |
| R13 Mood (Must) | mood (M4) | unit/mood/* | OK: valence/arousal 1 Hz curves, 57 tag curves, one row per section (JR: valence 0.40-0.61, arousal 0.39-0.69, lower in the intro and outro). The tags are audio-only (JR "love" on 19 of 20 sections) | ~ Arousal is useful; valence and tags are weak (documented) | OK (Essentia CC-BY-NC-ND) |
| R14 True meaning (Must) | meaning (M6b) | unit/meaning/*, review/M6b (8 majors open: intent parsing and template) | ~ All songs: `pending`; interview.md is built from the song (NN: 4 voices with seconds, first line and sections, and an announcer question); the YAML template, request.md, input.json and schema.json exist. The round trip with an authored intent on SY gives `status: user` and per-section feel (see R19) | ~ Usable; the intent-parsing majors are open (M6b) | n/a |
| R15 Choreography (Must) | choreo (M2) | unit/choreo, review/M2 | Counts are OK (JR 71 + E000, partial E004/E005 at the 3/4 bar; NN 51; restarts at phrase starts; `count()` gives a count on every in-pulse frame; JS = Python). Hit points (JR 29, NN 12) and holds (JR 36) are OK. The movement curve is OK. **Grooves X: groove ids nearly one per bar (JR 91 ids / 124 bars, 77 used once; 31 bars with the identical kick/snare steps get 14 ids; VS 60/80, MF 57/63, NN 38/88; SY 12/26 vs truth 11) (W3C-1). Syncopation is 0 on 85 % of JR's and 100 % of NN's syncopated bars (W3C-2)** | X groove_id and syncopation cannot drive move repetition or "how off-beat" a passage should move | n/a |
| R16 Characters & lip-sync (Must; visemes Should) | voices, lipsync (M5); singing (M6b) | unit/voices, unit/lipsync, unit/meaning/test_singing_truth, integration/M5 | NN ~: 4 voices (announcer + 3 rappers, = W0); voice changes match the battle form; 4 per-voice mouth curves. **But at every hand-off the outgoing rapper's last word is still open: 7.0 s of overlapping singing rows from different voices, 6.7 s with 2 mouth curves open, and singer_at lists duplicates on 47 % of the sung instants (W3C-5)**. SY OK: 2 voices = truth; the duet opens both mouths correctly. JR ~: 1 voice; every span is flagged `review` because of grade D (cascades from S03); the outro has vocals and an open mouth but no singer (S03). MF X: singer without vocal range (S04). VS ~: the mouth opens for 0.55 s (S07). Visemes: JR 537, NN 741, MF 177 | ~/X `singerAt` is wrong at rap hand-offs (W3C-5) | OK (ECAPA Apache-2.0, Rhubarb MIT) |
| R17 Cues & moments (Must) | cues (M2) | unit/cues | OK: tiers 1-4 (JR 20/2/124/401; NN 14/21/83/268); every cue has a `source`; `lead_in_s` is set on tier 1-2; 20 moments with cue ids; `next(t, {minTier})` matches between JS and Python. JR has only 2 tier-2 cues in 317 s (1 impact, 1 silence; its phrases coincide with sections) | OK | n/a |
| R18 Viewing (Must) | viewer (M6a) | unit/viewer/*, review/M6a (1 major open: undo) | OK: viewer.html on every song (3-16 MB inline), `lanes_without_data: []`, and lanes for sections, meaning, lyrics & singers, beats & counts, hits, bands, loud & quiet, instruments & stems (solo/mute), notes, vocal range and cues. Not re-checked in a browser by me (the file:// open was refused); M6a's browser review covers it | OK | n/a |
| R19 Corrections (Must; the override round trip is a W3 acceptance test) | runner (RUNTIME), viewer POST (M6a), structure/lyrics/voices (M2/M5), meaning re-anchor (M6b) | unit/runner/test_runner_e2e (overrides make stages stale), unit/viewer/test_server (POST), unit/meaning/test_anchor and test_merge (orphans); **no end-to-end test with real stages** | ~ SY copy (section 3): the round trip works. Only the affected stages re-run, the label and moved boundary appear, lyrics and singing follow, and meaning re-anchors 3 claims with no orphans. **But one move shifts other, untouched boundaries (25.0 -> 29.0, the EDM build start) (W3C-6)** | X targeted corrections are not local (W3C-6) | n/a |
| R20 Agent integration (Must) | CLI (RUNTIME), lib (RUNTIME), skill/brief/frames (M6b) | unit/cli, unit/lib (golden + parity), unit/brief, unit/frames | OK: `mvh analyze/status/validate/brief/meaning/frames/view` exist. SKILL.md is 6.3 kB. The brief is 1.3-1.9k tokens (cap 4k). `mvh brief --section S04` on NN gives 1.8 kB, with no lyric text. **The JS and Python loaders agree on real folders** (NN and JR, 6 instants each: count, singerAt, meaningAt, vocalAt, lyricAt, the drums.kick curve, cues.next). `mvh frames` gives a 1356 x 40 CSV with no NaN (section 3) | OK. The manifest is 2.87-2.90k of 3k tokens, with stage summaries trimmed on every song (minor m4) | n/a |

## 2. Output files (PLAN §4 / CONTRACT §1)

| File | Producer (owner) | Test | Present / plausible (MF VS JR NN SY) | Usable | Licence |
|---|---|---|---|---|---|
| manifest.json | finalize (RUNTIME) | unit/runner/test_finalize, contract | all present, valid; 11.5 kB, status flags are honest | OK (read only status + summary; SKILL says so) | n/a |
| brief.md | brief (M6b) | unit/brief | all present; 1332-1877 tokens; every row names its source file. Still shows `key:key:` flags (minor m1: stale after S02 fix) | OK | n/a |
| viewer.html | viewer (M6a) | unit/viewer | all present | OK | n/a |
| run.json | finalize (RUNTIME) | unit/runner | all present; 26 licences, fallbacks, timings | OK | OK (licences live here) |
| overrides.json | user / viewer | unit/viewer/test_server | absent in all (no edits yet: correct) | see R19 | n/a |
| audio/mix.flac, preview.opus | ingest (RUNTIME) | unit/ingest | all present; VS loses 52 ms to the corrupt frame (warning, by SPIKE) | OK | n/a |
| stems/*.flac (+ .wav twins), stems/drums/*.flac | separate_hq (M3a) | unit/separate_hq | all 9 + 6 on every song | OK | ~ (m5) |
| curves/index.json + core/stems/vocal/chroma12.f32, instruments_1hz/mood_1hz.f32 | finalize from stage channels | contract, lib golden | 238 channels on JR; per-voice `vocal.mouth_open.V*` on NN (4) and SY (2) | OK via lib only | n/a |
| curves/spectrum128.u8 | spectral (M1) | unit/spectral | all present; `spectrumAt` returns 128 bytes | OK | n/a |
| events/*.json (49 names) | each stage | contract schemas + validate | all present (edm_roles empty on JR/NN: correct; stops empty on the real songs) | ~ grooves (W3C-1/2), singing (W3C-5) | provenance.models carry licences |
| tables/beats.csv, bars.csv, sections.csv | choreo (M2) | unit/choreo | all present; IDs match events | OK | n/a |
| notes/notes.json, notes.mid, <src>.mid, vocals.mid | notes, vocals (M3b) | unit/notes | all present; no piano.mid when there are no piano notes (null in notes.json) | OK | OK |
| lyrics/lyrics.json, lines.tsv, .lrc/.vtt/.srt/.ass | lyrics (M5) | unit/lyrics | present on MF, JR, NN, SY; VS: empty lines.tsv (instrumental) | ~ (S03, W3C-5) | OK |
| lipsync/visemes.json, phonemes.json (Should) | lipsync (M5) | unit/lipsync | MF JR NN SY; none on VS (correct) | OK as decoration | OK |
| meaning/interview.md, request.md, input.json, schema.json, meaning.json, meaning.md, orphans.json | meaning (M6b) | unit/meaning | all present; intent.md/authored.json absent (user inputs) | OK | n/a |
| meta/*.json (13 topics) | per stage | contract | all present | OK | n/a |
| artwork/cover.jpg | ingest (RUNTIME) | unit/ingest | all present | OK | n/a |
| frames/<fps>fps.csv | frames (M6b), on demand | unit/frames | not made by analyze (correct, D19); see section 3 | see section 3 | n/a |
| lib/mvh.js, mvh_load.py, mvh.glsl, mvh.d.ts; schema/** | finalize (RUNTIME) | unit/lib (golden, parity) | all present; JS = Python on real folders | OK | n/a |

## 3. R19 override round trip (critic experiment on a copy of the synthetic folder)

Setup: `out/_wip/critic-w3/rt-synth` is a copy of the integrator's synthetic folder, run with the current code.
`out/_wip/critic-w3/rt_step.ps1` drives it; logs are in `rt-step1.log` and `rt-step2.log`.

1. **Step 1.** I added the fixture's `meaning/intent.md` and `authored.json` (synthetic, no real lyrics) and ran `mvh analyze <folder>`.
   - The integrator's cache was partly stale because module fixers had changed structure params. Structure and its dependants re-ran.
   - meaning: `status: user`, per-section feel `user`/`draft` per field_sources, orphans [].
2. **Step 2.** I wrote `overrides.json` in the schema form the viewer POSTs:
   `structure.boundaries [{move t 16.998 -> 21.0}]`, `structure.labels [{t 4.0: intro}]`. Then I ran `mvh analyze <folder>` again.
   - **Only the affected stages re-ran.** These were cache misses: structure, lyrics, mood, vocals, choreo, cues, voices, lipsync,
     meaning, brief and viewer. The 13 upstream stages were cache hits. Structure provenance lists both overrides in
     `overrides_applied`.
   - **The change appears in the output.** S01 is now labelled `intro`, and the boundary at 17.0 s is now at 21.0 s.
     Line section_ids follow the new grid (L005 moves from S03 to S02). Word and line times are unchanged.
   - **meaning was re-anchored.** Its notes say "re-anchored 3 per-section claim(s) by time overlap". It is still
     `status: user`, with no orphans; the verse claim now covers S02 and S03.
   - **X: an untouched boundary moved.** The build boundary at 25.0 s (the generator truth, and the start of edm_roles R01)
     became 29.0 s, and the build shrank from 7.5 s to 3.5 s.
     - Cause: a "move" becomes forced/forbidden bars, and the global DP re-segments everything.
     - Reproduced on the structure stage alone with the recorded real upstream of the synthetic song. Moving 9->13
       loses 17.0 and 25.0. Moving 17->21 loses 25.0 and adds 29.0. Moving 34.5->38.5 loses 50.5 and adds 52.5.
     - With the fixture's exact upstream the other boundaries stay (the control test passes).
     - This is **W3C-6**. A user who fixes one boundary must re-check them all, and correct ones can be lost.
3. **`mvh frames --fps 24 --frame0 1`** wrote `frames/24_f1fps.csv`: 1356 rows (= 56.5 s x 24), 40 columns, no NaN/inf.
   - The columns are the curves plus section_id, beat/bar/count/eight_id, line_id, singer, cue tier/id and hit.
   - The file name follows CONTRACT §7. SKILL.md's table says `frames/24fps.csv` for the `--frame0 1` example (minor m7).

Not run: the viewer's own POST (covered by unit/viewer/test_server). The test above starts from the overrides file
the viewer writes.

## 4. Findings

New findings. Each has a failing test under `tests/review/W3/critic/`.

| ID | Sev | Location (owner first) | Claim | Test |
|---|---|---|---|---|
| W3C-1 | major | M2: src/mvh/stages/choreo/__init__.py groove clustering (sim 0.5·cos + 0.5·Jaccard vs the cluster's first bar, threshold 0.85, all four rows incl. hat) | Groove ids nearly one per bar on every real song (JR 91/124 with 31 identical kick/snare bars split over 14 ids; MF 57/63; VS 60/80; NN 38/88) | test_w3c_grooves.py::test_w3c_groove_ids_cluster_bars, ::test_w3c_identical_kick_snare_bars_share_a_groove |
| W3C-2 | major | M2: src/mvh/stages/choreo/__init__.py `syncopation()` | Only an onset followed by a rest on the next 16th step counts, so 8th-note syncopation (the '&' kick tied over the next beat) is always 0: 85 % of JR's and 100 % of NN's syncopated bars score 0 | test_w3c_grooves.py::test_w3c_syncopation_sees_offbeat_kicks, ::test_w3c_syncopation_function_scores_eighth_note_syncopation |
| W3C-3 | major | M2: src/mvh/stages/rhythm/fusion.py `feel_labels` (feel only from tracker tempo ratios) | NN: 76 % of the strong snares are on beat 3 (a half-time backbeat at 138 BPM); feel says normal (0.94). VS is similar | test_w3c_feel.py::test_w3c_half_time_backbeat_is_labelled |
| W3C-4 | major | M3a: src/mvh/stages/drums/core.py drumsep_hits (hihat sub-stem detection on a distorted rock mix) | JR: only 37 % of 496 strong hats are on the 16th grid (chance 25 %; kick and snare about 90 %): the hats are mostly bleed | test_w3c_hats.py::test_w3c_jeremy_hats_are_on_the_grid |
| W3C-5 | major | M5: src/mvh/stages/lyrics/core.py `_finalise_line` (last word sustain up to 1.5 s, not limited by the next line's first word); downstream voices/lipsync/meaning singing and lib singer_at | NN: 46 of 52 line pairs overlap by a median of 1.41 s. Two characters sing at every rapper hand-off: 7.0 s of different-voice row overlap and 6.7 s with two mouth curves open; singer_at duplicates on 47 % of the sung instants | test_w3c_handoffs.py (4 tests) |
| W3C-6 | major | M2: src/mvh/stages/structure/__init__.py overrides + DP (a move = forbid old bar + force new bar, then the global `segment_dp`) | Moving one boundary re-segments the song: on the real-upstream synthetic song 3 of 3 moves lose or add other boundaries (17->21 loses the build start 25.0 and adds 29.0); seen end to end in the rt-synth round trip | test_w3c_override_locality.py::test_w3c_moving_one_boundary_keeps_the_others_real_upstream |

Minor (no test; listed here and in the report):
- **m1 (M6b / RUNTIME).** brief.md status lines still show `key:key:modulation`. The S02 fix re-finalised the manifest, but the brief stage's cached output was not regenerated.
- **m2 (M5).** One-voice songs graded D (JR, MF) flag every singing row `review` (40/40, 14/14). The brief then reports
  `singers:review=40` for a song with one singer, so the warning loses its meaning. This cascades from S03 and S04.
- **m3 (M2).** NN: the V3->V2 rapper change at 67.6 s falls 2.1 s (about one bar) before section S06. The other changes are within 0.7 s.
- **m4 (RUNTIME).** The manifest reaches 2873-2898 of its 3000-token cap on every song, with `manifest:stage_summaries_trimmed` (MF lost the
  viewer summary). One more stage summary will overflow the cap.
- **m5 (M3a).** Five model licences are still marked unclear or unverified in run.json (DrumSep, the two Mel-RoFormers and the htdemucs weights), as in SPIKE's known gaps.
- **m6 (M2).** sections.edm_role is set only on the first section of a drop (MF S10 `drop`, S11-S13 null, although they are labelled drop and lie
  inside R02). Agents should read `events/edm_roles.json` instead. The field is not in the CONTRACT table.
- **m7 (M6b).** SKILL.md §5 says `mvh frames ... [--frame0 1] -> frames/24fps.csv`, but with `--frame0 1` the file is
  `frames/24_f1fps.csv` (CONTRACT §7 naming). RECIPES.md is correct.

Already open, not filed again (with their failing tests): S03 (JR lyrics grade D and outro without lines), S04 (MF singer without
vocal range), S05 (JR section one bar after the band entry), S06 (two kick timelines), S07 (VS mouth opens), S09 (synth labels);
M1 B1-R2/R3-B1 (kick events); M2 F4-r3/F6-r3; M5 R3-1..4; M6b R3-1..5 + R-WORDS R3-1..3; M6a undo; M4 R3-M1; M3a R3-1.
