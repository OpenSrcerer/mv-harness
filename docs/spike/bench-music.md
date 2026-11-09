# W0 benchmark: music-analysis tools on the four test songs (bench-music)

Date 2026-11-08 · Machine: Windows 11, Ryzen 7 9800X3D, RX 9070 (no CUDA; everything here is CPU) · env-main locks (`uv.lock` `38ef4ea6...`) · offline (`HF_HUB_OFFLINE=1`)

Every tool ran on the **full song** inside one heavy slot at **6 threads** (`OMP/OPENBLAS/MKL/NUMBA_NUM_THREADS=6`, `torch.set_num_threads(6)`, ORT intra 6).
No lyric text was read, printed or stored; all numbers below are tool outputs about audio. Raw outputs: `tests/.cache/real/<slug>/<tool>/` (gitignored),
registry `tests/.cache/real/index.music.json` (song × artefact → path, model, revision, format). Scripts: `docs/research/spike-scripts/bench-music/`
(`bench_music.py` driver, `analyze.py`, `extra.py`, `run_all.sh`; numbers in `analysis.json` and `extra.json`). Each step leaves `_done.json` with wall time, process CPU,
system-wide CPU busy fraction during the step, and the heavy/gpu locks held by other agents at start and end.

Inputs (ffmpeg decode, `-map 0:a:0`, float32, all 44.1 kHz stereo, no resampling needed for the stems):

| Song | slug | duration | peak dBFS | decoder warnings |
|---|---|---|---|---|
| MEGAFAUNA | megafauna | 217.25 s | -0.30 | 0 |
| Versatile | versatile | 227.74 s | 0.00 | 2 (`overread`, `Decoding error: Invalid data found`): the corrupt FLAC frame; ffmpeg still delivers the full 227.74 s, one frame concealed |
| Jeremy (Redux) | jeremy | 316.587 s (equals the LRCLIB 316.587 s entry) | 0.00 | 0 |
| Newton vs Nye | newton-vs-nye | 170.43 s | 0.00 | 0 |

## 1. Timings (wall seconds, 6 threads) and concurrent load

| Tool (step) | megafauna | versatile | jeremy | newton-vs-nye | Notes |
|---|---|---|---|---|---|
| ffmpeg decode + WAV write | 0.4 | 0.7 | 0.7 | 0.3 | |
| demucs-onnx htdemucs + htdemucs_6s (both) | 111.7 | 129.7 | 170.9 | 79.4 | each model alone is 0.21-0.31 x real time (35-81 s) |
| beat_this final0 (inference only) | 3.7 | 4.1 | 6.4 | 3.1 | 50 fps logits |
| all-in-one harmonix-all (8 folds, incl. spectrograms) | 40.3 | 35.4 | 65.0 | 26.8 | on htdemucs stems |
| librosa tempo/tempogram/PLP/onsets/beat_track | 2.5 | 2.7 | 3.5 | 2.0 | |
| spectral proto + dynamics segmentation | 18.5 | 16.7 | 27.1 | 13.4 | single-threaded numpy, includes the proto's own key/chords block (6-14 s) |
| lv-chordia (5-model ensemble) | 5.8 | 10.6 | 10.3 | 5.5 | |
| key: S-KEY global + 30 s windows + HPSS/CQT profiles | 7.2 | 7.6 | 13.0 | 5.7 | |
| basic-pitch on bass, other, 6s-guitar | 4.2 | 4.6 | 8.7 | 3.2 | 0.9-2.6 s per stem |
| SwiftF0 + RMVPE on htdemucs vocals | 6.4 | 3.4 | 5.7 | 2.9 | SwiftF0 0.3-0.8 s, RMVPE 2.2-4.2 s |
| CED-base (7 sources) + CLAP (5 sources) | 67.9 | 67.0 | 111.0 | 55.5 | CED windows 4 s hop 1 s; CLAP windows 10 s hop 5 s |
| Essentia mood (5 ONNX models) | 2.8 | 1.3 | 2.2 | 1.0 | |
| madmom-infer RNN + 2 DBN passes | 41.3 | 37.1 | 76.2 | 36.2 | RNN 14-35 s, the rest is the two DBNs |
| piano transcription | skipped | skipped | skipped | skipped | no piano anywhere (section 5); a mistaken run on a silent stem cost 67.7 s = 0.31 x real time |
| **Sum** | **313** | **296** | **501** | **229** | |

Concurrent load (other agents were running; the machine was never idle):

| Song | Other lock holders seen during the run | System CPU busy during heavy steps (demucs / allin1 / CED+CLAP) |
|---|---|---|
| megafauna | `heavy-1: bench-words` during allin1 onward (not at demucs) | 0.83 / 0.70 / 0.58 |
| versatile | `env-sep` whisper (Vulkan, holding `gpu` and `heavy-0`) throughout | 0.69 / 0.39 / 0.48 |
| newton-vs-nye | `env-sep` `sw_6stem` and whisper (`heavy-0`, `gpu`) throughout | 0.53 / 0.39 / 0.46 |
| jeremy | `env-sep` `sw_6stem` on `heavy-0` | 0.85 / 0.71 / 0.78 |

Consequences: wall times of the same tool differ by up to about 20 percent between songs for load reasons, not only duration. Real-time factors for a full 6-thread slot under about
two concurrent jobs: demucs 4-stem 0.21-0.31, allin1 0.15-0.21, CED+CLAP 0.29-0.35, madmom 0.16-0.24, everything else below 0.1. A whole `max` analysis of these tools is about 5 to 8 minutes per song.

## 2. Tempo and beats: cross-tool agreement

Trackers: beat_this final0 (minimal postprocessor, no DBN), allin1 (harmonix-all), madmom-infer (RNN + DBN, `beats_per_bar=[3,4]` and `[4]`: **identical output on all four songs**), and the librosa `beat_track`/tempogram.
F-measure is mir_eval at ±70 ms. "bpm" is the median inter-beat interval.

| Song | beat_this bpm (p10-p90) | allin1 bpm | madmom bpm | librosa tempo | tempogram peaks (bpm, salience) |
|---|---|---|---|---|---|
| megafauna | **200.0** (103-333) | **105** | **193.5** | 103.4 | 215.3 (.76), 103.4 (.74), 143.6 (.72), 83.4 (.72) |
| versatile | 130.4 (125-136) | 130 | 130.4 | 129.2 | 129.2 (.81), 64.6 (.73), 86.1 (.67) |
| jeremy | 107.1 (103-115) | 105 (107.1 from beats) | 107.1 | 107.7 | 215.3 (.76), 107.7 (.75), 71.8 (.68) |
| newton-vs-nye | 136.4 (68-143) | 140 (139.5 from beats) | 136.4 | 136.0 | 136.0 (.68), 92.3 (.65), 69.8 (.62) |

| Pair (beat F at ±70 ms) | megafauna | versatile | jeremy | newton-vs-nye |
|---|---|---|---|---|
| beat_this vs allin1 | **0.57** | 0.92 | 0.95 | 0.85 |
| beat_this vs madmom | 0.61 | 0.96 | 0.92 | 0.86 |
| allin1 vs madmom | 0.51 | 0.91 | 0.95 | 0.97 |
| allin1 vs librosa beat_track | 0.30 | 0.92 | 0.88 | 0.99 |
| beat_this vs allin1, downbeat F | 0.48 | 0.86 | 0.93 | 0.82 |
| madmom vs beat_this, downbeat F | 0.56 | **0.26** | 0.90 | **0.05** |
| madmom vs allin1, downbeat F | 0.45 | **0.21** | 0.95 | **0.04** |

Findings:
- **MEGAFAUNA is genuinely ambiguous, and the trackers split into two camps.** allin1 and librosa say about 105 (103-105), beat_this and madmom say 193-200 (a 1.9x ratio, not exactly 2x), and the tempogram also has a 143.6 peak (close to the "140" of the plan; about 4:3 of 105) and a 215 peak.
  beat_this local tempo per 30 s window: 273, -, -, 107, 214, 103, 107, 214: it flips between the 105 family and its double *within the song*. allin1 reads 62-64 (half-time) from 30 to 90 s (the breakdown) and 105 from 90 s on.
  madmom reads 187-207 except a 105 window. Cross-F of any tracker with another tracker's x2 version is only 0.52-0.61, so doubling does not reconcile them: the beat grids genuinely differ in phase/placement (breakbeat-style
  syncopated drums). Conclusion: do **not** hard-select one tempo for this class of material; carry the candidate set {~105, ~143, ~200-215}, a per-segment feel label, and let the rhythm stage arbitrate against the kick-envelope (the viz-port kick gives 467 kick events, vs 382 beat_this beats and 277 allin1 beats).
- **Non-ambiguous songs agree well:** beat F between the three neural trackers 0.85-0.97 (median 0.92) on versatile, jeremy and newton-vs-nye. Raw tempo agrees within 2 percent (130.4/130/129.2; 105-107.7; 136-140; allin1's integer `bpm` field is rounded and sometimes off by 2 from its own beats: 105 vs 107.1 and 140 vs 139.5, so use the beat-derived value).
- **beat_this has octave flips on sparse/half-time passages.** newton-vs-nye: local 69.8 bpm in 3 of 6 windows (the intro/announcer and breaks), against 136-140 elsewhere. beat_this vs allin1 half-tempo F is 0.80 there (x2 gives only 0.54), so it really tracks half-time for those stretches.
  Beats-per-bar histograms (from the bar lines each tracker emits): allin1 and madmom are always 4 (jeremy 133 of 133 bars; no 3/4 detected in any song); beat_this emits 1-3 and 5-8 beat "bars" at section edges (megafauna 77 of 121 bars not 4, jeremy 26 of 151).
- **Downbeat phase is the weak point.** On versatile and newton-vs-nye madmom's downbeats sit exactly one beat from allin1/beat_this (shift of -1 or +3 beats gives downbeat F 0.50/0.94 against 0.26/0.04 unshifted; for newton-vs-nye allin1 vs madmom at shift -1 is 0.94). beat_this and allin1 agree with each other (0.86, 0.82), but two out of three trackers disagreeing with the third by one beat means bar phase is not trustworthy without a fusion vote. On jeremy all three agree (0.90-0.95).
- librosa `beat_track` is a usable fourth voter on steady songs (0.84-0.99 against the others) and useless on MEGAFAUNA (0.30).

## 3. Key and harmony

Top-1 global key by method (S-KEY = ONNX, KS = Krumhansl-Schmuckler on HPSS CQT chroma, TP = Temperley profiles, chords = diatonic-chord weighting of the lv-chordia durations):

| Song | S-KEY | KS | TP | lv-chordia diatonic top | S-KEY 30 s windows agreeing with its global |
|---|---|---|---|---|---|
| megafauna | A minor (p=.068) | D minor | D minor | D minor / F major tie (.84) | 0.50 (A minor 7, D minor 4 of 14) |
| versatile | A minor (.093) | A minor | F major | D minor / A minor / F major tie (.85) | 1.00 (15 of 15) |
| jeremy | A minor (.092) | A minor (A major second at .67) | F major | A minor / C major (.61) | 0.76 (16 of 21; D major 5) |
| newton-vs-nye | A minor (.094) | A minor | F major | A minor / C major (.98) | 1.00 (11 of 11) |

- S-KEY and KS agree exactly on three of four songs (A minor). On MEGAFAUNA they are a fifth apart (A minor vs D minor), and the chord-based evidence is symmetric (D minor 75 s, C major 30 s, A minor 28 s): the song sits in the A minor/D minor/F major pitch set. Treat as ambiguous, report both.
- Temperley prefers F major on three songs where S-KEY/KS pick A minor (F major shares its pitch set with D minor and sits next to A minor in the same diatonic cluster, so this is a mode/tonic-centre confusion inside one tonal area, not noise). A key ensemble must treat {A minor, F major, C major} as one tonal centre and report the mode with low confidence.
- **S-KEY's probability is not a usable confidence**: the winning class has p between .068 and .094 on every song (24-way softmax is nearly flat for full-song inputs). Use window agreement (0.5-1.0 here) and cross-method agreement as the confidence. *(W3 amendment: the flatness is an export artefact, softmax applied twice; `harmony` inverts it (`keys.recover_probs`, see the M4 decisions merged into CONTRACT.md) and the recovered p is informative. Windows with recovered p_max < 0.2 do not vote.)*
- lv-chordia: 44-70 segments per song (6-13 distinct chords from the `submission` vocabulary, major/minor only), 'N' (no chord) covers 4.5 percent (jeremy) to 22 percent (newton-vs-nye, i.e. the rap breaks). Jeremy alternates A minor and A major (133.9 s and 110.1 s), which is a modal/blues-flavoured grunge key, not a tracking error. Newton-vs-nye reduces to Am/F/G (66.6/55.1/8.7 s), plausible for a looped rap-battle beat.

## 4. Structure, loudness, dynamics (drops)

allin1 sections (labels are the Harmonix vocabulary):
- **jeremy**: 17 segments: intro 0.5-21.8, verse 21.8-40.1, chorus 40.1-76.4, verse 76.4-113, chorus 113-149.2, bridge 149.2-176.1, verse 176.1-203.1, chorus 203.1-288.1, outro 288.1-316.6. A conventional verse/chorus map; the outro (no lyrics after the last synced line near 217 s per the plan) is not separated until 288 s, so structure alone cannot be used for the "no words in the instrumental tail" check.
- **newton-vs-nye**: 13 segments in 8-bar blocks (13.9 s at 139.5 bpm): intro, verse x3, chorus, verse, chorus, verse, chorus, outro x2. Plausible for a rap battle.
- **versatile**: 15 segments (intro 0-51.7, chorus 51.7-114.5, break 114.5-144, inst 144-158.8, chorus 158.8-191.5, outro 191.5-224). **megafauna**: 10 segments, nearly all "inst"/"intro", one "chorus" at 169-185: the Harmonix vocabulary has no build/drop and gives no information on instrumental electronic music, which confirms the plan's decision to define EDM roles in `structure` only.

Loudness and dynamics (prototype port; `lra_lu` and integrated LUFS by pyloudnorm):

| Song | integrated LUFS | LRA LU | sample peak dBFS | viz-port kick events (offline ref) |
|---|---|---|---|---|
| megafauna | -10.81 | 17.89 | -0.3 | 467 (464) |
| versatile | -6.08 | 14.23 | 0.0 | 209 (208) |
| jeremy | -7.02 | 6.49 | 0.0 | 680 (617) |
| newton-vs-nye | -10.08 | 3.53 | 0.0 | 203 (199) |

Observed drop/build timings from the prototype segmentation (seg.py, Foote novelty on 10 Hz features; tags are heuristic, to be superseded by the structure stage):
- **megafauna**: soft opening 0-25.9 s, breakdown 25.9-58.6 s (-12.9 LU), quiet 58.6-74.7, build-up 74.7-114.1 and 114.1-146.3, **drop tags at 114.1 and 146.3 s**, loud plateau 146-217 s (+2 to +3 LU). The dynamic range (LRA 17.9 LU) is wide, so the drop is the single big event.
- **versatile**: build-up 0-37.5 s (the first 8 s at -28.8 LU), loud from 37.5 s, **drops at 47.5 s and 171.9 s**, mid-song soft section 108.8-138.9 (build-up tag at 123.1), breakdown 204.5-227.7 s (-22 LU).
- **jeremy**: the segmentation returns only 3 segments (0-8.7 intro soft, 8.7-277.7 "loud + drop", 277.7-316.5 soft). A loud, heavily limited master (LRA 6.5) flattens LUFS; the Foote kernel with fixed thresholds finds almost nothing, while allin1 finds 17 sections. The dynamics detector needs per-song adaptive prominence and the PLAN's bass/kick/slope features, not LUFS alone.
- **newton-vs-nye**: loud 18.9-142.9 s with no internal structure (LRA 3.5 LU), build-up tag 5.4-18.9, breakdown 154.9-170.4.

## 5. Instruments, vocals, piano, mood

**Piano presence.** The 6-stem `piano` stem is silent in all songs (-73.5 to -79.9 dBFS mean; active fraction 0.0-0.088), and CED "Piano" probability is 0.000-0.003 on the mixes. The gate (stem active >= 10 percent of frames, or CED mix piano mean >= .05, or p95 >= .25) skipped piano transcription on all four songs. A first, mistaken run on MEGAFAUNA before the CED fix (below) transcribed the silent stem and produced 378 spurious notes in 67.7 s: **the gate is necessary, and the stem-activity test alone (with 8.8 percent active) was close to the threshold, so keep the CED check in the rule.**

**CED-base**. Mix top tags: megafauna Music .83, Electronic music .15, Ambient .15, Drum and bass .09; versatile Electronic music .19, Dubstep .10; jeremy Grunge .37, Rock music .18, Punk rock .13; newton-vs-nye Rapping .28, Hip hop music .28. On the htdemucs vocals: jeremy Male singing .27 / Speech .18 / Singing .05; newton-vs-nye Speech .55 / Rapping .06 / Male speech .06 (the style classifier separates singing from rap/speech). jeremy bass stem: Bass guitar .75 / Guitar .58. Correct genre and instrument tags on all four.

**CLAP (30-prompt synth vocabulary)**. Cosine range is narrow (about .2-.45), the top prompt is often wrong for vocals (jeremy vocals: "vocal chops" .28, "a choir singing" .25; newton-vs-nye mix: "lead synthesizer" .45, "brass" .34), though jeremy mix is correctly "grunge rock" (.38). CLAP is usable for relative change over time and for user-supplied terms, not for absolute labels.

**Vocal f0 on htdemucs vocals** (SwiftF0 gated at conf > .9 and above the stem's 30th loudness percentile; RMVPE gated at conf >= .3):

| Song | SwiftF0 gated voiced time | SwiftF0 p2/p50/p98 | RMVPE voiced fraction | RMVPE p2/p98 (MIDI) | agree within 1 semitone / octave-off |
|---|---|---|---|---|---|
| jeremy | 60.7 s (19.2 %) | G3 / MIDI 61.2 / G#4 (55.3-68.0) | 60 % | 53.6-73.8 | 0.95 / 0.03 (3795 frames) |
| newton-vs-nye | 8.6 s (5.1 %) | C3 / 65.7 / A#4 (48.1-69.8) | 41 % | 45.0-69.1 | 0.998 / 0.00 (538) |
| megafauna | 9.8 s (4.5 %) | C4 / 64.0 / A4 | 15 % | 50.5-76.9 | 0.997 / 0.002 (610) |
| versatile | 1.1 s (0.5 %) | A3-F6 (noise) | 3 % | 55.7-76.2 | 0.62 / 0.30 (69) |

Jeremy: sustained range G3-G#4 (MIDI 55-68, about an octave plus a semitone) is plausible for a baritone; RMVPE's higher p98 (MIDI 73.8) includes backing-vocal/harmony frames and bleed. Versatile has effectively no lead vocal (1.1 s), consistent with the "near-instrumental" description (the voiced frames are vocal-chop bleed, and they show the octave disagreement); MEGAFAUNA has 9.8 s of voiced frames, almost at the plan's 8 s `present` threshold.
The rap battle fails the conservative SwiftF0 gate (8.6 s of 170 s is "voiced"): rap/speech has unstable pitch, so f0-based `present` and range logic must not run on rap; RMVPE finds 41 percent.

**Notes (basic-pitch)** (notes per stem, 5th-95th percentile MIDI): jeremy bass 1194 (33-56), other 2238 (45-67); megafauna bass 241 (26-45), other 1122 (38-81); versatile bass 310 (24-40); newton-vs-nye bass 502 (29-45). Quality was not scored (no ground truth), but the ranges are plausible (bass E1-A3, MIDI 24-56).

**Mood (Essentia, 1-9 scale, [valence, arousal])**: emoMusic megafauna [3.98, 4.82], versatile [4.60, 5.71], jeremy [5.13, 6.06], newton-vs-nye [4.40, 6.44]; DEAM valence 5.4-5.9, arousal 4.3-5.9. Top mood tags: megafauna dark/space, versatile energetic/dark, jeremy love/melodic/energetic/sad, newton-vs-nye energetic .26. Arousal ordering is sensible (rap and grunge high, ambient-ish MEGAFAUNA lowest); the two heads disagree on valence (emoMusic 3.98 vs DEAM 5.55 on MEGAFAUNA) so valence stays low confidence, as in the plan.

## 6. Go / no-go per tool

| Tool | Verdict | Evidence and fallback |
|---|---|---|
| ffmpeg decode | **go** | Corrupt Versatile FLAC decodes fully with 2 warnings; all four songs 44.1 kHz stereo |
| demucs-onnx htdemucs (fp16 weights, array route) | **go** | 0.21-0.31 x RT at 6 threads; stems vs mix relative RMS error 2.1-3.6 percent, so the "stems sum to the mix" invariant belongs to `separate_hq` only |
| demucs-onnx htdemucs_6s | **go with caveat** | Same speed; sum error 6.4-9.9 percent; its `piano` stem was silent on all songs (cannot say anything on quality) and its `guitar` stem was used only as a basic-pitch source |
| beat_this final0 | **go with caveat** | 3-6 s per song; best single tracker on steady songs but octave flips and 1-3/5-8 "bars"; logits are kept for fusion |
| all-in-one harmonix-all | **go** | Beats consistent with the others (F .85-.95), 4/4 bar grid, structure good on vocal songs; Harmonix labels uninformative on electronic songs, so EDM roles stay in `structure` |
| librosa tempo/PLP/tempogram | **go** | Global tempo within 2 percent on steady songs; tempogram candidate list contains the alternatives that the trackers split on (MEGAFAUNA 103/143.6/215) |
| spectral prototype (bands, kick, LUFS) | **go** | 13-27 s per song; kick counts port vs offline reference within 1 percent (jeremy 10 percent) |
| dynamics segmentation prototype (seg.py) | **go with caveat** | Fine on EDM (drops found), fails on limited rock master (3 segments on jeremy); needs adaptive thresholds and bass/kick features |
| lv-chordia | **go** | 5-10 s; vocabulary major/minor only; 'N' up to 22 percent on rap breaks |
| S-KEY ONNX | **go with caveat** | Agrees with KS on 3 of 4; probability flat (max .09), use window and cross-method agreement. Fallback profile ensemble (KS+Temperley) works but Temperley disagrees on 3 of 4 | *(W3 amendment: the flatness is an export artefact, softmax applied twice; `harmony` inverts it (`keys.recover_probs`, see the M4 decisions merged into CONTRACT.md) and the recovered p is informative. Windows with recovered p_max < 0.2 do not vote.)*
| basic-pitch (ONNX) | **go** | 0.9-2.6 s per stem; note accuracy unmeasured here |
| SwiftF0 | **go** | 0.3-0.8 s; gating needed; unusable as presence detector on rap |
| RMVPE ONNX | **go** | 2.2-4.2 s; as arbiter: where both voiced, agrees within 1 semitone 95-99.8 percent (octave-off 3 percent on jeremy, 30 percent on the vocal-less versatile); outputs a pitch for every frame, so gate on `conf` (0.3 used here) |
| CED-base ONNX | **go** | Correct tags on all songs; **output is already a probability, not a logit** (see change request 1) |
| CLAP ONNX (small vocabulary) | **go with caveat** | Low-contrast, wrong top prompt on vocals; use for relative curves and user terms only |
| Essentia ONNX mood | **go with caveat** | Valence low confidence; arousal sensible |
| madmom-infer DBN | **go with caveat** | Beats good (F .86-.96 vs beat_this) but downbeat phase one beat off on 2 of 4 songs; `[3,4]` vs `[4]` identical here; 0.21-0.24 x RT; fallback only |
| piano_transcription_inference | **go with caveat** | Smoke-tested only; not exercised on a real piano (no piano in any test song); 0.31 x RT; must be gated |

## 7. Re-baselined thresholds and design consequences (supported by the evidence above)

| Item | Initial | Recommended | Why |
|---|---|---|---|
| Cross-tracker beat F (±70 ms) used as the confidence signal | not set | high >= 0.85; medium 0.7-0.85; below 0.7 means tempo/phase ambiguity: carry alternatives, do not pick | steady songs 0.85-0.97, MEGAFAUNA 0.30-0.61 |
| Tempo agreement | 0.5 BPM on clicks | keep 0.5 BPM for synthetic clicks; for real songs use "within 2 percent" for agreement, because allin1's integer bpm and the 50 fps quantisation of beat_this already differ by 1-2 percent | 105 vs 107.1, 140 vs 139.5 |
| Downbeat/bar phase | one tracker | require 2-of-3 vote (beat_this, allin1, madmom) and flag a one-beat disagreement | versatile and newton-vs-nye madmom off by one beat |
| Beats-per-bar | any | accept only 3 or 4 (and flag bars of other lengths as irregular) | beat_this emits 1-8 beat bars at section edges |
| Vocal `present` rule (>= 8 voiced seconds from SwiftF0 gated) | 8 s | keep for singing; for speech/rap use RMVPE voiced time (>= 15 s) or the CED style label; skip f0 range statistics when CED says Speech/Rapping | newton-vs-nye is 8.6 s by SwiftF0 yet 41 percent by RMVPE |
| Key confidence | ensemble probability | window agreement >= 0.75 and S-KEY = KS, otherwise report two candidates; never use the S-KEY softmax value | max p .068-.094 |
| Piano gate | stem activity | stem activity >= 10 percent of frames or CED piano mean >= .05 or p95 >= .25 | silent stems produced 378 spurious notes in 67.7 s |
| `separate_fast` stem-sum invariant | -30 dB (plan §3.1 for HQ) | do not assert on `separate_fast`: relative RMS error 2.1-3.6 percent (htdemucs), 6.4-9.9 percent (6s) | measured |
| Real-time budget (6 threads, shared box) | none | document: `max` music stages 1.3-1.6 x duration in total; with the separators, a 5 min song takes about 8-12 min | section 1 |

Not measurable here (no ground truth): kick F1, drum classification, note F1, chord accuracy, tempo error against truth. Cross-tool agreement is reported, not asserted, as the plan specifies.

## 8. Change requests (not applied, other agents own the files)

1. **docs/spike/main.md, row 18/recipes (CED-base)**: the ONNX output `logits [B, 527]` is already a **probability** (values 0..1, e.g. max .69 on a music window; applying `sigmoid` squashes everything to .5-.73, which made "Piano" read .50 everywhere). Do not apply sigmoid.
2. **docs/spike/main.md, heavy-lock note**: `heavy_lock.py run -- <command>` fails with `WinError 2` for a relative or backslash-less path; pass an absolute interpreter path with forward slashes (`C:/.../.venv/Scripts/python.exe`), because `python` resolves to the system interpreter under `run.ps1`.
3. **Stage design (rhythm)**: carry the tempo-candidate set and a per-segment feel for ambiguous material, and fuse downbeats by vote (section 7); the `rhythm` spec already says tempo arbitration, and this data is the evidence that it is required, not optional.
4. **dynamics stage**: replace the fixed-threshold Foote segmentation of the prototype by adaptive prominence plus bass/kick/slope features before relying on it for limited masters.
5. No env, lock or model changes needed. (`basic_pitch`, `swift_f0` models are bundled in their wheels, hence `null` revisions in the index.)

## 9. Where the data is

- `tests/.cache/real/index.music.json`: song × artefact → path, model, revision, format. Per-step `_done.json` holds timings and load.
- Formats are documented in each tool's JSON (`format` key). Highlights: beat_this logits `.npy` float32 [T] at 50 fps; allin1 `activations.npz` (beat, downbeat, segment [T]; label [10,T], 100 fps) and `embeddings.npy` [4,T,24,8]; spectral `curves.f32` float32 [frames, 34] at 100 Hz (columns in `curve_columns.json`) and `spectrum128.u8`;
  CED `ced_<src>.npz` probs float16 [W,527]; CLAP `clap_<src>.npz` embeds [W,512] and sims [W,30]; mood `mood.npz`; madmom `rnn_activations.npy` [T,2] at 100 fps; pitch `swiftf0.npz`/`rmvpe.npz`; notes JSON `[start,end,midi,amp]` plus MIDI.
- Stems: `demucs/htdemucs/{drums,bass,other,vocals}.wav` and `demucs/htdemucs_6s/{...,guitar,piano}.wav` (float32 WAV, 44.1 kHz stereo).
- Re-run one song: `docs/research/spike-scripts/bench-music/run_all.sh <slug>[:force,steps]` (resumable; takes a heavy slot per song).
