# builder-m3b report: M3b pitch and timbre (notes, vocals, instruments)

Status: implemented and measured on the synthetic song and all four real songs. Gate result: see "Gate" at the end.
No real-song lyric text appears anywhere in this report, in the logs or in the test output.

## What each stage does

### instruments (`src/mvh/stages/instruments/`: `__init__.py`, `ced.py`, `clap.py`, `vocab.py`, `fuse.py`)
- CED-base ONNX (AudioSet 527 labels) on the mix and on every available stem (vocals, lead_vocals, backing_vocals, drums,
  bass, guitar, piano, other), 4 s windows at a 1 s hop on 16 kHz mono. The output is ALREADY a probability: no sigmoid
  (unit test `test_ced_output_is_already_a_probability`). Silent windows are skipped (probability 0).
- 28-slug open vocabulary (`vocab.py`) mapping AudioSet label groups to instruments, with per-slug lo..hi scaling.
- Fusion with stem activity (I-M3b-2): an instrument that owns a separator stem needs both the stem and the tag; the
  vocals stem alone is weak evidence of a voice (w = 0.2), which is what keeps MEGAFAUNA's synth-lead "vocals" stem from
  becoming a voice.
- Outputs: `inst.<slug>` curves at 1 Hz for every slug (zeros when absent), `vstyle.<singing|speech|rap>` curves,
  `events/instruments.json` segments (hysteresis 0.5/0.35, >= 2 s, `evidence` = both | stem | tagger, `stem`),
  `events/vocal_style.json`, `meta/instruments.json` (summary rows with coverage/mean/peak, vocal_style with shares and
  dominant, top_tags, vocabulary).
- CLAP (Xenova larger_clap_music_and_speech ONNX) only for RELATIVE curves: synth sub-types (pad/lead/arp/bass, capped by
  `inst.synth`) and user terms (`--param instruments.vocabulary=[...]` -> `inst.term_<slug>`). Never a top-1 label, never
  a segment or summary row; index descriptions say "RELATIVE (CLAP)".
- Vocal style: CED singing/speech/rapping groups on lead_vocals; speech over a hip-hop context counts as rap; a SwiftF0
  pitch-sustain ratio moves weight to singing when notes are held (style only; SwiftF0 is never used for presence).
- QA: warning + `qa:vocals_stem_non_vocal_s=<n>` provenance note when the vocals stem is active without vocal tags;
  `instruments:no_clap` fallback (status degraded) if CLAP fails.

### notes (`src/mvh/stages/notes/`: `__init__.py`, `bp.py`, `post.py`, `midi.py`)
- basic-pitch (nmp.onnx via onnxruntime, arrays in) on bass, guitar, other with per-source presets (bass monophonic,
  27-420 Hz). Post-processing: onsets snapped to the stem's own audio onsets, re-triggered fragments merged, monophonic
  bass, notes masked by `stem.<src>.active`.
- piano: piano_transcription_inference (ByteDance CRNN) ONLY when the piano stem is active >= 10 % AND CED reports piano
  over its active windows (I-M3b-8). An active piano stem without piano tags goes to basic-pitch (fallback
  `piano:basic_pitch`, status degraded, warning). An inactive or silent stem gets no notes (W0: 378 invented notes on
  MEGAFAUNA; now 0 on every real song).
- `vel` from the stem level at the onset (per-source normalised) blended with model amplitude; `conf` = model evidence.
- `notes/notes.mid` (tracks: tempo map, bass, piano, guitar, other), `notes/<src>.mid` for sources with notes,
  `events/notes.<src>.json`, `notes/notes.json` (count, range, density, pitch-class histogram, file index, tempo-map
  description). Tempo map: every beat on a quarter-note boundary, one set_tempo per beat-interval change, time signatures
  from bars (I-M3b-7). Vocal notes are the vocals stage's (D6/D39).
- Human correction: `--param notes.piano_mode="auto"|"crnn"|"basic_pitch"|"off"`.

### vocals (`src/mvh/stages/vocals/`: `__init__.py`, `pitch.py`)
- RMVPE (ONNX) on lead_vocals is the arbiter, voiced when conf >= 0.3; SwiftF0 is the second opinion that scales
  `vocal.conf` (agree / octave / other) and is never used for presence.
- Presence gate: RMVPE voiced AND lead stem active AND level > max(-55 dBFS, p99 - 35 dB) AND `inst.voice` >= 0.35.
  Octave islands folded, < 50 ms islands dropped.
- Curves (100 Hz): `vocal.f0_hz`, `vocal.midi` (NaN unvoiced), `vocal.voiced`, `vocal.conf`, `vocal.pitch01` (p2..p98 of
  voiced frames, held through gaps with a 150 ms linear ease, never NaN; norm lo/hi in the index meta).
- `meta/vocal_range.json`: present, voiced_s, p2/p10/median/p90/p98, span, lowest/highest SUSTAINED notes (>= 0.3 s in
  notes >= 0.15 s) with times, register (CED male/female share on sung frames + median pitch, low confidence), conf, plus
  additive `basis`, `spoken_pitch`, `style`. Rap/speech-dominant leads: statistics only over sung frames, null when
  < 8 s (docs/SPIKE.md: no f0 range logic on rap); spoken pitch reported separately.
- `events/notes.vocals.json`, `notes/vocals.mid` (beat-grid tempo map), `events/vocal_phrases.json` (VPnnn, rests
  < 0.45 s joined).
- Human correction: `--param vocals.present=true|false`, `--param vocals.style="singing"|"speech"|"rap"`.
- Lyrics coverage is not combined into presence: lyrics is not a dep of vocals (CR-M3b-1).

## Measured accuracy vs thresholds (synthetic ground truth; asserted in tests/unit)

| Check | Threshold | Measured |
|---|---|---|
| Bass monophonic note F1 (stage on synth song, onset 50 ms) | >= 0.8 (PLAN §7) | 0.907 |
| Bass note F1 on the BASS_LINE primitive | >= 0.8 | 0.903 |
| Piano note F1 (basic-pitch path on synth) | >= 0.8 | 0.985 (CRNN forced: 0.977) |
| Guitar on a digitally silent stem | 0 notes | 0 |
| "other" pad notes in key | >= 90 % | pass |
| Vocal p2 / p98 vs truth | +-1 semitone | within 0.22 st |
| Vocal lowest / highest sustained note | +-1 semitone | G3 / A4 exact |
| Vibrato sines range (primitive) | +-1 semitone | pass |
| Raw pitch accuracy (50 cents) / voicing recall and precision | >= 0.95 / >= 0.85 | 0.996 / pass |
| Vocal note F1 on synth | >= 0.75 | pass |
| pitch01 eased through gaps (no jump > 0.5) | asserted | pass |
| instruments: drums / bass / voice segment overlap with truth | > 0.9 / 0.85 / 0.8 | pass; no voice before 9 s or after the duet; no guitar on the silent stem |
| CED output is a probability, silent windows 0 | asserted | pass |
| vstyle.* sum <= inst.voice | asserted | pass |

## Real songs (upstream from the tests/contract/real-<slug> overlays; direct harness inside a heavy slot)

Timings are wall-clock with up to 7 other agents competing for the two heavy slots (3 threads):

| Song | instruments | notes | vocals |
|---|---|---|---|
| synth | 50 s | 10 s | 4 s |
| jeremy | 148 s | 16 s | 19 s |
| newton-vs-nye | 89 s (788 s under heavy contention) | 8 s | 4 s |
| megafauna | 102 s | 12 s | 4 s |
| versatile | 93 s | 10 s | 4 s |

Observations (coverage = fraction of the song in segments):
- **Jeremy (grunge, sung):** guitar 1.00, bass 0.91, distorted_guitar 0.90, drums 0.88, voice 0.81; piano 0 (silent piano
  stem: 0 notes, CRNN not run). Style singing (0.72). Vocal present, 192 s voiced; p2/p98 MIDI 53.2/70.6 (W0 RMVPE
  53.6-73.8; W0 conservative SwiftF0 p2-p98 G3-G#4 = 55.3-68.0); tessitura p10/p90 A3-A4; sustained lowest/highest E3/C#5
  (held >= 0.3 s; includes some backing-harmony bleed in the lead stem); register tenor/baritone border (reported tenor,
  conf 0.87 for the range, register itself is a low-confidence cue). 584 vocal notes, 42 phrases. Notes: bass 1073
  (MIDI 29-61), guitar 2663, other 88.
- **Newton vs Nye (rap battle):** drums, drum_machine, voice 0.80, bass, synth. Style rap (share 1.0). Vocal present
  (71 s voiced) but sung-range statistics are null (rap), spoken pitch reported. Bass 361 notes, other 470, piano 0.
- **MEGAFAUNA (electronic, vocals stem = synth leads):** voice coverage 0.03 (only a 7 s tagger segment); warning that the
  vocals stem is active for ~87 s without vocal tags; vocal present false, 0 voiced s after the voice gate. Piano 0 notes
  (W0 CRNN invented 378). Bass 71, guitar 370, other 1057.
- **Versatile (near-instrumental):** bass 0.84, drums, synth, drum_machine; voice 0.17 (vocal chops, tagger only);
  vocal present false (1.5 s voiced). Bass 258 notes, other 1032.

Real-song snapshot tests (`tests/unit/vocals/test_m3b_real.py`, opt-in `MVH_REAL=1`, tolerances) encode these.

## Decisions
Recorded in `docs/contract/decisions/M3b.md` (I-M3b-1..12): open instrument vocabulary, fusion rule, 1 Hz window
semantics, CLAP curves relative, vocal-style shares, notes conf/vel, MIDI tempo map, piano gate, vocal presence and
range rules, pitch01 ease, vocal phrases, human-correction params. Additive fields: `meta/vocal_range.json`
`basis`/`spoken_pitch`/`style`, `meta/instruments.json.top_tags`, CLAP index descriptions.

## Change requests
- CR-M3b-1: vocals should read lyrics coverage (optional dep or combine downstream).
- CR-M3b-2: notes <- instruments dep (read `inst.piano`) to drop the extra CED pass in the piano gate.
- CR-M3b-3: promote `notes.piano_mode`, `vocals.present`, `vocals.style`, `instruments.vocabulary` to overrides.json keys.
- CR-M3b-4: fold the additive fields into catalog.py.

## Open issues
- `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` asserts that `mvh.stages.rhythm.run` is a stub;
  M2 replaced it, so the contract unit folder fails in every module gate (not M3b code; W3 integrator / contract owner).
- The real-song fixtures lack stem_activity, instruments and spectral outputs; tests/synth/m3b/stem_overlay.py builds an
  overlay with a reference stem_activity, so real-song numbers depend on that reference until M3a's stage runs upstream.
- Register (male/female, baritone/tenor) is a weak cue; Jeremy sits on the baritone/tenor border.
- Jeremy's sustained extremes (E3/C#5) are wider than W0's conservative SwiftF0 p2-p98 (G3-G#4) because the lead stem
  carries some harmony bleed; p10/p90 (A3-A4) is the better "tessitura" for agents.
- vocal style on sung verses: CED tags low sung verses as speech (Jeremy 28 % speech); statistics use all voiced frames
  for singing-dominant leads so this does not shrink the range.

## Tests and gate

- `uv run --frozen --no-sync python -m pytest -q tests/unit/{notes,vocals,instruments}`: notes 11 passed, vocals 14 passed
  + 4 skipped (real-song tests, opt-in), instruments 13 passed. Includes `tests/unit/vocals/test_m3b_hooks.py`
  (human-correction params). The synthetic run of the three stages is cached under `tests/.cache/m3b/synth-<hash>` keyed
  on the stage sources, so the three gate pytest processes share one inference run.
- `scripts\gate.ps1 M3b` (log: `out/_wip/builder-m3b/logs/gate1.log`): fixture PASS, unit FAIL (only
  `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs`, which asserts `mvh.stages.rhythm` is still a stub;
  notes=0 vocals=0 instruments=0), review SKIP (no M3b review folder yet), ruff PASS, contract PASS, validate PASS,
  e2e PASS (567 s, real M3b stages inside the full pipeline), lib-node PASS, determinism PASS (1000 s; two analyze --force
  runs byte-identical apart from run.json/.cache). Every M3b-owned check passes; the single failure is a stale W1 test
  outside the M3b paths (open issue 1).
- Real-song snapshot tests: `MVH_REAL=1 ... pytest -q tests/unit/vocals/test_m3b_real.py`: 4 passed in 537 s (Jeremy,
  Newton vs Nye, MEGAFAUNA, Versatile; log `out/_wip/builder-m3b/logs/real1.log`).
