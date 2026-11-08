# builder-m5 report: M5 Words (identity, lyrics, voices, lipsync)

Status: **done** (all four stages real; unit tests green incl. the model tests; all four real songs and the
synthetic song run on the final code; gate: see "Gate"). Progress log: `docs/build/progress/builder-m5.md`.
Contract decisions: `docs/contract/decisions/M5.md` (M5-D1 .. M5-D22, CR-M5-1, CR-M5-2).
No lyric text appears in this report, in any log line the stages write, in warnings, summaries or provenance.

## Files (owned paths only)

| Path | What |
|---|---|
| `src/mvh/stages/identity/{__init__,core}.py` | tag normalisation, chromaprint + AcoustID (key only), MusicBrainz (1 req/s, UA, version-tag retry, paging, 503 back-off), credits |
| `src/mvh/stages/lyrics/{__init__,core,lrclib,text,asr,align,ctc_viterbi,grade,exports,vocal_env}.py` | source cascade, ASR, MMS_FA alignment, offset, expansion, G1-G8 gate, LRC/VTT/SRT/ASS |
| `src/mvh/stages/voices/{__init__,core,embed,cluster,intent}.py` | ECAPA (WeSpeaker ONNX fallback) embeddings, k selection, clustering, backing spans, intent.md |
| `src/mvh/stages/lipsync/{__init__,core}.py` | gated mouth_open (+ per voice), ungated wordless fallback, Rhubarb visemes, g2p phonemes |
| `tests/unit/{identity,lyrics,voices,lipsync}/` | 51 tests: logic (fast), synthetic through the real models (`models`, default on), real songs (`real`, opt-in) |
| `tests/synth/m5/{harness,fakehttp,make_http_fixtures,pytest_markers}.py` | in-process harness on the runner's child code, recorded-HTTP replay, markers |
| `tests/fixtures/http/{musicbrainz_versioned,lrclib_synth}.json` | SYNTHETIC recorded HTTP only |
| `docs/contract/decisions/M5.md` | additive fields, interpretations, change requests |

## What each stage does

**identity** (1.0.0). Normalises ingest's ffprobe tags (title, artist, album, album artist, year, ISRC, track, genre,
credit tags). In `max` (`verify: true`) it looks the recording up: AcoustID only with `ACOUSTID_API_KEY` /
config.json key (ffmpeg chromaprint, gzip POST); MusicBrainz WS/2 at 1 req/s with the identifying User-Agent: ISRC
lookup, recording search with a ±3 s duration window (full title, then without the parenthesised version tag), then
plain searches paged (limit 100, 2 pages), 503 back-off. Match = score >= 90, |Δdur| <= 3 s, title/artist gates.
Credits from artist and work relationships. Offline without a cached response: tags kept, `identity:offline`.
`conf` 0.98 tags+MB agree, 0.9 tags only, 0.85 tags with no MB match.

**lyrics** (1.0.0). Cascade `--lyrics` file > embedded tags (D8 path to ingest's `embedded_lyrics.json`) > LRCLIB >
faster-whisper transcription. LRCLIB: get+album, get, search(track, artist), search(q) every time; title/artist gate,
then within 2 s prefer synced, word sync, smallest |Δdur|; 2-5 s accepted with `version_mismatch`. ASR always runs
when there is a voice: faster-whisper large-v3 int8 CPU on the vocal stem (arrays, temperature 0, Silero VAD with
the library defaults, beam 5), hallucination filter incl. the vocal-activity mask, and (new, M5-D19) a no-VAD retry
when VAD keeps < 0.15 words per active second. Alignment: torchaudio MMS_FA `forced_align` over 30 s windows with 2 s
context (vendored Viterbi fallback, stable-ts below 0.60 coverage), uroman + num2words, line-group windows with the
line-window constraint, global offset (median CTC - source line start, applied > 0.15 s, mismatch > 3 s),
ASR-guided repair bounded by the source window, repeat expansion and ASR-only lines that only ADD lines, sustain
extended word durations, overrides (`lyrics.lines`, `lyrics.words`). Gate G1-G8 exactly as bench-words §5 plus
M5-D20 (G1 needs ASR evidence); never the per-line mean score. Outputs `lyrics.json` (speaker_hint per D3, flags,
gate, asr, alignment, lrclib blocks) and `.lrc` (A2 word tags), `.vtt`, `.srt`, `.ass`.
Vocal stem: `lead_vocals`, or `vocals` when lead is > 20 dB quieter (M5-D18, MEGAFAUNA).

**voices** (1.0.0). One item per aligned line (word chunks for long lines, < 1 s lines inherit their neighbour),
SpeechBrain ECAPA on the vocal stem (`LocalStrategy.COPY`, explicit `pretrained_path`), WeSpeaker ONNX fallback.
k: intent.md (count or mapping) > speaker labels in the source > estimate (1 when the 2-split is not separated;
else best silhouette at k >= eigengap; eigengap bound itself under 24 items, M5-D21; minor clusters folded,
foreign singletons such as an announcer kept). Agglomerative cosine/average. V1.. by first appearance, conf from
the centroid margin, `review` flags (low conf, inherited, grade-D lyrics M5-D22). Backing spans from
backing_vocals for duets. `events/voice_spans.json`, `meta/voices.json`, voice activity curves.

**lipsync** (1.0.0). `vocal.mouth_open` = vocal envelope (10/60 ms attack/release) gated by the
sustain-extended word span (word end held to the next word start; a line's last word held while the envelope stays
within 20 dB of p95, <= 1.5 s, stopping at the next line's start), ±80 ms pad, soft edges; ungated fallback for
wordless vocals (handed to the nearest sung voice). `vocal.mouth_open.<V>` when >= 2 voices (D16). Rhubarb 1.14.0
per voice block (16 kHz 16-bit WAV, `-f json -o`, `-d` dialog in scratch, deleted after; `--threads 1`, blocks in
parallel, deterministic) as a decoration viseme track filled with `X`; g2p-en ARPAbet phonemes over aligned words.

## Measured accuracy vs thresholds (synthetic, scored against `tests/contract/synth/_truth`)

| test | threshold | measured |
|---|---|---|
| word onset error on TTS, plain-text user file (anchored) | median < 80 ms (PLAN §7) | **20 ms**, p90 76 ms, 96.2 % < 300 ms, 53/53 words, grade A, coverage 1.0, G1 1.0 |
| same, synthetic LRCLIB with a +1.3 s version offset | offset detected (±0.15 s), median < 80 ms | offset **-1.28 s** (truth -1.3), median **20 ms**, p90 136 ms; L002 override +0.25 s honoured (timing_source user); 4 requests |
| same, transcription only (no text) | median < 80 ms on LCS-matched words | **20 ms** median, 53/53 words matched, p90 80 ms, grade B (G1 n/a) |
| voices: estimate on the 2-singer synthetic song | k = 2, >= 90 % lines right | k = 2 (eigengap bound, 10 items), attribution >= 0.9 (asserted), duet backing spans V2 |
| voices: intent.md count + override | n_source intent, C1/C2 proposed, override conf 1 | pass |
| lipsync: per-voice gating vs truth words | own voice open > 0.05, other < 0.02 inside every word | pass; energy outside gate 0.0 (< 0.15) |
| lipsync: sustain hold | held to next word, last word held while sustained, capped at 1.5 s | pass (exact frame asserts) |
| Rhubarb visemes | A-H/X only, whole timeline per voice, no gaps, dialog files deleted | pass (227 visemes, 2 voices) |
| identity: version-tag retry, ±3 s window, 503, offline | per SPIKE | pass (recorded synthetic HTTP) |

## Real songs (upstream = tests/contract/real-<slug>, final code, online LRCLIB/MusicBrainz)

Timings are wall time per stage on 6 threads (CPU), heavy slot held.

| | jeremy | newton-vs-nye | megafauna | versatile | synth |
|---|---|---|---|---|---|
| identity | tags+MB accepted (version-tag retry), conf 0.98, 2 credits, 0.3 s | MB accepted, 0.98, 3 credits, 0.3 s | MB accepted, 0.98, 7 credits, 0.4 s | MB not found, 0.85, 0.3 s | MB not found, 0.85 |
| lyrics source | LRCLIB **22859144** (Δdur 0.00 s, via search) | LRCLIB **3921433** (synced, Δ -0.44 s) | embedded tag (txt, LRCLIB 404) | none (instrumental) | transcribed |
| grade / G1 / G2 coverage | **B** / 0.752 / 0.763 | **B** / 0.851 / 0.763 | **D** / 0.544 (asr_unreliable) / 0.684 | n/a | B / n/a / 1.0 |
| G3 / G4 / G5 / G7 / G8 | 0.388 / 0.072 / 0.875 / 0.566 / 1.36 | 0.435 / 0.099 / 0.941 / 0.946 / 1.24 | 0.216 / 0.040 / n/a / 0.650 / 1.27 | | 0.743 / 0.0 / n/a / n/a / 1.26 |
| offset | -0.14 s (not applied) | **-1.32 s applied** (W0 -1.33) | n/a (unsynced) | | |
| lines / words | 40 / 194 | 52 / 476 (51 + the announcer intro, asr_only) | 14 / 76 (anchored, 53 % anchors) | 0 | 10 / 53 |
| last word end | **218.1 s** (outro wordless) | 123.3 s | 178.5 s | | 41.8 s |
| ASR | 149 words, p 0.854, P/R 0.866/0.665 | 473 words, p 0.914, P/R 0.854/0.849 | VAD 2 words -> no-VAD retry 71 words, p 0.651 | 0 words (VAD), retry not used | 53 words, p 0.931 |
| lyrics time | 129.7 s | 142.5 s | 126.2 s (two ASR passes) | 10.3 s | 40.8 s |
| voices | **1** (estimate, 2 -> 1 merge_minor) | **4**: V1 announcer, V2 L002-016 + L032-043, V3 L017-031, V4 L044-052 | 1 (eigengap bound, 1 item folded), all 14 spans review | 0 | 2 + 4 backing spans |
| voices time | 7.1 s | 5.4 s | 3.6 s | 0.1 s | 2.6 s |
| lipsync | 1 channel, open 74.9 %, outside-gate energy 0.026, ungated 75.5 s (the wordless outro), 539 visemes | 5 channels, open 73.2 %, 0.015, ungated 15.0 s, overlap 3.1 %, 714 visemes, 1554 phonemes | vocals stem, open 40.7 %, 0.007, ungated 46.4 s, 175 visemes | ungated 0.7 s only | 3 channels, overlap 55.5 % (duet), 227 visemes |
| lipsync time | 45.9 s | 44.7 s | 24.8 s | 0.9 s | 12.4 s |

Sanity checks against the brief and W0:
- **Jeremy**: LRCLIB 22859144 chosen (the `/get` candidate is 2.4 s off; search finds the exact one), grade B like
  W0 (G1 0.752 vs W0 0.762), no lyric words after 218.1 s; the 217-300 s wordless outro is covered by the ungated
  mouth fallback (asserted in the real test). One voice (3 isolated timbre-change lines folded).
- **newton-vs-nye** (stress test): offset -1.32 s detected and applied (G5 0.94, G7 0.95). The voice partition is
  W0's ECAPA/WeSpeaker k = 4 partition exactly: announcer, A (two blocks), B, late low-register rapper C. The
  announcer intro is now a lyric line (M5-D11 refinement) and its own voice (centroid cosine <= 0.06 to the rest).
  Blocks, not scatter (5 runs). Per-voice mouth channels overlap only 3 %.
- **MEGAFAUNA**: the lead/backing split put the whole voice in backing (lead p95 -74 dBFS), so all three stages use
  the `vocals` stem (M5-D18). Silero VAD discarded the processed voice (2 words); the no-VAD retry recovers 71 words
  and anchors (F1 0.00 -> 0.54, whole-song -> anchored alignment). The grade stays an honest **D** (three gate
  fails); voices flags every span for review. The user should check lines in the viewer.
- **Versatile**: instrumental; LRCLIB false friends rejected (no match), no lines, no voices, Rhubarb skipped.
- Determinism: newton ran twice on unchanged lyrics code (17:52 and 21:24) with identical numbers (temperature 0, default VAD).

## Gate

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gate.ps1 M5` (22:49, exit 1):

| step | result | note |
|---|---|---|
| fixture | PASS | |
| unit | FAIL | identity=0 lyrics=0 voices=0 lipsync=0 (all M5 folders green); **contract=1**: `test_stub_files_are_stubs` asserts rhythm is still a stub (M2 replaced it), CR-M5-3 |
| review | SKIP | no tests/review/M5 folder |
| ruff | PASS | `ruff check src tests` |
| contract | PASS | `mvh.contract.gen --check` |
| validate | PASS | |
| e2e | PASS | full 25-stage analyze of the synth song with every module's real stage (2107 s, slot contention) + validate |
| lib-node | PASS | |
| determinism | FAIL | 28 of 179 files differ; the first non-deterministic outputs are upstream: `stems/drums/*.flac` (M3a drums), `curves/stems.f32`, `events/sections.json`; M5's lyrics/voices/lipsync files differ downstream of those |

M5 determinism verified separately with fixed upstream (`scratchpad/m5_det.py`: identity, lyrics, voices, lipsync run
twice on the synth fixture through the harness, every output file byte-compared): **0 files differ**. So both gate
failures are outside M5's owned paths; they are reported as CR-M5-3 and CR-M5-4.

Unit runs inside the gate (models on, real opt-in skipped): identity 8 passed, lyrics 24 passed / 4 skipped (real),
voices 10 passed, lipsync 5 passed (229 s total). With `MVH_SKIP_MODELS=1` the M5 folders run in ~8 s. Real songs (opt-in, `MVH_REAL_TESTS=1 ... pytest tests/unit/lyrics/test_real_songs.py`): **4 passed** in 742 s (jeremy, newton, megafauna, versatile; LRCLIB replayed from the W0 recordings).

## Decisions (full text in docs/contract/decisions/M5.md)

- M5-D1 lyrics reads `embedded_lyrics.json` through the D8 path; `ingest` NOT added to lyrics deps because
  `tests/unit/contract/test_deps_match_plan` pins PLAN deps (CR-M5-1).
- M5-D2/D3 cascade order and LRCLIB ranking; M5-D4 MusicBrainz by default in `max`.
- M5-D5 grade per bench-words §5; M5-D6 coverage = G2; M5-D7 word `d` is the sung (sustain-extended) duration;
  M5-D8 line ids/groups; M5-D9 timing_source values; M5-D10 user word timings authoritative; M5-D11 lines only added
  (ASR-only intro rule refined this session); M5-D12/D14c bounded ASR-guided repair; M5-D13 overrides by run ids;
  M5-D14 determinism (temperature 0, default VAD); M5-D14b activity = stem_activity OR envelope.
- M5-D15/D16/D17 voices k source order, merge_minor, conf/review, tolerant intent.md parsing.
- M5-D18 vocals-stem fallback. New this session: **M5-D19** no-VAD retry, **M5-D20** G1 applicability,
  **M5-D21** small-sample eigengap bound, **M5-D22** review flags on grade-D lyrics.

## Change requests

- **CR-M5-1** add `ingest` to lyrics' deps and to `PLAN_DEPS` in `tests/unit/contract/test_catalog_dag.py`
  (the brief allowed the dep, but the contract DAG test pins it; code switches automatically).
- **CR-M5-2** fold the additive fields (lyrics `source.*`, `gate`, `asr` incl. `vad`/`vad_retry`, `alignment`,
  `lrclib`, `words[].flags` values; voices meta extras; voice_spans `role`/`source`) into `catalog.py`.
- **CR-M5-3** `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` asserts `mvh.stages.rhythm.run`
  still calls `run_stub`; M2 replaced that stub, so `unit: contract=1` fails in every module's gate (not an M5
  file; M5's own folders are all green). The test should use a stage that stays a stub or check the template.
- **CR-M5-4** (M3a / M2 / W3) gate determinism: `analyze --force` twice gives different `stems/drums/*.flac`,
  `curves/stems.f32` and `events/sections.json`; everything downstream (incl. lyrics `section_id`, voice spans,
  visemes) inherits the difference. M5 alone is byte-deterministic with fixed inputs.

## Open issues

- MEGAFAUNA grade D: MMS on a heavily processed EDM voice gives mean token score 0.22; coverage 0.68 is above
  the 0.60 stable-ts trigger, so stable-ts did not run. Needs a user check or a `--lyrics` file with timings.
- tests/contract/real-* have no stem_activity outputs; the M5 harness synthesises `stem.*.active` (PLAN rule).
  Real `stem_activity` (M3a) may differ slightly; our activity is OR-ed with the stem envelope anyway (M5-D14b).
- Versatile: 0.7 s of ungated mouth on an instrumental (a vocal chop). Harmless, could be suppressed when
  `instrumental` is true if the user prefers.
- g2p-en emits a SyntaxWarning on import (library, Python 3.13); harmless.
- The ffmpeg Vulkan whisper path is draft-only (no VAD) and was exercised on synth only.
