# Integration seams (W3, integrator and integrator-r2)

Found by running the whole pipeline (`mvh analyze --profile max`, contract 1.0.0-rc.2) on the four real songs and the
synthetic song, into `out/_wip/integrator/<slug>`, and reading the outputs the way a choreography or character agent
would (brief.md, manifest, counts, hit points, sections, lyrics/lines.tsv, singing, meaning). Every seam has an owner,
a severity and, where feasible, a test under `tests/integration/<module>/`. The `test_real_*` tests read the
integrator's run folders and skip when they are absent. RUNTIME items were fixed in W3; module items go to the W3
module fixers. No lyric text appears here.

Run conditions: offline (`MVH_OFFLINE=1`, as the build rules require). MusicBrainz was therefore unavailable
(`identity:offline` on every song: tags only, no credits). LRCLIB answers were replayed from the W0 recordings
(`tests/.cache/real/<slug>/http`) by seeding each song's lyrics HTTP cache (`out/_wip/integrator/seed_lrclib.py`)
before the lyrics stage ran, so the lyrics are what an online run would have fetched.

Tools: `out/_wip/integrator/summarize.py` (per-stage status, sizes, tokens, counts), `seamcheck.py` (cross-module
checks), `truthcmp.py` (synthetic song against the generator truth).

## Summary

| ID | Module | Severity | Status | Seam | Test |
|---|---|---|---|---|---|
| S01 | M3a | blocker | fixed | GPU DrumSep sub-stems not reproducible; determinism gate failed on 11 files | tests/integration/M3a/test_drumsep_device.py |
| S02 | RUNTIME | minor | fixed | manifest flags `key:key:modulation` (double prefix) | tests/integration/RUNTIME/test_manifest_key_flags.py |
| S03 | M5 | major | fixed (W3 fix rounds + r2 re-run) | correct synced lyrics graded D; sung outro has no lines (Jeremy) | tests/integration/M5/test_real_lyrics_grade.py |
| S04 | M3b | major | fixed (W3 fix rounds, D67) | MEGAFAUNA: lyrics, voices and singing have a singer; vocals says none | tests/integration/M3b/test_real_vocal_presence.py |
| S05 | M2 | major | fixed (W3 fix rounds) | section grid one bar after the band entry and the song's only impact (Jeremy) | tests/integration/M2/test_real_section_at_impact.py |
| S06 | M1 | major | open -> W4 (UD2) | two disagreeing kick timelines (MEGAFAUNA: 42 % / 23 % agreement) | tests/integration/M1/test_real_kick_sources_agree.py |
| S07 | M5 | minor | fixed (W3 fix rounds) | instrumental (Versatile) still opens the mouth curve | tests/integration/M5/test_real_instrumental_mouth.py |
| S08 | RUNTIME | minor | fixed | run.json stage seconds include heavy-slot waits; a no-op re-run erased all timings | tests/integration/RUNTIME/test_run_json_timings.py |
| S09 | M2 | minor | fixed (W3 fix rounds) | synthetic intro split in two and labelled verse; bridge labelled verse | tests/integration/M2/test_real_synth_intro_label.py |
| S10 | RUNTIME | major | fixed | the voices stage ignored the viewer's managed intent block and the YAML template | tests/integration/M5/test_voices_intent_seams.py |
| S11 | RUNTIME | major | fixed | `--no-lyrics-to-agents`, `--intent`, `--meaning-draft` missing; re-runs dropped `--lyrics` and `--param` | tests/integration/RUNTIME/test_cli_agent_flags.py |
| S12 | RUNTIME | major | fixed | the runtime unit tests assumed stubs; with real stages they no longer tested the runner | tests/unit/runner/test_runner_e2e.py (MVH_STAGE_STUBS seam) |
| S13 | M2 | major | fixed (D68) | a section boundary edit re-segmented the whole song (W3C-6) | tests/review/W3/critic/test_w3c_override_locality.py, tests/integration/test_override_roundtrip.py |
| S14 | M6a/M2 | blocker | fixed (D68) | the viewer could not load a song after a boundary edit was applied (F-R5-APPLIED-BOUNDARY) | tests/review/M6a/r-platform/test_r5_platform.py |
| S15 | M5 | major | fixed (D69) | mapping some voices in the viewer folded the other singers into them (F-R4-VOICE-FLOOR) | tests/review/M6a/r-platform/test_r4_platform.py |
| S16 | M5 | major | mostly fixed (D70) | rap line tails ran into the next rapper's line: two singers at every hand-off (W3C-5) | tests/review/W3/critic/test_w3c_handoffs.py (3/4 pass) |
| S17 | M2 | major | partly fixed (D71) | groove ids nearly one per bar; syncopation 0 on syncopated bars (W3C-1, W3C-2) | tests/review/W3/critic/test_w3c_grooves.py (6/8 pass) |
| S18 | M2 | major | open -> W4 | half-time backbeat labelled feel 'normal' (W3C-3) | tests/review/W3/critic/test_w3c_feel.py |
| S19 | M3a | major | open -> W4 | Jeremy hi-hat hits scatter off the beat grid (W3C-4) | tests/review/W3/critic/test_w3c_hats.py |
| S20 | RUNTIME | major | fixed (D77) | R19 override round trip had no end-to-end test on real stages | tests/integration/test_override_roundtrip.py |

## Details

### S01 (M3a, blocker, fixed): GPU DrumSep is not bit-reproducible
- **Evidence.** W2 gate: 11 of 180 files differ between two `analyze --force` runs (`stems/drums/*.flac`, then
  `events/drum_hits.json`, `curves/core.f32`, `curves/stems.f32`, manifest, viewer). Reproduced in isolation on a
  40 s drum stem: two ROCm runs in one process or two processes are identical, but with another process holding
  80 % of GPU memory every sub-stem differs (max 4.5e-8, 59-90 % of the samples). MIOpen picks convolution kernels by
  the free workspace. `cudnn.deterministic` and `miopen.immediate` do not help. The CPU path is bit-identical
  (two runs) and 1.45 x real time at 6 threads; the RoFormer stages (no convolutions) stay identical on the GPU.
- **Fix (CONTRACT D47).** `separate_hq.drumsep_device = "cpu"` (default; `"auto"` = GPU). The worker loads DrumSep
  on the CPU and takes no gpu.lock for that step. Cost: about 1.45 x the song length of CPU time (about 8 minutes
  for Jeremy; separate_hq took 982 s in the draft run and 1777 s in the max run, with four other songs queueing for
  the same two heavy slots). It is a cross-module seam (a GPU property cascading into M1/M2/M6 files), fixed in M3a's
  worker code.

### S02 (RUNTIME, minor, fixed): `key:key:` flags in the manifest
- **Evidence.** Every manifest showed `key:key:modulation`, `key:key:parallel_ambiguity`, and so on: finalize prefixed
  M4's already-prefixed flags.
- **Fix (D66).** `finalize.key_flags` prefixes only bare flags. Verified by re-finalising all five folders (cache hits).

### S03 (M5, major): a correct synced text graded D, and an outro without lines (Jeremy)
- **Evidence.** The lyrics source is LRCLIB 22859144 (synced, duration difference 0.0 s). G2 0.78, G3 0.40, G4 0.06,
  G5 0.93 and G7 0.62 pass. G1 (ASR-vs-text agreement) is 0.697 against 0.70, so the grade is **D** ("wrong
  text"). Every recorded LRCLIB candidate ends at 217 s, while `vocal_phrases` continue to 285 s: 79 s of vocal
  phrases have no line (42.7 s after the last line). The ASR hears the outro, which lowers G1. Repeat expansion and
  ASR-only lines (M5-D11) add nothing there (`expanded` 0, `asr_only` 0).
- **Impact.** The brief tells agents the lyrics are unreliable (grade D) although the 40 lines are well placed, and
  the final four chorus sections show a singer (vocal phrases, mouth curve) with no words.
- **Suggested fix.** Judge G1 on the time span the text covers (ASR words in uncovered gaps are not evidence of a
  wrong text). For sung passages after the last line, add ASR-only lines, or expand repeats of supplied lines with a
  `review` flag.

### S04 (M3b with M3a, major): MEGAFAUNA's singer exists for words but not for vocals
- **Evidence.** lyrics: 14 lines from the embedded tags (grade D, ASR no-VAD retry). voices: V1; singing: 14 events;
  meaning: one character who sings; visemes: 177. But `meta/vocal_range.json present=false`,
  `meta/stems.json vocals.present=false` (cross-model conf 0.30), and there are 0 vocal phrases and 0 vocal notes.
  `inst.voice` totals 7 s.
- **Impact.** A character agent gets a singer with lines and visemes, while the vocal range, the vocal phrases
  (breath and phrase timing) and `vocal.pitch01` are empty.
- **Owner.** M3b (CR-M3b-1: presence should combine stem activity, the tagger and lyric line coverage), with M3a's
  `stems.vocals.present` vote.

### S05 (M2 with M1, major): the section grid misses the band entry (Jeremy)
- **Evidence.** Bar 9 starts at 19.47 s. dynamics starts its first `loud` part there, and the song's only impact
  (+5.9 LU, bass +13.4 dB, strength top) is at 19.47 s. structure keeps bars 1-9 as the intro and starts verse#1 at
  bar 10 (21.80 s), 2.34 s later. The brief's moment list has the impact as a separate moment 2.3 s before the
  verse.
- **Owner.** M2 structure: a major impact on a downbeat should be a boundary candidate strong enough to move the
  phrase grid by one bar (today the dynamics evidence is only confirmatory, M2-D-struct-evidence).

### S06 (M1 with M3a, major): two kick timelines that disagree
- **Evidence.** Agreement within 30 ms between `events/hits.kick.json` (spectral) and the kick rows of
  `events/drum_hits.json` (DrumSep). MEGAFAUNA: 42 % of the 335 spectral kicks and 23 % of the 647 drum kicks.
  Versatile: 58 % / 86 %. Jeremy: 82 % / 76 %. Newton: 94 % / 97 %. Synth: 84 % / 89 % (truth: drums kick
  F1 1.00, hits.kick 0.86, the open M1 finding).
- **Impact.** choreo and cues read both, and a video agent cannot tell which kick to cut on.
- **Owner.** M1. W2 change request: fuse hits.kick with the DrumSep kick stem (needs `drums` in spectral's deps:
  acyclic, a contract change), or document the precedence (drum_hits for the kit, hits.kick for the viz envelope).

### S07 (M5, minor): an instrumental opens the mouth
- **Evidence.** Versatile: `lyrics.instrumental = true`, no lines, no voices (voices skipped), yet
  `vocal.mouth_open` exceeds 0.1 on 55 frames (0.55 s) through the `lipsync:ungated_wordless` fallback on a vocal
  chop.
- **Owner.** M5 (an open W2 note). Suppress the ungated fallback when lyrics says instrumental, or make it a param.

### S08 (RUNTIME, minor, fixed): stage timings
- **Evidence.** run.json `seconds` included the heavy-slot wait (Versatile separate_fast 1847 s, harmony on
  MEGAFAUNA 1614 s; both are about 1-minute jobs). A no-op re-run (all cache hits) rewrote run.json with no timings
  at all, so what each stage costs was lost.
- **Fix (D64).** Optional `wait_s` (runner-level slot wait, included in `seconds`) and, on cache hits,
  `computed_seconds` from `.cache/<stage>/latest.json`.

### S09 (M2, minor): structure labels on the synthetic song
- **Evidence.** With the full real upstream: boundaries F 0.92 at 0.5 s and repeat groups give chorus#1 = chorus#2,
  but the 4-bar intro becomes two 2-bar sections labelled `verse` (group A) and the bridge is labelled `verse`. On
  Jeremy, 12 of 20 sections are labelled chorus.

### S10 (RUNTIME, major, fixed): voices did not read the user's whole intent
- **Evidence.** The viewer writes voice-to-character edits into the managed block of `meaning/intent.md` (M6a V7).
  meaning read it, but voices did not: a voice mapping saved in the viewer did not change the voice count or the
  proposals, and the YAML template's `characters: {C1: {voices: [...]}}` lists were ignored (M6b CR-5).
- **Fix (D51).** The voices intent reader layers the viewer block (wins; the highest mapped voice is a floor for k) and
  the template, parsed by meaning's own parser.

### S11 (RUNTIME, major, fixed): agent flags and re-run parameters
- **Evidence.** PLAN §10's `--intent`, `--meaning-draft` and `--no-lyrics-to-agents` did not exist on `mvh analyze`.
  `viewer.inline_lyrics` was never tied to the privacy flag, so lyric text stayed inside viewer.html. A folder re-run
  dropped the earlier `--lyrics` file (the lyrics stage then fell back to LRCLIB or ASR) and replaced all
  `--param` values.
- **Fix (D52).** See CONTRACT D52.

### S12 (RUNTIME, major, fixed): runtime tests and the end of the stubs
- **Evidence.** After W2 the runner's end-to-end unit tests failed (they assumed the walking skeleton: every stage
  `done`, a stage failing on a missing fixture file). They could no longer exercise caching, `--only`, `--from` or
  failure propagation.
- **Fix (D65).** The child runs the fixture copier for stages named in `MVH_STAGE_STUBS` (the cache key records it);
  the runtime tests set it. The stale `test_stub_files_are_stubs` became `test_no_stage_is_still_a_stub`.

## Open W2 findings seen end to end (already routed, not new seams)
- M2 F6-r3: in the real MEGAFAUNA run the drop ends at 176.1 s (edm_roles drop 141.8 s for 34.3 s); SPIKE's loud
  plateau runs to 217 s.
- M1 B1-R2 / R3-B1: synth hits.kick F1 0.86 at 10 ms (drums kick 1.00) in the full real pipeline.
- M5 R3-x: lyrics header and label parsing were not exercised (no user lyric files in these runs).

## Checked and consistent (no seam)

- Sections start on downbeats and tile the song with no gaps, ending at the duration, on all 5 songs. Hit points are
  on beats (one synth hit point is more than 30 ms off a beat). Counts start on downbeats except the E000 lead-in
  (by design, M2-D14) and Jeremy's E004, which starts mid-bar after the 3/4 bar of the free-time intro (bar 6).
- Every lyric line has a voice span and a singing row; `lines.tsv` singers equal `singing.json`; line `section_id`
  values match the time overlap. Moments reference existing cues; meaning and mood sections reference existing
  section ids.
- Lyric lines sit inside vocal phrases (mean overlap 0.93 on Jeremy, 0.90 on Newton, 0.97 on synth).
- Newton: 4 voices (the W0 benchmark found the same: 3 rappers plus the announcer). Synth: 2 voices = truth.
- Synth against truth: beats F1 1.00, downbeats 0.98, drum kick 1.00 / snare 0.99 / hat 0.93 / tom 1.00 /
  cymbal 0.80 at 10 ms, EDM build and drop exact, key A minor, silences 1/1.
- Caching: a re-run of each finished folder is 25/25 cache hits in about 3 s and re-finalises the folder.
- Token caps: manifest 2873-2898 of 3000 (stage summaries trimmed on every song, `manifest:stage_summaries_trimmed`);
  brief 1331-1876 of 4000 (target 2500).

## W3 round 2 (integrator-r2): status after the module fix rounds and the fresh max runs

All five folders in `out/_wip/integrator/<slug>` were re-analysed from scratch with the final W3 code (`--profile max`,
offline, LRCLIB replayed; phase-1 folders kept in `out/_wip/integrator/_phase1/`): analyze 0 / validate 0 on all five, a
no-op re-run is 25/25 cache hits on each. Integration tests (`tests/integration`, 19 tests incl. the round trip): 18 pass, S06 fails.

### Fixed in this round
- **S03 (M5).** Jeremy's G1 is now judged on the span the text covers (M5-D51): grade B (G1 0.76), no longer D. The wordless outro
  is reported (`alignment.vocals_after_last_line_s`) and warned, not filled with invented lines (M5-D52); the integration
  test asserts the flag (the old "< 20 s after the last line" assertion contradicted W0's measurement; fixer M5 and the
  M5 verifier agreed).
- **S04 (M3b).** MEGAFAUNA: vocals present, range E3-E4 (p2 52.1 / p98 67.0, conf 0.44). Lyric lines count as voice
  evidence only with acoustic support (D67); untagged lyric frames no longer inherit a stray `speech` label.
- **S05, S09 (M2).** Jeremy's section starts at the band entry / impact; the synthetic intro is one `intro` section.
- **S07 (M5).** Versatile (instrumental): the mouth stays closed.
- **S13 / W3C-6 (M2, D68).** Boundary edits are applied locally to the automatic segmentation. Phrase remainders follow
  local evidence only (F8-r5).
- **S14 (M6a + M2, D68).** structure stamps one `overrides_applied` entry per key; the viewer collects repeated keys.
- **S15 (M5, D69).** Viewer-mapped voices are a floor; short-line speakers no longer crash voices (M5 R5-2).
- **S16 / W3C-5 (M5, D70).** Lead line tails are capped at the next lead line: Newton's overlapping consecutive lines 46 of 52 -> 0 of 53,
  different-voice singing overlap 7.0 s -> 0, duplicate singer_at entries gone. Remaining: two per-voice mouths open
  2.3 s in total, 2.1 s of it one line where voices detected a BACKING double (V1 under V3, Newton L021, 48.5 s); that
  is a backing-detection question, not a hand-off. The critic test still counts it (W4: confirm the backing is real or
  drop the span).
- **S17 / W3C-1, W3C-2 (M2, D71).** Syncopation uses the Longuet-Higgins/Lee form (truth re-baselined): Jeremy and Newton
  pass. Groove ids: Jeremy and Newton pass (identical kick/snare bars share a groove); MEGAFAUNA 45 ids / 63 bars and
  Versatile 36 / 80 still fail: their DrumSep kick/snare rows are noisy (MEGAFAUNA: hat bleed in the kick stem, S06), so
  this waits for UD2's drum-stem cleanup in W4.
- **S20 (D77).** `tests/integration/test_override_roundtrip.py` (real, slow, 2 tests, 8 min): viewer-style POSTs to the
  edit server on copies of the synthetic and Newton max folders, then `mvh analyze <folder>`.
  - Step 1 (boundary move + pinned cue + V1 -> C1 mapping + section meaning) re-ran exactly structure, lyrics, mood,
    vocals, choreo, cues, voices, lipsync, meaning, brief, viewer (separation, rhythm, harmony, drums, instruments: cache).
  - Step 2 (synthetic, `rhythm.downbeat_phase = 1`) re-ran rhythm and its descendants only; every downbeat moved by one
    beat and the earlier edits survived.
- Module review findings closed here (each has its review test passing): M3a R5-1 (D73), M3b r5-1/r5-2 (D67), M4 R5-M1/
  R5-M2 (D72), M5 R5-1 (D70), M5 R5-2 (D69), M6a F-R5-APPLIED-BOUNDARY (D68), M6a F-R4-VOICE-FLOOR (D69), M2 F8-r5 (D68),
  critic minors m1, m2, m6, m7 (D75, D69, D68).

### Still open (W4)
- **S06 (M1, major).** MEGAFAUNA kick timelines: hits.kick vs DrumSep kick 0.49 / 0.15. Superseded by user decision UD2
  (agent-facing kick = the drum-stem kick, mix kick as a marked fallback, `kick_source` in the manifest, an agreement QA
  flag, precision-first hits.kick). The M1 r-dsp recall tests (R5-M1..M4) are to be rewritten to the fallback's precision
  target in W4 phase 0.
- **S18 / W3C-3 (M2, major).** Newton's half-time groove is labelled `normal`. rhythm cannot see the snare backbeat (its
  deps are ingest, allin1, spectral); a fix needs either drums in rhythm's deps (a DAG change: rhythm would wait for
  separate_hq) or a feel re-vote in choreo with a new field. Left for W4 as a contract decision.
- **S19 / W3C-4 (M3a, major).** Jeremy's hi-hat onsets: 37 % on the 16th grid. Needs a grid / periodicity gate on the
  DrumSep hihat sub-stem or a cross-check with spectral hits.high (algorithmic, M3a).
- **M6b r-words R5-1..R5-4 (major, 23 failing review tests).** Superseded by user decision UD1 (one template grammar plus
  free text; the heuristic markdown parsing these tests probe is being removed). W4 phase 0 rewrites the tests.
- Minors: Newton S06 starts one bar after the rapper change (m3); the manifest sits at 2.87-2.90k of 3k tokens (m4);
  five model licences unclear (m5); Newton lyrics grade C (G2 0.748 against 0.75, after the separation bits changed:
  borderline, not a regression in the text); Newton voice count rests on a near-tie (fixer M5); lyrics r2-m1/r2-m2
  (seam clamp, check order); the TONAL_PEAK / chroma-peak thresholds are unvalidated on real drones.
