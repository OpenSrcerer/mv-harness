# fixtures — W1b report

**Generator command** (one command regenerates everything; the synth part is byte-identical on rerun):

```powershell
Set-Location C:\Users\OpenSrcerer\Desktop\playground\mv-harness; . .\scripts\mvh-env.ps1 -Offline
uv run --frozen --no-sync python -m tests.synth.build                 # synth + real-* (real needs tests/.cache/real/)
uv run --frozen --no-sync python -m tests.synth.build --only synth    # ~20 s -> tests/contract/synth/ (+ .done.json)
uv run --frozen --no-sync python -m tests.synth.build --check         # rebuild in a temp dir, diff vs .done.json (exit 1 on diff)
```

The gate should call `python -m tests.synth.build --only synth` when `tests/contract/synth/.done.json` is missing
(`tests/unit/fixtures/conftest.py` does the same).

## Deliverables

| Path | What |
|---|---|
| `tests/synth/audio_io.py` | WAV r/w (f32/s16/s24), 24-bit grid quantiser, bitexact ffmpeg encode (flac24/16, mp3, opus, cover art, tags), ffmpeg decode |
| `tests/synth/dsp.py` | seeded oscillators/envelopes, drum one-shots (kick, snare, 2 toms, closed/open hat, ride, crash), bass/pad/piano voices, riser |
| `tests/synth/midi.py` | deterministic SMF writer (tempo map, time-signature changes) |
| `tests/synth/tts.py` | SAPI David/Zira word rendering (committed int16 assets), sentences with SAPI word marks, LPC "singing" resynthesis with exact f0/voicing truth |
| `tests/synth/assets/tts/` | 46 word clips (.npy, 2.4 MB) — commit them (they make regeneration independent of installed voices) |
| `tests/synth/primitives.py` | click tracks (tempo ramp, swing), EBU 3341/3342 + true-peak signals, sweeps, MIDI render (bass line, chords), vibrato "sung" sines, TTS sentence/words, edge-case files (mono, 48 kHz, MP3 encoder delay, corrupt FLAC, 10 s, 10 min, unicode path) on demand under `tests/.cache/synth/` |
| `tests/synth/song/{score,render,truth,analysis,folder}.py` | the synthetic song: score = ground truth -> stems -> derived truth -> contract folder |
| `tests/synth/real.py` | W0-cache adapters -> `tests/contract/real-<slug>/` + `coverage.json` |
| `tests/synth/stubrun.py` | minimal Ctx/Writer to run `mvh.contract.fixture.run_stub` for every stage (optional dry mode) |
| `tests/synth/build.py` | the CLI above |
| `tests/contract/synth/` (generated) | complete song folder: 195 files, every catalogue output of every stage, `_intermediate/<stage>/`, `_truth/`, `.done.json` |
| `tests/contract/real-{megafauna,versatile,jeremy,newton-vs-nye}/` (generated) | partial folders for the stages W0 covered |
| `tests/contract/README.md` | how to regenerate, truth kinds per file, the real-folder coverage table |
| `tests/unit/fixtures/test_fx_*.py` | 57 tests (folder, links, audio, stubs, determinism, primitives, real) |

## The synthetic song (tests/contract/synth/)

"Lanterns on the Tide": 56.5 s, 44.1 kHz stereo, 120 BPM, A minor. Pickup beat (bar 0, beat_in_bar 4) at 0.5 s; intro
(bars 1-4), swung verse with call-and-response (5-8), duet chorus (9-12), build with snare roll + riser and **one 3/4 bar**
(13-16), **one bar of digital silence** (17), the **drop** = chorus#2 (18-25), outro with a final hit and a 4 s decay
(26-28, last bar without pulse). Swing 1.5 (60:40) in verse/chorus/outro, syncopated kick and bass; kick, snare, toms,
hihat, ride, crash each on its own DrumSep sub-stem; bass; pad (other); piano arpeggio; riser; two singers.

Ground-truth numbers (from `_truth/truth.json` / the folder): 112 beats, 29 bars, 6 sections, 8 phrases, 2 EDM roles,
16 eight-counts (E000 lead-in, 4 partial), 11 grooves, 370 drum hits, notes: bass 113, other(pad) 78, piano 64,
guitar 0, vocals 53 (lead) + 30 backing words, 10 lyric lines / 53 words, 2 voices / 2 characters, 14 voice spans,
17 hit points, 11 holds, 178 cues, 10 moments. Integrated -20.38 LUFS, LRA 7.2 LU, true peak -0.99 dBTP; the drop
classifies as `peak`, the silent bar as `silence`.

Truth kinds (stated in every file's provenance `params.truth`): **fixture** (exact generator truth: rhythm, structure,
counts, grooves, drum hits, notes, chords, key, lyrics timing, voices/singing, f0, dynamics events, hit points, holds, cues,
stems), **measured** (reference DSP of the rendered audio: band/fine/timbre/stereo/flux, spectrum128 approximation,
loudness, stem levels/activity, dynamics levels), **synthetic** (mood, instruments, vocal style, visemes/phonemes,
moments ranking, meaning). Example user inputs: `meaning/intent.md` and a draft `meaning/authored.json`.

Checks that pass (tests/unit/fixtures):
- every JSON (events, meta, intermediates, manifest, run, curves index) and every table row validates against its schema;
  `.done.json` hashes match the tree; manifest lists every public file;
- every required catalogue output of every stage exists, every non-pattern channel is in `curves/index.json`;
- IDs are numbered in time order and link: sections <-> phrases <-> bars.csv <-> counts <-> beats.csv; lines <-> words
  <-> sections; voice_spans <-> voices <-> characters <-> singing <-> lines.tsv; cues/hit points/holds sources resolve
  (`beat:<i>`, `bar:<n>`, IDs); moments -> cues; mood/edm roles -> sections; meaning sections match section times;
- stems decode to exactly the mix (`vocals = lead + backing`, `drums = Σ subs`, six-stem sum, `instrumental = mix − vocals`),
  same length; canonical.wav == mix; the input FLAC has tags + an attached cover stream;
- every truth drum hit has a transient at its sample in its sub-stem; the lead stem's pitch (autocorrelation at the
  vowel nucleus) matches the programmed note within 0.6 st; `vocal.midi` medians match word notes within 0.35 st;
  every word onset is audible; the silent bar and the pre-roll are exact zeros;
- a stub run of **every** stage (run_stub via StubWriter) succeeds and re-packing the handed-over channels reproduces
  `curves/*` byte for byte; regeneration into tmp_path is byte-identical;
- primitives: click onsets, tempo ramp, swing 60:40, EBU 3341 cases 1-4 within 0.1 LU (pyloudnorm), 3342 LRA within 1 LU,
  true peak (fs/4, 45°) within 0.2 dB, sweep frequency, MIDI render, sung-sine f0, TTS word onsets, SAPI word marks,
  edge-case decodes (MP3 gapless trimming verified within 1 ms).

End to end: `mvh analyze tests\contract\synth\_truth\synth-song.flac --out out\_wip\fixtures\synth --no-network` (runtime
CLI, built concurrently) exits 0 through every stage; the real ingest reproduces the fixture's `pcm_sha256` exactly.

## Real folders (tests/contract/real-<slug>/)

Adapters, not truth: provenance says "REAL-SONG ADAPTER". Full: ingest, identity, separate_fast, separate_hq, allin1,
rhythm (beat_this only, no fusion), loudness, structure (allin1 segments on downbeats, naive 4-bar phrases), notes,
vocals (RMVPE) on all four; lyrics + lipsync on jeremy and newton-vs-nye; voices on newton-vs-nye (2 voices, unlabelled).
Partial on all: spectral (no hit/onset events, slope, balance, mid/high raw hits), harmony (no chroma12). Absent:
stem_activity, drums, instruments, mood, dynamics, choreo, cues, meaning, brief, viewer, frames. Table in
tests/contract/README.md; detail per output in each `coverage.json`. Sizes 0.6-1.2 GB each (canonical.wav and fast stems
are hard links into tests/.cache/real/). No lyric text was printed or written outside these gitignored folders.

## Commands run and results
- `python -m tests.synth.build --only synth`: 195 files, 0 validation errors, ~19 s.
- `python -m tests.synth.build --check`: 0 differing files (run 3 times across code reformatting).
- `python -m tests.synth.build --only real`: 4 folders, 0 errors, 0 validation errors.
- `python -m pytest -q tests/unit/fixtures tests/unit/contract`: **147 passed, 1 skipped (10-min file, MVH_SLOW=1), 1 xfailed** (CR 1 below).
- `ruff check tests/synth tests/unit/fixtures` and `ruff format --check`: clean.

## Deviations
- `lib/` is not in the fixture (the runner's finalize copies it; the lib files were changing concurrently and would break
  byte-identity). `schema/` is included.
- `viewer.html` is a placeholder; `frames/` holds one sample export (`24fps.csv`, 6 channels).
- spectrum128 / `bands.*_viz` use an approximation of the viz mapping (documented), not the exact `viz/js/audio.js` port.
- Dynamics level thresholds (quiet < -12, soft < -6, medium < -2, loud < +1.5 LU, else peak; silence < -60 LUFS) are the
  fixture's own choice, documented in provenance.
- Separation models in meta/separation.json are `fixture.generator` (the stems ARE the generator tracks).
- `meta/source.json.palette` is the cover's designed palette; the real ingest's k-means returns close but not identical hex
  values (JPEG) plus a 6th mixed colour: compare palettes with a tolerance.
- Source files carry `# ruff: noqa: E501` (long data tables/docstrings); the rest of the lint set is clean.

## Open issues
- The fixture manifest is ~12.4k characters (~3.1k tokens by chars/4), just over the 3k-token cap, almost all of it
  `files[]` (110 entries without schema/). Real songs will be similar (CR 2).
- `test_tts_sentence_word_marks` and missing-asset regeneration need Windows SAPI; with the committed assets the synth
  build does not.
- `MVH_SLOW=1` enables the 10-minute edge-case test (not run here).

## Change requests
1. **`src/mvh/contract/fixture.py` (contract owner):** `run_stub` turns `{src}`/`{stem}`/... into `*`, so the notes stub's
   `notes/{src}.mid` also copies `notes/notes.mid` and `notes/vocals.mid`, and `events/notes.{src}.json` also copies
   `events/notes.vocals.json` (owned by the vocals stage). Restrict each placeholder to its valid values
   (`{src}` in bass|piano|guitar|other for notes) and skip paths another declared output of any stage owns.
   Pinned by the strict xfail `tests/unit/fixtures/test_fx_stubs.py::test_each_file_copied_by_one_stage`.
2. **Manifest token cap (CONTRACT §1, runtime finalize):** `files[]` alone pushes manifest.json past 3k tokens for a full
   song (~110 files). Either exclude `files[]` from the cap, or write it compactly (one line per entry / no indent).
