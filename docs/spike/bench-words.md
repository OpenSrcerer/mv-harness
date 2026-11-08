# W0 spike: words, voices, lip sync (bench-words)

Date 2026-11-08 · Machine: Ryzen 7 9800X3D (6 threads inside a heavy slot), RX 9070 not used (all CPU) · env from `docs/spike/main.md`.
Songs: `jeremy` (Pearl Jam, 316.59 s) and `newton-vs-nye` (rap battle, 170.43 s) for tasks 3 to 6; identity and LRCLIB for all four.
No lyric text appears in this file; every raw response and every word-level artefact is in gitignored `tests/.cache/real/<slug>/`.
Scripts: `docs/research/spike-scripts/bench-words/bw_*.py` (run as `powershell -NoProfile -File scripts\run.ps1 python <abs path>`; the model scripts take the heavy slot themselves).

Stem used: **env-sep `lead_vocals.wav`** (ROCm BS-Roformer/Mel-Band + karaoke split, stereo float32 44.1 kHz, mixed to mono and soxr-resampled to 16 kHz). No own demucs stem was produced.
Checked first: on both songs `lead_vocals` carries the same level as `vocals` for the whole sung range (the rap battle keeps all three rappers; the karaoke split removed only the post-lyrics tail), so it is safe to feed alignment and voices.

## 1. Identity (task 1)

ffprobe tags are complete for all four. Chromaprint through `ffmpeg -map 0:a:0 -vn -t 120 -f chromaprint -fp_format base64 -` works on all four (rc 0, 3.0-3.5 k characters,
saved under `identity/`). **AcoustID was skipped: no `ACOUSTID_API_KEY` exists on this machine.** MusicBrainz WS/2, 1.1 s apart, User-Agent `mv-harness/0.0-dev (...)`.

| song | tags | MusicBrainz recording search | verdict by the PLAN rule (score >= 90, |dur| <= 3 s) |
|---|---|---|---|
| megafauna | title, artist, album, track, 428-char embedded lyrics tag (`unsyncedlyrics`) | 1 hit, score 100, length diff 0.00 s | accepted |
| versatile | complete incl. ISRC | 0 hits; ISRC lookup 404 | none (not in MusicBrainz) |
| jeremy | complete (title carries "(Redux Version)") | the full title gives 0 hits; with the parenthesis removed 624 hits, top 8 are other live and album versions of the song (length diffs 3.9 to 34 s) | **none accepted**: the Redux recording is not in the top 8. One refinement query (release "Ten Redux") hit a MusicBrainz 503 twice and was not retried further. Needs `limit` paging or a release filter, see change requests |
| newton-vs-nye | complete | 6 hits; one at 170.0 s (diff -0.43 s), others 154 to 167 s | accepted (the 170.0 s recording) |

## 2. LRCLIB cascade (task 2), PLAN 5 exactly: get with album, get without album, always search (two queries), rank by smallest |delta dur|

Sequential requests 0.4 s apart, identifying User-Agent, no 429 or Retry-After seen (all calls 0.15 to 0.26 s). Raw responses are in `http/` per song. Candidate gate: title token-set >= 90 (parentheses stripped) and artist >= 85.

| song | get+album | get no album | search results pooled | chosen | note |
|---|---|---|---|---|---|
| jeremy | 200 (id 1603511, **+2.41 s**, near miss) | 200 (same) | 3 | **22859144**, delta 0.000 s, synced 40 non-empty lines | verified: the id from the brief. Runner-up 14959651 at +0.047 s also synced; the `/get` hit is 2.4 s off, exactly the failure the PLAN warns about |
| newton-vs-nye | 200 (id 3921433, -0.435 s, synced 51 lines) | 200 (same) | 14 | smallest delta is **25570391** (+0.069 s) but it has **plain lyrics only** | **rule gap**: all of these are inside 2 s, and only 3921433 is synced. Alignment used 3921433. Proposed tie rule below |
| megafauna | 404 | 404 | 0 | none | the embedded tag (cascade step 2) is the only text |
| versatile | 404 | 404 | 2 | none | both search hits are false friends (artist similarity 38 and 20, delta -96.8 s and +295 s): the artist gate rejects them |

Proposed ranking tweak (change request 1): after the text gate, take all candidates with |delta| <= 2 s, then prefer `has_synced`, then the smallest |delta|. With that rule jeremy is still 22859144 (it is synced and the best delta) and newton picks 3921433.
Chosen text sizes: jeremy 40 lines / 194 words (11 duplicate lines, one line repeated 8 times); newton 51 lines / 470 words (no duplicates). LRCLIB speaker labels: none in either.

## 3. faster-whisper large-v3 int8 CPU on `lead_vocals` (task 3)

`WhisperModel(.../large-v3, cpu, int8, cpu_threads=6)`, `vad_filter=True`, `word_timestamps=True`, `condition_on_previous_text=False`, `beam_size=5`, `language="en"`; array input (never a path).
Hallucination filter (`bw_whisper.py::filter_segments`): non-lyric tags, repeated trigram >= 3 times, unique-word ratio < 0.3, compression ratio > 2.4 with low logprob, no-speech > 0.8 with low logprob, mostly zero-duration words. **It dropped nothing on either song** (VAD already removed the junk), so it is untested against a real hallucination here.

| song | model load | transcribe | RTF | words (kept) | mean word prob | words with p < 0.5 | `lyrics_match_score` (LCS F1 vs LRCLIB) | precision / recall |
|---|---|---|---|---|---|---|---|---|
| jeremy | 3.2 s | 33.1 s | **0.104** | 155 | 0.878 | 7.1 % | **0.762** | 0.858 / 0.686 |
| newton-vs-nye | 3.1 s | 54.8 s | **0.321** | 471 | 0.903 | 6.2 % | **0.835** | 0.834 / 0.836 |

Notes:
* Jeremy recall is low because the voice goes through sustained and distorted lines; precision is fine. The ASR ends at 216.9 s and so does LRCLIB (212.3 s), but the vocal stem is loud until about 300 s. A no-VAD run over 205 to 316 s returned only 22 low-confidence words (no-speech prob 0.65 to 0.87) and a loose-VAD run 8 words ending at 216 s: **the 217 to 300 s outro is wordless singing**, not missing lyrics.
* Dense rap costs 3x the RTF of the sung song (471 words in 170 s, beam 5), still well under real time.
* `lyrics_match_score` is the PLAN confidence input: both songs clear 0.7.

## 4. MMS_FA forced alignment (task 4)

Implementation (`bw_align.py`), all on the **torchaudio `forced_align` op** (`_IS_ALIGN_AVAILABLE` True; no deprecation warning on torch 2.15 / torchaudio 2.11.1), the vendored Viterbi was not needed:
* emissions for the whole song in 30 s windows with 2 s of context each side (320-sample-aligned so frames stitch exactly), per-window zero-mean unit-variance, log-softmax; 20 ms frames;
* text: uroman, then num2words for digits, then only MMS dictionary characters (a-z and apostrophe); 0 words lost on both songs;
* line-group windows: consecutive LRCLIB lines grouped up to 30 s (split on a gap > 12 s), window = [first line start - 2 s, last line end + 2 s]; one CTC pass per group (10 groups for jeremy, 5 for newton);
* line-window constraint: a line whose start lands > 2.5 s from LRCLIB (+ offset) is re-aligned alone in [its start - 2.5 s, next start + 2.5 s] and kept only if its mean token score improves (jeremy: 3 re-aligned, 3 accepted; newton: 0);
* global offset: median of (CTC line start - LRCLIB line start); applied as a second pass when |median| > 0.15 s.

Cost: model load 1.1 s; emissions 29.2 s for jeremy (RTF **0.092**) and 16.3 s for newton (RTF 0.095); Viterbi **0.06 to 0.07 s** for the whole song. The CPU log-prob cache (`*_logp.npy`, fp16) makes every re-alignment free. Peak tokens per frame: 0.095 (jeremy), **0.361 (newton, the densest window)**, so even the rap never approaches the CTC limit of one token per frame; 0 group failures.

| metric (lead_vocals) | jeremy | newton-vs-nye |
|---|---|---|
| words / aligned | 194 / 194 | 470 / 470 |
| **mean token score** (exp of mean log prob per token span) | **0.399** | **0.443** |
| mean word score | 0.388 | 0.440 |
| words with score >= 0.5 / >= 0.3 / >= 0.1 | 34.5 / 57.2 / 79.9 % | 42.1 / 56.2 / 77.7 % |
| words with score < 0.01 | 3.1 % | 8.3 % |
| **global offset** (median CTC - LRCLIB line start) | **-0.11 s** (below the 0.15 s trigger, not applied) | **-1.33 s** (applied) |
| median abs line-start delta, raw / after removing the offset | 0.19 s / 0.245 s | 1.33 s / 0.21 s |
| p90 abs line-start delta after offset | 1.34 s | 0.90 s |
| lines within 0.5 s / 1 s / 2 s of LRCLIB + offset | 85.0 / 87.5 / 97.5 % | 82.4 / 92.2 / 100 % |
| vs faster-whisper word starts (LCS-matched words): median delta, within 250 ms | +0.35 s bias, 37.6 % raw, **58.6 % bias-removed** (133 words) | +0.11 s, **88.5 % raw**, 94.9 % bias-removed (393 words) |
| fraction of word spans < 40 ms | 3.6 % | 12.6 % |

Reading the numbers:
* Token scores of 0.40 to 0.44 look low but are normal for CTC on **sung or fast-rap audio** (the same model gave 0.9+ on clean TTS in the smoke test). The per-line mean score is **not** a usable bad-line detector: AUC of "low line score" for "line start > 1 s from LRCLIB" is 0.59 (jeremy) and 0.47 (newton). Do not gate on token score alone.
* **The LRCLIB offset on newton is real:** -1.33 s from MMS, and faster-whisper (independent) agrees to 0.11 s. The synced lines belong to a version with about 1.3 s more lead-in. Offset detection is therefore Must (without it, raw line starts are 1.3 s late for the whole song).
* Acoustic cross-check without ground truth (`bw_quality.py`): word-start hit rate within 60 ms of a vocal-stem energy-flux onset, divided by the chance rate (same starts shifted by 0.35 to 0.5 s). Lift (higher is better): MMS words **1.34 / 1.25** (jeremy / newton), faster-whisper 1.17 / 1.03, stable-ts 1.13 / 1.09, LRCLIB line starts 1.26 / 1.10, **MMS line starts 1.55 / 1.24**. Lift for MMS words with score >= 0.5 is 1.32 / 1.30, with score < 0.1 it is 1.11 / 1.18, so low score words are the ones that float. The onset detector is dense (6 onsets/s on jeremy), so chance is high (0.69); the lift is modest but consistently ranks MMS first. Median signed lag to the nearest onset is -0.01 s for all sources.
* LRCLIB has no ground truth either; the only absolute reference is that line starts agree among three independent sources after the offset.

### 4a. stable-ts `align` fallback (faster-whisper large-v3 int8, whole text, `original_split=True`, no VAD)

| | jeremy | newton-vs-nye |
|---|---|---|
| time (RTF) | 96.0 s (**0.303**) | 33.6 s (**0.197**) |
| median line-start delta vs LRCLIB, after offset removal | -0.505 s, abs 0.43 s | -1.35 s, abs **0.16 s** |
| p90 abs line-start delta after offset | 0.89 s | 0.71 s |
| mean word probability / share >= 0.5 | 0.75 / 77.8 % | 0.757 / 81.2 % |
| agreement with MMS word starts (within 250 ms) | 35.6 % (median -0.36 s) | not matched (468 vs 470 words: its tokeniser differs) |
| onset lift | 1.13 | 1.09 |

Verdict: stable-ts agrees with MMS on **line level** (newton line starts 0.16 s median abs after offset, even a touch tighter than MMS' 0.21 s) but its **word starts are weaker** (lower onset lift, jeremy words 0.36 s earlier than MMS) and it is 2 to 3x slower than MMS (3x on sung audio) because it needs the full transformer. It also reports 4 to 6 % of words < 40 ms. It stays the fallback for the coverage < 0.6 case, as planned, and can also provide a second opinion for lines.

### 4b. Repeated-section expansion (synthetic, `bw_expand.py`)

Neither song needed expansion (jeremy's LRCLIB text already lists every repeat, newton has none), so the mechanism was tested synthetically: jeremy's text was reduced to its first occurrence of every line (40 to 29 lines), faster-whisper segments were mapped to compact lines with rapidfuzz (blend of token-set and plain ratio, accept >= 45), consecutive segments mapping to the same line merged, ASR starts used as line starts, and MMS aligned the expanded text.
Result: 27 line instances recovered; sequence **recall 0.65 / precision 0.96** against the true 40-line order (recall is capped by whisper's own 0.69 word recall: it missed whole lines); 74 % of instances start within 2 s of the matching LRCLIB line; aligned instances have mean token score 0.46, and their starts equal the full-LRCLIB alignment (median |delta| 0.00 s, 78 % within 250 ms, n = 27). Good enough as "Should": use it only to add missing repeats, never to drop supplied lines; low-confidence instances get `source=interpolated`.

## 5. Proposed MEASURED alignment gate (initial values, from 2 songs)

The PLAN's "word coverage >= 75 %" has no unambiguous meaning for CTC (every word is placed). Define coverage on **word score** and add independent agreement checks. Measured values in brackets (jeremy / newton):

| # | check | pass threshold (proposal) | measured |
|---|---|---|---|
| G1 | `lyrics_match_score` (ASR LCS F1 vs supplied text) | >= 0.70 (below: grade D, text probably wrong version) | 0.762 / 0.835 |
| G2 | `alignment_coverage` = words with MMS score >= 0.10 | >= 0.75 (< 0.60 triggers the stable-ts fallback, per PLAN) | 0.799 / 0.777 |
| G3 | mean token score | >= 0.30 | 0.399 / 0.443 |
| G4 | words with score < 0.01 (hard misses) | <= 0.12 | 0.031 / 0.083 |
| G5 | lines within 1 s of source line start + detected global offset (only if the source has line timings) | >= 0.85 | 0.875 / 0.922 |
| G6 | offset report | detected offset reported; > 0.15 s applied; > 3 s flags `version_mismatch` | -0.11 / -1.33 s |
| G7 | bias-removed word-start agreement with ASR words (250 ms) | >= 0.55 (a bias > 0.5 s means ASR timing is the outlier, ignore) | 0.586 / 0.949 |
| G8 | onset lift (word starts vs vocal flux onsets) | >= 1.15 (informational, grade only) | 1.34 / 1.25 |

Grade: A = G1, G2, G3, G4, G5, G7 all pass with G1 >= 0.80 and G2 >= 0.85; B = all pass; C = 1 to 2 fail (G1 never alone); D = G1 fails or G2 < 0.60 after the fallback. With these values **newton grades B (G1 0.835, G2 0.777), jeremy grades B (G1 0.762)**; neither reaches A. The original 90 % gate cannot be met on sung or rap audio with this model; 75 % on word-score >= 0.1 is the honest value. Only G1, G2, G3, G4, G7 need no source timings, so they also work for the transcribed-lyrics path.
Not a gate: per-line mean score (AUC about 0.5), `frac_dur_lt40ms` (3 to 13 %, informational).

## 6. Voices on newton-vs-nye (task 5)

Items = the 51 aligned LRCLIB lines (span = first word start to last word end from MMS), minus 2 lines shorter than 1.0 s (ids 15 and 20, to inherit their neighbours' voice), plus **1 ASR-only span** (whisper segment 2.6 s before the first lyric line, the announcer intro) as a probe: 50 items. Embeddings on `lead_vocals` at 16 kHz. Agglomerative, cosine, average linkage. ECAPA (SpeechBrain, 192-d) took 2.0 s and WeSpeaker ResNet34-LM (ONNX, 256-d) 0.8 s for the 50 items, both CPU, 6 threads. Median f0 per item (SwiftF0) is used only as an independent plausibility cue.

| model | eigengap k (normalised Laplacian) | silhouette k=2 / 3 / 4 / 5 | k=4 cluster sizes (items) | runs along the line sequence at k=3 / 4 (shuffled-label mean) |
|---|---|---|---|---|
| **ECAPA** | **3** (eigs 0, 0.41, 0.64, 0.93, 0.95) | 0.247 / 0.287 / **0.354** / 0.309 | 26, 14, 9, 1 | 3 (17.3) / 5 (32.0) |
| WeSpeaker | 2 (eigs 0, 0.43, 0.72, 0.88) | **0.285** / 0.263 / 0.279 / 0.236 | 26, 14, 9, 1 | 3 (17.3) / 5 (32.0) |

Agreement between the two models (adjusted Rand index of the labels): k=3 **1.00**, k=4 **1.00**, k=5 0.93, k=2 0.12 (ECAPA k=2 splits off only the announcer probe).

Line to cluster sequence at k=4, **ECAPA = WeSpeaker, identical** (line ids; ids 15 and 20 excluded; `ann` is the ASR-only intro probe):
* **A**: lines 0-14 and 31-41 (26 items, 52 s voiced)
* **B**: lines 16-30 (14 items, 28.5 s)
* **C**: lines 42-50 (9 items, 41.5 s; median f0 about 139 Hz against about 252 Hz for A and 236 for B)
* **D** (announcer probe, 1 item, 2.6 s): the intro span, own cluster at every k >= 3

Compact order: `A(0-14) B(16-30) A(31-41) C(42-50)`, announcer before line 0.

Plausibility: **good, with one unverified assumption.** (1) Blocks, not scatter: 5 runs against a shuffled-label expectation of 32 (2.5th percentile 26); (2) two unrelated models give the same partition (ARI 1.0 at k=3 and k=4); (3) the late voice (C) enters at line 42 of 51 (the last fifth of the lyrics), is the lowest-pitched and is the only cluster with a clearly different register, which matches "one rapper joins late"; (4) the announcer probe separates at once. What is not proven: the battle should alternate A B A B, but only 3 blocks appear for the two main rappers (A takes both the first and the third block, and nothing carries a fourth turn), and A and B are close in register (252 vs 236 Hz) so their boundary is the least reliable part; without hand labels I cannot confirm that block 31-41 is the same performer as block 0-14. Eigengap gives 3 or 2 depending on the model, so **the estimate cannot replace the user's character count**: PLAN's "n from `intent.md` first, estimate otherwise" stands, and the estimate is reliable only as a lower bound (announcer plus 2 or 3 voices, k=4 maximises silhouette for ECAPA).
Short lines: skip < 1.0 s and inherit the voice of the neighbouring item.

**Model pick: ECAPA-TDNN (SpeechBrain) as primary**, matching env-main: higher silhouette at k=4 (0.354 vs 0.279), eigengap reaches the expected 3, same torch env; both give identical partitions at k=3 and 4, so **WeSpeaker ONNX stays the torch-free fallback** (2.5x faster). Needs `LocalStrategy.COPY` and `overrides={"pretrained_path": dir}`.

## 7. Rhubarb Lip Sync 1.14.0 and the mouth_open envelope (task 6)

Excerpts of 20 s of `lead_vocals` (16 kHz, 16-bit PCM mono, `rhubarb.exe -f json -o ... -d <dialog.txt> in.wav`), dialog = the aligned lines inside the excerpt, written to a temp directory **outside the repo and deleted afterwards** (verified: `temp_dialog_deleted=true` in every run). Every run was repeated without `-d`.

| excerpt | audio | runtime with -d / without | cues | cues/s | open-shape (non-X) share while the voice is on | X share inside aligned word spans |
|---|---|---|---|---|---|---|
| jeremy 76.9-96.9 s (6 lines, 30 words, sung) | sung rock | **6.5 s / 6.8 s** (RTF 0.33) | 81 / 82 | 4.1 | 97.6 % | 12.8 % |
| jeremy 107.7-127.7 s (4 lines, 24 words, sung) | sung rock | 6.0 s / 6.2 s | 67 / 64 | 3.35 | 96.2 % | 2.3 % (no dialog 17.8 %) |
| newton 36.1-56.1 s (11 lines, 92 words, rap) | rap | **10.7 s / 11.4 s** (RTF 0.55) | 119 / 118 | 5.95 | 99.7 % | 0.3 % |

Plausibility:
* It runs and emits valid A-H/X cues on sung vocals (A to H all seen; B and C dominate) at about 1/3 real time, so the cost on a 5 minute song is about 100 s single-threaded. **Usable as a Should.**
* Closed (X) cues appear in the gaps between phrases (54 to 66 % of unvoiced frames on the jeremy excerpts), and it is almost never closed during sung words. Correlation of the openness proxy (A 0.05, B 0.3, C 0.6, D 1, E 0.5, F 0.3, G 0.2, H 0.6, X 0) with vocal level in dB: 0.48 and 0.34 (sung), **0.12 (rap)**: shape changes follow phonemes, not loudness, which is expected, but on dense rap it hardly ever closes, so the visual mouth never rests.
* `-d` changes the output modestly: with and without dialog the openness tracks correlate 0.75 and 0.42 (sung), **0.30 (rap)**; the dialog helps most where the vocals are the hardest. Because Rhubarb's pocketsphinx recogniser is English-only and the dialog is a hint, not a forced alignment, its cue **timing is not tied to our MMS word times** (0 to 67 % of opens fall within 150 ms of an aligned word start, on only 1 to 7 openings per excerpt; too few for a stable figure).
* Sustained notes are not a problem for Rhubarb; they are for our own word-span gating, see below.
* Verdict: **go (Should), with `-d` on**, as a decoration track only; `vocal.mouth_open` stays the primary lip-sync signal. Not validated against any video or human labels (no ground truth).

### mouth_open prototype (`bw_lipsync.py`, `bw_mouth.py`)

One-pole envelope on 10 ms RMS of `lead_vocals`, attack 10 ms, release 60 ms, per-song p95 gain, gated by the aligned word spans (+/- 80 ms), 100 Hz. Three gate definitions compared (share of the stem's envelope energy that the gate throws away):

| gate | jeremy: time open / energy outside | newton: time open / energy outside |
|---|---|---|
| raw CTC word spans | 47.9 % / **28.6 %** | 65.5 % / 8.9 % |
| word end extended to next word start; last word of a line held while env > p95 - 20 dB, at most 1.5 s | 55.7 % / 20.9 % | 67.2 % / 7.7 % |
| line span with the same hold | 55.7 % / 20.9 % | 67.2 % / 7.7 % |

Findings:
1. **Raw CTC word spans are too short for sung vowels** (the CTC peak ends the word long before the note does): gating with them removes up to 29 % of the vocal energy on jeremy. Use the **sustain-extended gate** (word to next word start, hold the last word of a line until the envelope falls 20 dB under p95, at most 1.5 s).
2. After that, the remaining 20.9 % on jeremy is almost entirely the wordless outro: 17.9 percentage points of the energy lie after the last aligned word (221 s). For songs with wordless singing `mouth_open` therefore needs an **ungated fallback** (gate = word spans, or vocal-activity regions from `stem_activity` when no word covers them).
3. Per voice on newton (ECAPA k=4 minus the announcer, neighbour rule for short lines): V = 15, 27 and 9 lines, open 17.1 %, 30.7 % and 23.1 % of the song; two voices' gates overlap on only **5.6 %** of open frames (the 80 ms padding and the hold at a turn boundary), so a per-voice `mouth_open.<voice>` with policy `max` is workable.
4. Correlation of the gated envelope with Rhubarb's openness in the excerpts is 0.19 to 0.43: the two measure different things (loudness vs shape), so they should be offered as separate tracks, not mixed.

## 8. Go / no-go per tool

| tool | verdict | fallback / condition |
|---|---|---|
| ffprobe tags + ffmpeg chromaprint | **go** | AcoustID unverified (no key) |
| MusicBrainz WS/2 (1 req/s) | **go with caveat** | reached the right recording for 2 of 4; Jeremy Redux needs a release filter or paging; handle 503 with backoff |
| LRCLIB cascade (get, get no album, search x2) | **go with the tweak** | ranking must prefer synced inside 2 s (newton); false-friend gate works (versatile); `/get` alone was 2.4 s off for jeremy |
| faster-whisper large-v3 int8 CPU | **go** | RTF 0.10 sung, 0.32 rap; match score is a usable confidence input; filter untested on a real hallucination |
| MMS_FA via torchaudio `forced_align` | **go** | RTF 0.09 for emissions, Viterbi 0.07 s; windowing, offset detection and line constraints verified; vendored Viterbi unused |
| stable-ts align | **go as fallback only** | good on lines, weaker on words, 2 to 3x slower |
| repeated-section expansion | go (Should) | recall 0.65 / precision 0.96 on the synthetic test |
| SpeechBrain ECAPA | **go (primary)** | WeSpeaker ONNX the torch-free fallback |
| agglomerative + eigengap | **go with caveat** | estimate is only a lower bound; user character count wins |
| Rhubarb 1.14.0 with `-d` | **go (Should)** | RTF 0.33 sung, 0.55 rap; decoration track only |
| mouth_open envelope | **go (Must)** | sustain-extended gate and an ungated fallback for wordless vocals |

## 9. Change requests

1. **PLAN 5 lyrics cascade ranking:** after the text gate, among candidates within 2 s prefer `has_synced`, then the smallest |delta| (newton: the smallest-delta entry has plain lyrics only).
2. **PLAN 5 / 10 identity:** MusicBrainz search for titles with a parenthesised version tag should retry without the parenthesis and page past 8 results (or filter by release); Jeremy's Redux recording was not found in the first 8 of 624.
3. **PLAN gates (W0 measured gate):** replace "word coverage" by the G1 to G8 table above; do not gate on mean line score.
4. **PLAN lipsync / mouth_open:** gate on the sustain-extended word span, not raw CTC spans, and give `mouth_open` an ungated fallback for wordless vocals; per-voice tracks are safe.
5. **Environment:** nothing missing. `stable_ts.align` prints `SyntaxWarning` for an escape in its docstring on import (harmless). PLAN 12 still says `heavy.lock`.
6. **env-sep:** `lead_vocals` from the karaoke pass is good enough for words, voices and Rhubarb; no separate htdemucs vocal stem is needed for these stages.

## 10. Reproduce

```powershell
$s = "C:\Users\OpenSrcerer\Desktop\playground\mv-harness\docs\research\spike-scripts\bench-words"
powershell -NoProfile -File scripts\run.ps1 python $s\bw_identity_lrclib.py            # tasks 1+2, network, ~15 s per song
powershell -NoProfile -File scripts\run.ps1 python $s\bw_whisper.py jeremy             # task 3 (heavy slot)
powershell -NoProfile -File scripts\run.ps1 python $s\bw_align.py jeremy               # task 4 MMS (heavy slot; emissions cached)
powershell -NoProfile -File scripts\run.ps1 python $s\bw_stablets.py jeremy            # task 4a (heavy slot)
powershell -NoProfile -File scripts\run.ps1 python $s\bw_quality.py jeremy             # onset cross-check
powershell -NoProfile -File scripts\run.ps1 python $s\bw_expand.py                     # 4b synthetic expansion
powershell -NoProfile -File scripts\run.ps1 python $s\bw_gate.py                       # gate statistics
powershell -NoProfile -File scripts\run.ps1 python $s\bw_voices.py                     # task 5 (heavy slot)
powershell -NoProfile -File scripts\run.ps1 python $s\bw_lipsync.py jeremy L12         # task 6 Rhubarb + envelope (heavy slot)
powershell -NoProfile -File scripts\run.ps1 python $s\bw_mouth.py newton-vs-nye        # gate comparison, per voice
```
(`bw_whisper_tail.py` is the no-VAD probe of the jeremy outro.) Outputs: `tests/.cache/real/<slug>/{http,identity,lyrics_src,whisper_cpu,align_mms,align_stablets,voices,rhubarb,mouth_open}/` and `tests/.cache/real/index.words.json`.
