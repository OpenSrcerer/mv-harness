# mv-harness output contract (v1.0.0-rc.1)

The single source of truth for everything a song folder `out/<slug>/` contains and how to read it. Module builders code
against it; video agents read it (it is copied to `skill/mv-harness/references/CONTRACT.md`).

- **Machine sources.** Tables marked *generated* come from `src/mvh/contract/catalog.py` (files, events, fields, Consumed-by) and
  `src/mvh/contract/registry.py` (curve channels). Run `python -m mvh.contract.gen` after editing them; `--check` fails when this
  file or `src/mvh/contract/schema/**` is stale. The time/frame/helper semantics are defined **in code** by
  `src/mvh/contract/conventions.py`; the golden vectors in [contract/golden-vectors.json](contract/golden-vectors.json)
  ([readable spec](contract/golden-spec.md)) are computed from it.
- **Interfaces.** Stage declarations and the stage interface: `src/mvh/runner/spec.py`. IDs: `src/mvh/contract/ids.py`.
- **Frozen at v1** (PLAN §4.6): the envelope schemas (manifest, curves index, event-file envelope, provenance), the time and unit
  conventions, the IDs, and every field marked *frozen* below (which includes every field in the Consumed-by matrix). See §13 for what
  needs a change request.

Contents: 1 Layout · 2 Time and frames · 3 IDs and links · 4 Values · 5 Curves · 6 Events · 7 Other files and tables ·
8 File catalogue · 9 Helpers · 10 Stage interface · 11 Consumed-by matrix · 12 brief.md · 13 Change control · 14 Decisions

---

## 1. Layout

```
out/<slug>/                          slug: ^[a-z0-9][a-z0-9-]{0,63}$ (megafauna, versatile, jeremy, newton-vs-nye)
  manifest.json      index only: schema_version, source, timebase, status, summary scalars, files[]; no data arrays; <= 3k tokens
  brief.md           LLM entry point, <= 4k tokens (target 2.5k); `mvh brief --section S05` zooms (<= 1.5k tokens)
  viewer.html        read-only from file:// (preview data inlined); edit mode under `mvh view`
  run.json           volatile: timings, host, device, versions, licences, fallbacks (never diffed)
  overrides.json     user corrections (viewer or by hand)
  audio/mix.flac     THE soundtrack and timebase (24-bit); audio/mix.wav (float) also when |x| > 1; audio/preview.opus
  stems/<stem>.flac  vocals lead_vocals backing_vocals drums bass guitar piano other instrumental; stems/drums/<sub>.flac
                     (kick snare toms hihat ride crash, optional). Sample-aligned with the mix, same length.
  curves/index.json  channel registry with byte offsets          curves/core.f32 stems.f32 vocal.f32 chroma12.f32 (100 Hz)
  curves/spectrum128.u8  [frames x 128] row-major               curves/instruments_1hz.f32 mood_1hz.f32 (1 Hz)
  events/<name>.json event-file envelope (section 6)
  meta/<topic>.json  per-stage scalar documents (source, identity, separation, stems, loudness, tempo, key, structure,
                     instruments, vocal_range, mood, voices, grooves)
  tables/beats.csv bars.csv sections.csv                          derived, same IDs as the events
  notes/notes.json notes.mid <src>.mid vocals.mid
  lyrics/lyrics.json (canonical) lines.tsv lyrics.lrc .vtt .srt .ass
  lipsync/visemes.json phonemes.json                              (event envelopes; Should)
  meaning/interview.md intent.md(user) authored.json(agent draft) request.md input.json schema.json meaning.json meaning.md orphans.json
  artwork/cover.jpg                                               (palette in meta/source.json and the manifest)
  frames/<fps>fps.csv                                             on demand (`mvh frames`)
  lib/mvh.js lib/mvh_load.py lib/mvh.glsl schema/**.schema.json   copied in: the folder works without mvh installed
```

**Who writes what.** Each stage writes only its declared outputs, through `ctx.writer` (section 10). Outputs marked *cache only*
(`public=False`: the canonical WAV, separate_fast stems, allin1 activations) stay in `out/<slug>/.cache/<stage>/<key>/` and are read
by downstream stages through `ctx.upstream(...)`. The runner's **finalize** step (no stage) writes `manifest.json`, `run.json`,
`curves/index.json` and the packed `curves/*` files (from the channels every stage handed to `ctx.writer.curves`), and copies
`lib/` and `schema/`. The user (or the viewer) writes `overrides.json`, `meaning/intent.md`; an agent or LLM writes
`meaning/authored.json`. `mvh analyze` never overwrites those three.

**Privacy (NF5).** Lyric text lives only in `lyrics/*` and `lines.tsv` (and quotes of <= 10 words in brief.md / meaning). It never goes
into logs, reports, run.json, provenance, manifest or error messages.

---

## 2. Time and frames

Reference: `conventions.py` (`time_of`, `frame_centre`, `frame_window`, `frame_of`, `frame_count`, `samples_in_frame`, `curve_frame`).

1. **One clock.** Every time is in seconds from the first sample of `audio/mix.flac` (= `manifest.timebase.soundtrack`). Video agents use
   `mix.flac` or the stems as the soundtrack, never the original file. Stems have the same length and sample alignment as the mix.
2. **Curve samples.** Sample *i* of a curve at `rate` Hz is **centred** at `i / rate` s. Every channel of a file has
   `n = ceil(n_samples * rate / sample_rate)` samples (integer arithmetic), so samples cover [0, duration).
3. **Frame rule** `fr = {fps, frame0 = 0, early = false}`; `fps` is a number or `[num, den]` (numbers are literal: give NTSC as
   `[24000, 1001]`; 23.976 differs by < 0.01 frame over 5 minutes). With F = num/den and half = 0.5·den/num:
   - `time_of(n) = (n - frame0) * den / num` - the frame's nominal time t_n;
   - **centred** (default): window [t_n - half, t_n + half), sampling instant t_n;
   - **early**: window [t_n, t_n + 2·half), sampling instant t_n + half (all three rules shift together);
   - `frame_of(t) = floor(t * num / den + (early ? 0 : 0.5) + 1e-9) + frame0`;
   - `frame_count(duration) = ceil(duration * num / den - 1e-9)` (frames frame0 .. frame0+count-1, i.e. t_n < duration).
4. **One membership rule.** An event at t belongs to frame `frame_of(t)`; curve sample i belongs to frame `frame_of(i / rate)`.
   So a curve flash and its event land on the **same** frame (see the flash rule in section 4).
5. **Resample policies** (per channel, in the registry): `linear` = lerp at the sampling instant; `hold` = the nearest sample
   (`floor(x + 0.5 + 1e-9)`, x = t·rate); `mean` / `max` = mean / max of the samples that belong to the frame (if none, which only happens
   above 100 fps: lerp at the instant). `curve.at(t)` is lerp for linear/mean/max and nearest for hold. Indices clamp to [0, n-1].
   NaN-aware pitch channels: see section 4.

**Worked examples** (all in the golden vectors):

| Case | Result |
|---|---|
| 24 fps, frame0 0, centred: `frame_of(1.0)` | floor(24 + 0.5) = **24**; window of frame 24 = [0.979167, 1.020833) |
| same, `frame_of(0.0208)` / `frame_of(0.02086)` | 0 / 1 (the boundary is 1/48 = 0.0208333 s) |
| 24 fps, **early**: `frame_of(1.0)`, `frame_of(0.02086)` | 24 (window [1.0, 1.041667)), 0 |
| 23.976 fps, centred: `frame_of(1.0)`; early | floor(23.976 + 0.5) = 24; floor(23.976) = **23** |
| [24000, 1001], frame0 1 (Blender): `time_of(25)` | (25 - 1) · 1001 / 24000 = 1.001 s |
| 25 fps: `frame_of(0.0208)` | floor(0.52 + 0.5) = 1 (frame 0 window is [-0.02, 0.02)) |
| `frame_count(316.587)` at 24 / 23.976 / 30 fps | 7599 / 7591 / 9498 |
| 24 fps frame 0, `mean` of a 100 Hz curve | samples 0, 1, 2 (0.00, 0.01, 0.02 < 0.020833) |
| 60 fps frame 1 (window [0.008333, 0.025)) | samples 1 and 2 |

---

## 3. IDs and links

Reference: `ids.py` (regexes `ID_KINDS`, `make_id`, `parse_id`, `kind_of`, `word_id`, `ref_key`). Numbered IDs are 1-based, zero-padded
to the width shown, may grow (`S100`), and are assigned in time order (voices, characters and motifs: order of first appearance).

| Entity | ID | Defined in | Required links |
|---|---|---|---|
| Section | `S01` | `events/sections.json` (**canonical**) | label, occurrence, occurrence_label (`chorus#2`), repeat_group (`A`, `B`, ... `AA`) |
| Phrase | `P01` | `events/phrases.json` | start_bar, n_bars, section_id |
| Bar / beat | bar int (1-based, **0 = pickup**); beat_in_bar 1..N; beat_index 0-based (= position in beats.json) | `events/bars.json`, `events/beats.json` | bars.csv carries section_id, phrase_id, groove_id |
| Eight-count | `E001`; `E000` = synthesised 5-6-7-8 lead-in | `events/counts.json` | phrase_id, section_id, len (8, 6 in 3/4; shorter when partial) |
| Groove | `G01` | `meta/grooves.json`, per bar in `events/grooves.json` | bars |
| Lyric line | `L001` (sung order) | `lyrics/lyrics.json` | section_id, text_group (`T01`), repeat_group (`LG01`); singer (character) and voice_id via `events/singing.json` / `lines.tsv` |
| Word | `L001.03` (k 1-based in the line) | `lyrics/lyrics.json` | line_id, conf |
| Voice | `V1` | `meta/voices.json` | proposed_character_id; spans in `events/voice_spans.json` |
| Character | `C1` | `meaning/meaning.json` | voice_ids, lead_backing, line_ids, section_ids |
| Motif | `M1` | `meaning/meaning.json` | occurrences (times, line ids) |
| Cue | `Q0001` | `events/cues.json` | tier, source `{file, id}` |
| EDM role | `R01` | `events/edm_roles.json` | role, section_id |
| Hit point / hold | `H001` / `O001` | `events/hit_points.json` / `events/holds.json` | sources / source |
| Impact / stop / silence / decay tail | `I001` / `X001` / `Z001` / `Y001` | `events/impacts.json` ... | - |
| Vocal phrase | `VP001` | `events/vocal_phrases.json` | - |

**Reference keys** for items without an ID: `beat:<beat_index>` and `bar:<bar>` (e.g. tier-4 cues: `source = {file: "events/beats.json", id: "beat:12"}`).
**Links point downstream-to-upstream only**: an item cites what it came from (`source`, `sources`, `section_id`, ...). Reverse lookups
(e.g. "which cue came from impact I003") are done by the helpers, never stored upstream (Decision D4).

---

## 4. Values

- **Absolute twins.** Every 0..1 curve derived from a physical quantity has a physical twin (`bands.bass` <-> `bands.bass_db`,
  `loud.short_term` <-> `loud.short_term_lufs`, `vocal.pitch01` <-> `vocal.midi`). Per-song normalisation is p02-p99.5 of the twin;
  `curves/index.json` records `norm {method, of, lo, hi}`. Composites (`dyn.intensity`, `choreo.movement`, `choreo.accent`, hit
  envelopes, mood) are documented as unitless (`norm.method = composite | model`).
- **Floors, not infinities.** dB channels are floored at -120 dBFS, LUFS channels at -70 LUFS (`special.floor`). No channel holds inf.
- **Unvoiced pitch.** `vocal.f0_hz` and `vocal.midi` are **NaN where unvoiced** (`special.nan = "unvoiced"`); `vocal.voiced[i] ==
  isfinite(vocal.midi[i])`. NaN-aware sampling (`conventions.nan_aware_at`): both neighbours voiced -> lerp; else the nearest sample if
  voiced; else hold the last voiced value (else the first voiced after); `mean`/`max` frames use voiced samples only. Helpers and the
  frames export never return NaN (0 when the song has no voiced frame). `vocal.pitch01` = (midi - p2)/(p98 - p2), held through gaps with
  a 150 ms ease, never NaN. `vocal.voiced` is 0/1 with policy `max`.
- **Flash rule** (writers of event-driven `max` channels: `hits.*`, `drums.*`, `choreo.accent`, `vocal.mouth_open*`): the envelope holds
  its peak at both `floor(t·100)` and `ceil(t·100)` (`conventions.flash_samples`), so the max-pooled value of the event's frame equals
  the peak at every fps <= 100.
- **Off-grid rhythm.** `events/beats.json` covers the whole song: in no-pulse regions rhythm writes **virtual beats** at the neighbouring
  tempo with `in_pulse: false`. Before the first and after the last beat the helpers extend the grid with the first/last inter-beat
  interval and report `in_pulse: false`.
- **Confidence** fields are 0..1. **Velocities** in events are 0..1 (MIDI files use 1..127).
- **Writing.** JSON: UTF-8, `ensure_ascii=False`, LF, `allow_nan=False` (NaN -> null), times rounded to 6 decimals; event items sorted by
  t (ties keep producer order). CSV/TSV: UTF-8 without BOM, LF, header row, empty cell = null, booleans `0`/`1`, `lines.tsv` replaces tabs
  and newlines in text by spaces. No timestamps or host names outside run.json (NF1 determinism).
- **Pitch.** MIDI numbers with C4 = 60; note names like `A3`, sharps as `#`; pitch classes C = 0.

---

## 5. Curves

`curves/index.json` (schema `mvh/envelope/curves_index`) lists `files{id: {path, dtype, layout, rate_hz, n_frames, n_channels, quant?,
band_edges_hz?}}` and `channels[{id, file, offset_bytes, n, rate_hz, unit, range, norm, resample, special, twin, stage, description}]`.
`.f32` files are float32 LE **column-major**: channel j at `offset_bytes = 4·n·j` (`new Float32Array(buf, off, n)`; numpy
`np.fromfile(path, '<f4', count=n, offset=off)`). Channel order in a file = registry order, then id. `spectrum128.u8` is row-major
[n x 128]; `u8 / 255` is the viz band value (same as the R channel of viz `bandBytes`), `quant = {scale: 1/255, offset: 0}`.
Patterned ids are families: `stem.{stem}.*` for every stem in section 1 (drum sub-stems as `drums_kick` ...), `vocal.mouth_open.{voice}`
(written when there are >= 2 voices; `vocal.mouth_open` is always written as the max over voices), `inst.{label}`, `mood.tag.{tag}`.

**Channel registry** (*generated*):

<!-- BEGIN GENERATED: channels -->
| Channel id | File | Unit | Range | Resample | Norm / special | Twin | Stage | Description |
|---|---|---|---|---|---|---|---|---|
| `bands.bass` | core | 0..1 | 0..1 | mean | p02-p99.5 of `bands.bass_db` | `bands.bass_db` | spectral | bass band 32-150 Hz power (per-song 0..1) |
| `bands.bass_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `bands.bass` | spectral | bass band 32-150 Hz power (dBFS) |
| `bands.bass_viz` | core | 0..1 | 0..1 | mean | viz |  | spectral | viz-compatible bass level (mean of normalised log bands, as viz audio.bass) |
| `bands.mid` | core | 0..1 | 0..1 | mean | p02-p99.5 of `bands.mid_db` | `bands.mid_db` | spectral | mid band 150-2200 Hz power (per-song 0..1) |
| `bands.mid_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `bands.mid` | spectral | mid band 150-2200 Hz power (dBFS) |
| `bands.mid_viz` | core | 0..1 | 0..1 | mean | viz |  | spectral | viz-compatible mid level (mean of normalised log bands, as viz audio.mid) |
| `bands.high` | core | 0..1 | 0..1 | mean | p02-p99.5 of `bands.high_db` | `bands.high_db` | spectral | high band 2200-16000 Hz power (per-song 0..1) |
| `bands.high_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `bands.high` | spectral | high band 2200-16000 Hz power (dBFS) |
| `bands.high_viz` | core | 0..1 | 0..1 | mean | viz |  | spectral | viz-compatible high level (mean of normalised log bands, as viz audio.high) |
| `bands.level` | core | 0..1 | 0..1 | mean | viz |  | spectral | viz-compatible overall level (viz audio.level) |
| `bands.kick` | core | 0..1 | 0..1 | mean | p02-p99.5 of `bands.kick_db` | `bands.kick_db` | spectral | kick band 35-100 Hz power (per-song 0..1) |
| `bands.kick_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `bands.kick` | spectral | kick band 35-100 Hz power (dBFS) |
| `fine.sub` | core | 0..1 | 0..1 | mean | p02-p99.5 of `fine.sub_db` | `fine.sub_db` | spectral | fine band sub 20-60 Hz power (per-song 0..1) |
| `fine.sub_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `fine.sub` | spectral | fine band sub 20-60 Hz power (dBFS) |
| `fine.bass` | core | 0..1 | 0..1 | mean | p02-p99.5 of `fine.bass_db` | `fine.bass_db` | spectral | fine band bass 60-150 Hz power (per-song 0..1) |
| `fine.bass_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `fine.bass` | spectral | fine band bass 60-150 Hz power (dBFS) |
| `fine.lowmid` | core | 0..1 | 0..1 | mean | p02-p99.5 of `fine.lowmid_db` | `fine.lowmid_db` | spectral | fine band lowmid 150-500 Hz power (per-song 0..1) |
| `fine.lowmid_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `fine.lowmid` | spectral | fine band lowmid 150-500 Hz power (dBFS) |
| `fine.mid` | core | 0..1 | 0..1 | mean | p02-p99.5 of `fine.mid_db` | `fine.mid_db` | spectral | fine band mid 500-2000 Hz power (per-song 0..1) |
| `fine.mid_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `fine.mid` | spectral | fine band mid 500-2000 Hz power (dBFS) |
| `fine.highmid` | core | 0..1 | 0..1 | mean | p02-p99.5 of `fine.highmid_db` | `fine.highmid_db` | spectral | fine band highmid 2000-4000 Hz power (per-song 0..1) |
| `fine.highmid_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `fine.highmid` | spectral | fine band highmid 2000-4000 Hz power (dBFS) |
| `fine.presence` | core | 0..1 | 0..1 | mean | p02-p99.5 of `fine.presence_db` | `fine.presence_db` | spectral | fine band presence 4000-6000 Hz power (per-song 0..1) |
| `fine.presence_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `fine.presence` | spectral | fine band presence 4000-6000 Hz power (dBFS) |
| `fine.air` | core | 0..1 | 0..1 | mean | p02-p99.5 of `fine.air_db` | `fine.air_db` | spectral | fine band air 6000-16000 Hz power (per-song 0..1) |
| `fine.air_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `fine.air` | spectral | fine band air 6000-16000 Hz power (dBFS) |
| `hits.kick` | core | unitless | 0..1.5 | max | composite |  | spectral | kick hit envelope with 0.18 s release (viz audio.kick); a typical hit reads ~0.85 |
| `hits.kick_raw` | core | unitless | 0..1.5 | max | composite |  | spectral | kick hit envelope without release (viz audio.kickRaw) |
| `hits.mid` | core | unitless | 0..1.5 | max | composite |  | spectral | mid hit envelope with 0.18 s release (viz audio.midHit); a typical hit reads ~0.85 |
| `hits.mid_raw` | core | unitless | 0..1.5 | max | composite |  | spectral | mid hit envelope without release (viz audio.midHit raw) |
| `hits.high` | core | unitless | 0..1.5 | max | composite |  | spectral | high hit envelope with 0.18 s release (viz audio.highHit); a typical hit reads ~0.85 |
| `hits.high_raw` | core | unitless | 0..1.5 | max | composite |  | spectral | high hit envelope without release (viz audio.highHit raw) |
| `flux.bass` | core | 0..1 | 0..1 | max | p02-p99.5 |  | spectral | bass-band spectral flux (onset strength), per-song 0..1 |
| `flux.mid` | core | 0..1 | 0..1 | max | p02-p99.5 |  | spectral | mid-band spectral flux (onset strength), per-song 0..1 |
| `flux.high` | core | 0..1 | 0..1 | max | p02-p99.5 |  | spectral | high-band spectral flux (onset strength), per-song 0..1 |
| `timbre.centroid` | core | 0..1 | 0..1 | mean | p02-p99.5 of `timbre.centroid_hz` | `timbre.centroid_hz` | spectral | spectral centroid (per-song 0..1) |
| `timbre.centroid_hz` | core | Hz | 0..22050 | mean |  | `timbre.centroid` | spectral | spectral centroid (Hz) |
| `timbre.rolloff` | core | 0..1 | 0..1 | mean | p02-p99.5 of `timbre.rolloff_hz` | `timbre.rolloff_hz` | spectral | 85% spectral roll-off (per-song 0..1) |
| `timbre.rolloff_hz` | core | Hz | 0..22050 | mean |  | `timbre.rolloff` | spectral | 85% spectral roll-off (Hz) |
| `timbre.flatness` | core | 0..1 | 0..1 | mean |  |  | spectral | spectral flatness (Wiener entropy) |
| `timbre.slope_db_oct` | core | dB/oct | -30..10 | mean |  |  | spectral | spectral slope |
| `stereo.width` | core | 0..1 | 0..1 | mean |  |  | spectral | side/(mid+side) energy ratio |
| `stereo.balance` | core | -1..1 | -1..1 | mean |  |  | spectral | left(-1)/right(+1) energy balance |
| `stereo.correlation` | core | -1..1 | -1..1 | mean |  |  | spectral | inter-channel correlation |
| `loud.momentary` | core | 0..1 | 0..1 | mean | p02-p99.5 of `loud.momentary_lufs` | `loud.momentary_lufs` | loudness | momentary loudness (0.4 s, centred) (per-song 0..1) |
| `loud.momentary_lufs` | core | LUFS | -70..6 | mean | floor=-70.0 | `loud.momentary` | loudness | momentary loudness (0.4 s, centred) (LUFS) |
| `loud.short_term` | core | 0..1 | 0..1 | mean | p02-p99.5 of `loud.short_term_lufs` | `loud.short_term_lufs` | loudness | short-term loudness (3 s, centred) (per-song 0..1) |
| `loud.short_term_lufs` | core | LUFS | -70..6 | mean | floor=-70.0 | `loud.short_term` | loudness | short-term loudness (3 s, centred) (LUFS) |
| `loud.rms` | core | 0..1 | 0..1 | mean | p02-p99.5 of `loud.rms_db` | `loud.rms_db` | loudness | RMS level (46 ms centred window) (per-song 0..1) |
| `loud.rms_db` | core | dBFS | -120..6 | mean | floor=-120.0 | `loud.rms` | loudness | RMS level (46 ms centred window) (dBFS) |
| `loud.peak_db` | core | dBFS | -120..6 | max | floor=-120.0 |  | loudness | sample peak (46 ms centred window) |
| `loud.crest_db` | core | dB | 0..60 | mean |  |  | loudness | crest factor (peak - RMS) |
| `tempo.bpm` | core | BPM | 30..300 | linear |  |  | rhythm | local tempo from the beat grid |
| `rhythm.beat_act` | core | 0..1 | 0..1 | max | model |  | rhythm | beat activation (beat_this probability) |
| `rhythm.downbeat_act` | core | 0..1 | 0..1 | max | model |  | rhythm | downbeat activation |
| `rhythm.in_pulse` | core | 0/1 | 0..1 | hold |  |  | rhythm | 1 inside a pulse region |
| `dyn.intensity` | core | 0..1 | 0..1 | linear | composite |  | dynamics | intensity composite (short-term LU vs integrated, bass, onset density, brightness) |
| `dyn.novelty` | core | 0..1 | 0..1 | max | composite |  | dynamics | Foote novelty (section-change evidence) |
| `drums.kick` | core | 0..1 | 0..1 | max | composite |  | drums | kick hit envelope (velocity-scaled) |
| `drums.snare` | core | 0..1 | 0..1 | max | composite |  | drums | snare hit envelope (velocity-scaled) |
| `drums.hat` | core | 0..1 | 0..1 | max | composite |  | drums | hat hit envelope (velocity-scaled) |
| `drums.tom` | core | 0..1 | 0..1 | max | composite |  | drums | tom hit envelope (velocity-scaled) |
| `drums.cymbal` | core | 0..1 | 0..1 | max | composite |  | drums | cymbal hit envelope (velocity-scaled) |
| `drums.perc` | core | 0..1 | 0..1 | max | composite |  | drums | perc hit envelope (velocity-scaled) |
| `choreo.movement` | core | 0..1 | 0..1 | linear | composite |  | choreo | movement-density composite |
| `choreo.accent` | core | 0..1 | 0..1 | max | composite |  | choreo | count accent envelope (drum hits, onsets, vocal onsets) |
| `stem.{stem}.level` | stems | 0..1 | 0..1 | mean | p02-p99.5 of `stem.{stem}.rms_db` | `stem.{stem}.rms_db` | stem_activity | stem RMS level (per-song 0..1 over all stems) |
| `stem.{stem}.rms_db` | stems | dBFS | -120..6 | mean | floor=-120.0 | `stem.{stem}.level` | stem_activity | stem RMS (dBFS) |
| `stem.{stem}.rel_db` | stems | dB | -120..12 | mean | floor=-120.0 |  | stem_activity | stem level relative to the mix |
| `stem.{stem}.active` | stems | 0/1 | 0..1 | hold |  |  | stem_activity | 1 when the stem is active (> -45 dBFS and within 18 dB of the mix, 300/500 ms hysteresis) |
| `vocal.f0_hz` | vocal | Hz | 30..2000 | linear | nan=unvoiced | `vocal.midi` | vocals | lead-vocal f0; NaN where unvoiced |
| `vocal.midi` | vocal | MIDI | 20..100 | linear | nan=unvoiced | `vocal.pitch01` | vocals | lead-vocal pitch (fractional MIDI); NaN where unvoiced |
| `vocal.pitch01` | vocal | 0..1 | 0..1 | linear | p02-p98 of `vocal.midi` | `vocal.midi` | vocals | (midi - p2) / (p98 - p2), held through gaps with a 150 ms ease; never NaN |
| `vocal.voiced` | vocal | 0/1 | 0..1 | max |  |  | vocals | 1 where the lead vocal is voiced (== isfinite(vocal.midi)) |
| `vocal.conf` | vocal | 0..1 | 0..1 | mean | model |  | vocals | pitch confidence |
| `vocal.mouth_open` | vocal | 0..1 | 0..1 | max | composite |  | lipsync | mouth opening: vocal envelope (10 ms attack, 60 ms release) gated by aligned words; max over voices |
| `vocal.mouth_open.{voice}` | vocal | 0..1 | 0..1 | max | composite |  | lipsync | mouth opening of one voice (written when there are >= 2 voices) |
| `chroma.0` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 0 (C=0), max-normalised per frame |
| `chroma.1` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 1 (C=0), max-normalised per frame |
| `chroma.2` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 2 (C=0), max-normalised per frame |
| `chroma.3` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 3 (C=0), max-normalised per frame |
| `chroma.4` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 4 (C=0), max-normalised per frame |
| `chroma.5` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 5 (C=0), max-normalised per frame |
| `chroma.6` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 6 (C=0), max-normalised per frame |
| `chroma.7` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 7 (C=0), max-normalised per frame |
| `chroma.8` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 8 (C=0), max-normalised per frame |
| `chroma.9` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 9 (C=0), max-normalised per frame |
| `chroma.10` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 10 (C=0), max-normalised per frame |
| `chroma.11` | chroma12 | 0..1 | 0..1 | mean |  |  | harmony | chroma of pitch class 11 (C=0), max-normalised per frame |
| `inst.{label}` | instruments_1hz | 0..1 | 0..1 | linear | model |  | instruments | instrument presence probability (fused CED/CLAP/stem activity), 4 s window, 1 s hop |
| `vstyle.singing` | instruments_1hz | 0..1 | 0..1 | linear | model |  | instruments | lead-vocal style probability: singing |
| `vstyle.speech` | instruments_1hz | 0..1 | 0..1 | linear | model |  | instruments | lead-vocal style probability: speech |
| `vstyle.rap` | instruments_1hz | 0..1 | 0..1 | linear | model |  | instruments | lead-vocal style probability: rap |
| `mood.valence` | mood_1hz | 0..1 | 0..1 | linear | model |  | mood | audio valence (0.5 neutral); lower confidence than arousal |
| `mood.arousal` | mood_1hz | 0..1 | 0..1 | linear | model |  | mood | audio arousal (0.5 neutral) |
| `mood.tag.{tag}` | mood_1hz | 0..1 | 0..1 | linear | model |  | mood | MTG-Jamendo mood/theme tag probability |
| `spectrum128` | spectrum128 | 0..1 | 0..1 | hold | viz |  | spectral | 128 log bands 32 Hz-16 kHz, viz mapping (2.6 dB/oct tilt, -88..-18 dB, soft knee, per-song gain); u8 = round(255 * value) |
<!-- END GENERATED: channels -->

**vizState(t, fr) mapping** (so `viz/` scenes run offline unchanged): `bass/mid/high` <- `bands.{b}_viz`; `level` <- `bands.level`;
`kick`, `kickRaw`, `midHit`, `highHit` <- `hits.kick`, `hits.kick_raw`, `hits.mid`, `hits.high`; `beat`, `beatPulse`, `onset`,
`beatCount` <- events `onsets.bass` (onset = an item in the current frame; pulses decay as in viz `audio.js`); `midPulse/midOnset`,
`highPulse/highOnset` <- `onsets.mid`, `onsets.high`; `bpm` <- `tempo.bpm`; `bandBytes` <- RGBA from `spectrumAt(t)` (R = G = B = value,
A = 255); `waveBytes` <- 128 (flat; not stored). The decay constants are taken from `viz/js/audio.js` by the lib builder and recorded in
the lib's golden addendum.

---

## 6. Events

Every `events/<name>.json` (and `lipsync/visemes.json`, `lipsync/phonemes.json`) uses the **event-file envelope**
(`mvh/envelope/events`):

```json
{"schema": "mvh/events/beats", "schema_version": "1.0.0-rc.1", "name": "beats", "kind": "event",
 "fields": {"t": {"unit": "s", "type": "number"}, ...}, "provenance": {...},
 "items": [ {"beat_index": 0, "t": 0.25, ...}, ... ]}
```

- `kind: event` items have `t` (and optionally `d`, e.g. notes); `kind: segment` items always have `t` and `d > 0`; membership is
  half-open [t, t + d).
- `fields` documents every field present (unit, type); producers may add optional fields (documented there).
- `provenance` (`mvh/envelope/provenance`) is deterministic: stage, stage_version, contract_version, cache key, params, models
  (id, licence, revision), tools, device, upstream keys, overrides_applied, fallbacks, notes. No timestamps.
- Names are dotted (`notes.bass`, `hits.kick`); the loaders map a name to its file through `manifest.files[]` (`events` field when the
  path is not `events/<name>.json`).

**Events catalogue** (*generated*; "Frozen = yes" fields are required in every item):

<!-- BEGIN GENERATED: events -->
#### `hits.kick` - event, by **spectral**
`events/hits.kick.json` · schema `mvh/events/hits.kick` · kick hit events from the viz hit envelope (refined on a 2.5 ms envelope)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `t_peak` | number | s | yes | time of the envelope peak |
| `strength` | number | 0..1+ | yes | 1 ~ a typical hit |
| `db` | number | dBFS | yes | band level at the peak |

#### `hits.mid` - event, by **spectral**
`events/hits.mid.json` · schema `mvh/events/hits.mid` · mid hit events from the viz hit envelope (refined on a 2.5 ms envelope)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `t_peak` | number | s | yes | time of the envelope peak |
| `strength` | number | 0..1+ | yes | 1 ~ a typical hit |
| `db` | number | dBFS | yes | band level at the peak |

#### `hits.high` - event, by **spectral**
`events/hits.high.json` · schema `mvh/events/hits.high` · high hit events from the viz hit envelope (refined on a 2.5 ms envelope)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `t_peak` | number | s | yes | time of the envelope peak |
| `strength` | number | 0..1+ | yes | 1 ~ a typical hit |
| `db` | number | dBFS | yes | band level at the peak |

#### `onsets.bass` - event, by **spectral**
`events/onsets.bass.json` · schema `mvh/events/onsets.bass` · bass-band flux onsets (centred threshold)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `strength` | number | 0..1 | yes |  |

#### `onsets.mid` - event, by **spectral**
`events/onsets.mid.json` · schema `mvh/events/onsets.mid` · mid-band flux onsets (centred threshold)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `strength` | number | 0..1 | yes |  |

#### `onsets.high` - event, by **spectral**
`events/onsets.high.json` · schema `mvh/events/onsets.high` · high-band flux onsets (centred threshold)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `strength` | number | 0..1 | yes |  |

#### `beats` - event, by **rhythm**
`events/beats.json` · schema `mvh/events/beats` · the beat grid: every beat, virtual beats (in_pulse false) continue through no-pulse regions

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `beat_index` | integer |  | yes | 0-based; equals the item's position |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `bar` | integer |  | yes | 1-based bar; 0 = pickup bar |
| `beat_in_bar` | integer |  | yes | 1..beats_in_bar |
| `beats_in_bar` | integer |  | yes | nominal beats in this beat's bar |
| `in_pulse` | boolean |  | yes | false for virtual-grid beats in no-pulse regions |
| `strength` | number | 0..1 | yes | tracker activation at the beat |
| `conf` | number | 0..1 | yes |  |

#### `bars` - segment, by **rhythm**
`events/bars.json` · schema `mvh/events/bars` · bars (downbeat to downbeat); section/phrase/groove links are in tables/bars.csv

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `bar` | integer |  | yes | 1-based; 0 = pickup |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `beats_in_bar` | integer |  | yes | nominal (meter numerator) |
| `n_beats` | integer |  | yes | beats actually in this bar |
| `first_beat` | integer |  | yes | beat_index of the bar's first beat |
| `pickup` | boolean |  | yes |  |
| `in_pulse` | boolean |  | yes |  |
| `conf` | number | 0..1 | yes |  |

#### `tempo_segments` - segment, by **rhythm**
`events/tempo_segments.json` · schema `mvh/events/tempo_segments` · piecewise tempo grid

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `bpm` | number | BPM | yes |  |
| `stable` | boolean |  | yes |  |

#### `pulse_regions` - segment, by **rhythm**
`events/pulse_regions.json` · schema `mvh/events/pulse_regions` · regions with / without a perceptible beat, covering the whole song

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `in_pulse` | boolean |  | yes |  |

#### `key` - segment, by **harmony**
`events/key.json` · schema `mvh/events/key` · key regions (one item when the key never changes)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `key` | string |  | yes | e.g. 'A minor' |
| `tonic_pc` | integer |  | yes | pitch class, C = 0 |
| `mode` | string |  | yes | one of major, minor |
| `conf` | number | 0..1 | yes |  |
| `agree` | boolean |  | yes | methods agree |

#### `chords` - segment, by **harmony**
`events/chords.json` · schema `mvh/events/chords` · chord timeline snapped to beats

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `label` | string |  | yes | Harte-style label, e.g. 'A:min', 'N' for no chord |
| `root_pc` | integer|null |  | yes | pitch class, C = 0 |
| `quality` | string |  | yes | maj, min, 7, maj7, min7, dim, aug, sus2, sus4, N, ... |
| `bass_pc` | integer|null |  | yes | pitch class, C = 0 |
| `conf` | number | 0..1 | yes |  |
| `beat_index` | integer|null |  | yes | beat the chord starts on |

#### `dynamics` - segment, by **dynamics**
`events/dynamics.json` · schema `mvh/events/dynamics` · loud and quiet parts, boundaries snapped to downbeats

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `level` | string |  | yes | one of silence, quiet, soft, medium, loud, peak |
| `rel_lu` | number | LU | yes | mean short-term loudness relative to integrated |
| `mean_lufs` | number | LUFS | yes |  |
| `conf` | number | 0..1 | yes |  |

#### `impacts` - event, by **dynamics**
`events/impacts.json` · schema `mvh/events/impacts` · ids `impact` · sudden energy increases

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Dynamics impact id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `strength` | number | 0..1 | yes |  |
| `delta_lu` | number | LU | yes |  |
| `delta_bass_db` | number | dB | yes |  |
| `bar` | integer|null |  | yes |  |

#### `stops` - event, by **dynamics**
`events/stops.json` · schema `mvh/events/stops` · ids `stop` · sudden cuts to (near) silence

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Dynamics stop (sudden cut) id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `strength` | number | 0..1 | yes |  |
| `gap_s` | number | s | yes |  |

#### `silences` - segment, by **dynamics**
`events/silences.json` · schema `mvh/events/silences` · ids `silence` · silent stretches

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Dynamics silence id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `depth_db` | number | dB | yes | below integrated loudness |

#### `decay_tails` - segment, by **dynamics**
`events/decay_tails.json` · schema `mvh/events/decay_tails` · ids `decay_tail` · ringing-out tails after hits or section ends

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Dynamics decay tail id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `strength` | number | 0..1 | yes |  |

#### `sections` - segment, by **structure**
`events/sections.json` · schema `mvh/events/sections` · ids `section` · CANONICAL sections; boundaries on downbeats; segments shorter than 2 bars are merged

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Section id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `label` | string |  | yes | intro, verse, pre-chorus, chorus, bridge, inst, solo, break, outro, silence (open vocabulary) |
| `occurrence` | integer |  | yes | 1-based count of this label so far |
| `occurrence_label` | string |  | yes | label#occurrence, e.g. chorus#2 |
| `repeat_group` | string |  | yes | Section repeat group (A, B, ..., Z, AA, AB, ...) id |
| `start_bar` | integer |  | yes |  |
| `n_bars` | integer |  | yes |  |
| `label_probs` | object |  | yes | label -> probability |
| `conf` | number | 0..1 | yes |  |
| `boundary_conf` | number | 0..1 | yes |  |

#### `phrases` - segment, by **structure**
`events/phrases.json` · schema `mvh/events/phrases` · ids `phrase` · 4/8/16-bar phrases aligned to section starts

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Phrase (4/8/16 bars) id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `start_bar` | integer |  | yes |  |
| `n_bars` | integer |  | yes |  |
| `section_id` | string |  | yes | Section id |

#### `edm_roles` - segment, by **structure**
`events/edm_roles.json` · schema `mvh/events/edm_roles` · ids `edm_role` · THE definition of builds, drops and breakdowns (snapped to downbeats)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | EDM-role segment (build, drop, breakdown) id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `role` | string |  | yes | one of build, drop, breakdown |
| `start_bar` | integer |  | yes |  |
| `n_bars` | integer |  | yes |  |
| `section_id` | string |  | yes | Section id |
| `conf` | number | 0..1 | yes |  |
| `evidence` | string[] |  | no |  |

#### `stem_activity` - segment, by **stem_activity**
`events/stem_activity.json` · schema `mvh/events/stem_activity` · active segments per stem

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `stem` | string |  | yes | one of vocals, lead_vocals, backing_vocals, drums, bass, guitar, piano, other, instrumental, drums_kick, drums_snare, drums_toms, drums_hihat, drums_ride, drums_crash |
| `mean_db` | number | dBFS | yes |  |

#### `drum_hits` - event, by **drums**
`events/drum_hits.json` · schema `mvh/events/drum_hits` · classified drum hits

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `drum` | string |  | yes | one of kick, snare, hat, tom, cymbal, perc |
| `vel` | number | 0..1 | yes |  |
| `level_db` | number | dBFS | yes |  |
| `conf` | number | 0..1 | yes |  |
| `source` | string |  | yes | one of drumsep, classifier |

#### `instruments` - segment, by **instruments**
`events/instruments.json` · schema `mvh/events/instruments` · instrument timeline segments

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `instrument` | string |  | yes | instrument slug |
| `conf` | number | 0..1 | yes |  |
| `evidence` | string |  | yes | one of stem, tagger, both |
| `stem` | string|null |  | yes | one of vocals, lead_vocals, backing_vocals, drums, bass, guitar, piano, other, instrumental, drums_kick, drums_snare, drums_toms, drums_hihat, drums_ride, drums_crash |

#### `vocal_style` - segment, by **instruments**
`events/vocal_style.json` · schema `mvh/events/vocal_style` · lead-vocal style segments

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `style` | string |  | yes | one of singing, speech, rap |
| `conf` | number | 0..1 | yes |  |

#### `notes.{src}` - event, by **notes**
`events/notes.{src}.json` · schema `mvh/events/notes` · note events of one pitched stem (src = bass, piano, guitar, other)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `midi` | integer |  | yes | MIDI note number |
| `name` | string |  | yes | note name, e.g. A3 (C4 = MIDI 60) |
| `vel` | number | 0..1 | yes | velocity 0..1 |
| `conf` | number | 0..1 | yes |  |

#### `notes.vocals` - event, by **vocals**
`events/notes.vocals.json` · schema `mvh/events/notes` · lead-vocal notes (from f0)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `midi` | integer |  | yes | MIDI note number |
| `name` | string |  | yes | note name, e.g. A3 (C4 = MIDI 60) |
| `vel` | number | 0..1 | yes | velocity 0..1 |
| `conf` | number | 0..1 | yes |  |

#### `vocal_phrases` - segment, by **vocals**
`events/vocal_phrases.json` · schema `mvh/events/vocal_phrases` · ids `vocal_phrase` · voiced phrases of the lead vocal

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Vocal phrase id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `median_midi` | number | MIDI | yes |  |
| `min_midi` | number | MIDI | yes |  |
| `max_midi` | number | MIDI | yes |  |
| `mean_db` | number | dBFS | yes |  |

#### `mood` - segment, by **mood**
`events/mood.json` · schema `mvh/events/mood` · mood per section

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `section_id` | string |  | yes | Section id |
| `valence` | number | 0..1 | yes |  |
| `arousal` | number | 0..1 | yes |  |
| `valence_conf` | number | 0..1 | yes |  |
| `arousal_conf` | number | 0..1 | yes |  |
| `tags` | string[] |  | yes | top mood/theme tags |

#### `voice_spans` - segment, by **voices**
`events/voice_spans.json` · schema `mvh/events/voice_spans` · proposed voice per line or word span (a line may have several spans)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `line_id` | string |  | yes | Lyric line, in sung order id |
| `first_word` | string|null |  | yes | Lyric word (line_id.k, k 1-based) id |
| `last_word` | string|null |  | yes | Lyric word (line_id.k, k 1-based) id |
| `voice_id` | string |  | yes | Voice cluster (one singing or rapping voice) id |
| `conf` | number | 0..1 | yes |  |
| `review` | boolean |  | yes | low confidence: flagged for review |

#### `voice_activity` - segment, by **voices**
`events/voice_activity.json` · schema `mvh/events/voice_activity` · when each voice sings

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `voice_id` | string |  | yes | Voice cluster (one singing or rapping voice) id |

#### `visemes` - segment, by **lipsync** (optional file)
`lipsync/visemes.json` · schema `mvh/events/visemes` · Rhubarb mouth shapes A-H, X (Preston Blair mapping in CONTRACT.md)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `viseme` | string |  | yes | one of A, B, C, D, E, F, G, H, X |
| `voice_id` | string|null |  | yes | Voice cluster (one singing or rapping voice) id |
| `line_id` | string|null |  | yes | Lyric line, in sung order id |

#### `phonemes` - segment, by **lipsync** (optional file)
`lipsync/phonemes.json` · schema `mvh/events/phonemes` · phonemes

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `phoneme` | string |  | yes | ARPAbet or IPA symbol |
| `voice_id` | string|null |  | yes | Voice cluster (one singing or rapping voice) id |
| `word_id` | string|null |  | yes | Lyric word (line_id.k, k 1-based) id |

#### `counts` - segment, by **choreo**
`events/counts.json` · schema `mvh/events/counts` · ids `eight` · eight-counts; restart at every phrase and section start; E000 = synthesised 5-6-7-8 lead-in

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Eight-count (E000 = synthesised lead-in) id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `start_beat` | integer |  | yes | beat_index of the first count (may be < 0 for the E000 lead-in) |
| `len` | integer |  | yes | beats in this count: 8 (6 in 3/4), shorter when partial |
| `first_count` | integer |  | yes | 1, or 5 for the E000 lead-in |
| `phrase_id` | string|null |  | yes | Phrase (4/8/16 bars) id |
| `section_id` | string|null |  | yes | Section id |
| `partial` | boolean |  | yes |  |
| `lead_in` | boolean |  | yes |  |
| `in_pulse` | boolean |  | yes |  |
| `accents` | number[] | 0..1 | yes | accent per count (len entries) |

#### `grooves` - segment, by **choreo**
`events/grooves.json` · schema `mvh/events/grooves` · per-bar 16-step groove matrix

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `bar` | integer |  | yes |  |
| `groove_id` | string |  | yes | Groove (per-bar pattern cluster) id |
| `swing` | number | ratio | yes | long/short 8th ratio; 1 = straight |
| `syncopation` | number | 0..1 | yes |  |
| `pattern` | object |  | yes |  |

#### `hit_points` - event, by **choreo**
`events/hit_points.json` · schema `mvh/events/hit_points` · ids `hit_point` · ranked coinciding accents

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Choreography hit point id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `strength` | number | 0..1 | yes |  |
| `rank` | integer |  | yes |  |
| `kinds` | string[] |  | yes | what coincides: drum, onset, impact, stop, vocal_onset, chord, ... |
| `sources` | object[] |  | yes |  |

#### `holds` - segment, by **choreo**
`events/holds.json` · schema `mvh/events/holds` · ids `hold` · sustained moments to hold a pose

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Choreography hold id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `kind` | string |  | yes | one of vocal_note, chord, decay, silence |
| `strength` | number | 0..1 | yes |  |
| `source` | object |  | yes | link to the item a derived item comes from |

#### `cues` - event, by **cues**
`events/cues.json` · schema `mvh/events/cues` · ids `cue` · THE list agents cut from; ONE cue per time (D37: co-timed cues merge, kinds[]/sources[] list them); tier-4 beats are references to events/beats.json: strength/lead_in_s null

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `id` | string |  | yes | Cue id |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `kind` | string |  | yes | one of section, drop, build_start, breakdown, phrase, impact, stop, silence, hit_point, downbeat, beat, pinned |
| `tier` | integer |  | yes | 1 section/drop/build start, 2 phrase/impact/stop, 3 hit point/downbeat, 4 beat |
| `strength` | number|null | 0..1 | yes |  |
| `lead_in_s` | number|null | s | yes | recommended anticipation window |
| `next_major_in_s` | number|null | s | yes | time to the next tier-1 cue |
| `source` | object |  | yes | link to the item a derived item comes from |
| `kinds` | string[] |  | no | every kind merged into this cue, highest priority first (kinds[0] == kind) |
| `sources` | object[] |  | no | the source of every merged kind (sources[0] == source) |

#### `moments` - event, by **cues**
`events/moments.json` · schema `mvh/events/moments` · top moments (the brief shows the top 15)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `rank` | integer |  | yes |  |
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number|null | s | yes | duration in seconds |
| `cue_id` | string |  | yes | Cue id |
| `kind` | string |  | yes |  |
| `strength` | number | 0..1 | yes |  |
| `description` | string |  | yes | no lyric text beyond 10 words |

#### `singing` - segment, by **meaning**
`events/singing.json` · schema `mvh/events/singing` · who sings when: lines joined with voices and characters (singerAt reads this)

| Field | Type | Unit | Frozen | Description |
|---|---|---|---|---|
| `t` | number | s | yes | time in seconds from the first sample of audio/mix.flac |
| `d` | number | s | yes | duration in seconds |
| `character_id` | string |  | yes | Character (from intent.md or meaning) id |
| `voice_id` | string |  | yes | Voice cluster (one singing or rapping voice) id |
| `line_id` | string |  | yes | Lyric line, in sung order id |
| `lead_backing` | string |  | yes | one of lead, backing |
<!-- END GENERATED: events -->

**Viseme mapping** (Rhubarb -> Preston Blair): A = M/B/P (closed) · B = most consonants, K/S/T, "ee" (slightly open, teeth) ·
C = E/AE (open) · D = A/I (wide open) · E = O/ER (rounded) · F = U/W/OO (puckered) · G = F/V (teeth on lip) · H = L (tongue up) ·
X = rest/idle.

---

## 7. Other files and tables

**JSON documents** (*generated*: required keys; producers may add keys):

<!-- BEGIN GENERATED: files -->
#### `mvh/files/source` - `meta/source.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `channels` | integer |  |  |
| `codec` | string |  |  |
| `decode_warnings` | integer |  |  |
| `duration_s` | number | s |  |
| `file_name` | string |  |  |
| `has_cover` | boolean |  |  |
| `lossless` | boolean |  |  |
| `n_samples` | integer |  |  |
| `palette` | string[] |  |  |
| `pcm_sha256` | string |  | sha256 (hex) |
| `peak_abs` | number | linear | max \|x\| of the canonical decode |
| `sample_rate` | integer |  |  |
| `soundtrack` | string |  | audio/mix.flac, or audio/mix.wav when peak_abs > 1 |
| `tags` | object |  | ffprobe tags, keys lower-cased |

#### `mvh/files/identity` - `meta/identity.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `album` | string|null |  |  |
| `artist` | string|null |  |  |
| `conf` | number | 0..1 |  |
| `credits` | object[] |  |  - item keys: `name`, `role` |
| `duration_s` | number | s |  |
| `source` | string |  | one of tags, acoustid, musicbrainz, user |
| `title` | string|null |  |  |

#### `mvh/files/separation` - `fast/separation.json`, `meta/separation.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `degraded` | boolean |  |  |
| `lead_backing_split` | boolean |  |  |
| `models` | object[] |  |  - item keys: `id`, `licence` |
| `stems` | object |  |  |
| `variant` | string |  | one of rocm, cpu, htdemucs, fast |

#### `mvh/files/stems` - `meta/stems.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `stems` | object |  |  |
| `thresholds` | object |  |  - keys: `active_db`, `attack_ms`, `release_ms`, `within_db` |

#### `mvh/files/loudness` - `meta/loudness.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `integrated_lufs` | number | LUFS |  |
| `lra_high_lufs` | number | LUFS |  |
| `lra_low_lufs` | number | LUFS |  |
| `lra_lu` | number | LU |  |
| `plr_db` | number | dB |  |
| `sample_peak_db` | number | dBFS |  |
| `true_peak_dbtp` | number | dBTP |  |

#### `mvh/files/tempo` - `meta/tempo.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `bpm` | number | BPM |  |
| `candidates` | object[] |  |  - item keys: `bpm`, `relation`, `score` |
| `confidence` | number | 0..1 |  |
| `feel` | string |  | one of normal, half_time, double_time |
| `is_variable` | boolean |  |  |
| `meter` | object |  |  - keys: `beats_per_bar`, `changes`, `confidence`, `time_signature` |
| `qa` | object |  |  - keys: `beat_agreement_f`, `downbeat_agreement_f`, `flags` |

#### `mvh/files/key` - `meta/key.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `agreement` | string |  | agree \| relative \| parallel \| fifth \| disagree |
| `flags` | string[] |  |  |
| `global` | object |  |  - keys: `conf`, `key`, `mode`, `tonic_pc` |

#### `mvh/files/structure` - `meta/structure.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `n_sections` | integer |  |  |
| `phrase_bars` | integer |  | dominant phrase length in bars (4, 8 or 16) |
| `repeat_groups` | object |  |  |

#### `mvh/files/instruments` - `meta/instruments.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `summary` | object[] |  |  - item keys: `coverage`, `instrument`, `mean_conf` |
| `vocabulary` | string[] |  |  |
| `vocal_style` | object |  |  - keys: `dominant`, `shares` |

#### `mvh/files/notes_index` - `notes/notes.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `sources` | object |  |  |
| `tempo_map` | string |  | how notes.mid's tempo map was built |

#### `mvh/files/vocal_range` - `meta/vocal_range.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `conf` | number | 0..1 |  |
| `highest` | object|null |  |  - keys: `hz`, `midi`, `name`, `t` |
| `lowest` | object|null |  |  - keys: `hz`, `midi`, `name`, `t` |
| `median_midi` | number|null | MIDI |  |
| `p10` | number|null | MIDI |  |
| `p2` | number|null | MIDI |  |
| `p90` | number|null | MIDI |  |
| `p98` | number|null | MIDI |  |
| `present` | boolean |  | false when < ~8 voiced seconds; then the statistics are null |
| `register` | string|null |  | bass, baritone, tenor, alto, mezzo, soprano (low confidence) |
| `span_semitones` | number|null | semitones |  |
| `voiced_s` | number | s |  |

#### `mvh/files/mood` - `meta/mood.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `global` | object |  |  - keys: `arousal`, `arousal_conf`, `tags`, `valence`, `valence_conf` |

#### `mvh/files/voices` - `meta/voices.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `method` | string |  |  |
| `n_source` | string |  | one of intent, estimate, hints |
| `n_voices` | integer |  |  |
| `voices` | object[] |  |  - item keys: `hint`, `id`, `n_lines`, `proposed_character_id`, `seconds` |

#### `mvh/files/grooves` - `meta/grooves.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `grooves` | object[] |  |  - item keys: `bars`, `id`, `n_bars`, `prototype`, `swing`, `syncopation` |

#### `mvh/files/lyrics` - `lyrics/lyrics.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `coverage` | number | 0..1 |  |
| `grade` | string|null |  | A (best) .. D one of A, B, C, D |
| `instrumental` | boolean |  |  |
| `language` | string|null |  |  |
| `lines` | object[] |  |  - item keys: `backing`, `conf`, `d`, `first_word`, `grade`, `id`, `n_words`, `repeat_group`, `section_id`, `speaker_hint`, `t`, `text`, `text_group`, `timing_source` |
| `lyrics_match_score` | number|null | 0..1 |  |
| `provenance` | any |  |  |
| `schema` | any |  |  |
| `schema_version` | string |  | semver |
| `source` | object |  |  - keys: `duration_diff_s`, `has_word_sync`, `kind`, `lrclib_id` |
| `words` | object[] |  |  - item keys: `conf`, `d`, `id`, `line_id`, `t`, `text` |

#### `mvh/files/meaning` - `meaning/meaning.json`, `meaning/authored.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `characters` | object[] |  |  - item keys: `description`, `id`, `lead_backing`, `line_ids`, `name`, `provenance`, `section_ids`, `voice_ids` |
| `do_not` | string[] |  |  |
| `logline` | string|null |  |  |
| `motifs` | object[] |  |  - item keys: `id`, `name`, `occurrences`, `provenance` |
| `open_questions` | string[] |  |  |
| `palette` | string[] |  |  |
| `perspective` | object |  |  - keys: `addressee`, `narrator` |
| `schema` | any |  |  |
| `schema_version` | string |  | semver |
| `sections` | object[] |  |  - item keys: `camera_hint`, `characters_present`, `do_not`, `emotion`, `feel`, `meaning`, `movement_hint`, `occurrence_label`, `palette_hint`, `provenance`, `section_id`, `t0`, `t1` |
| `setting` | string|null |  |  |
| `status` | string |  | one of user, draft, pending |
| `summary` | string|null |  |  |
| `symbolism` | object[] |  |  - item keys: `cites`, `source`, `text` |
| `themes` | object[] |  |  - item keys: `cites`, `source`, `text` |
| `tone` | string|null |  |  |

#### `mvh/files/meaning_input` - `meaning/input.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `facts` | object |  | facts the draft may cite |
| `lines_file` | string|null |  | lyrics/lines.tsv, or null with --no-lyrics-to-agents |
| `schema_version` | string |  | semver |
| `sections` | object[] |  |  - item keys: `d`, `id`, `label`, `t` |
| `song` | object |  |  - keys: `artist`, `duration_s`, `title` |

#### `mvh/files/orphans` - `meaning/orphans.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `orphans` | object[] |  |  - item keys: `claim`, `occurrence_label`, `old_section_id`, `reason`, `t_range` |

#### `mvh/intermediate/allin1` - `allin1.json`

| Key | Type | Unit | Description |
|---|---|---|---|
| `activations` | object |  | row-major float32 [frames x columns]: beat, downbeat, boundary, then label probabilities - keys: `columns`, `file`, `frames`, `rate_hz` |
| `beat_positions` | integer[] |  |  |
| `beats` | number[] |  |  |
| `bpm` | number|null | BPM |  |
| `downbeats` | number[] |  |  |
| `embeddings` | object|null |  |  - keys: `dim`, `file`, `frames`, `rate_hz` |
| `labels` | string[] |  |  |
| `segments` | object[] |  |  - item keys: `end`, `label`, `start` |
<!-- END GENERATED: files -->

`meaning/schema.json` is a copy of `mvh/files/meaning` for the drafting agent. An authored draft (`meaning/authored.json`) must validate
against it with `status: "draft"`; the user's `meaning/intent.md` is free text or the YAML template written by the interview.
Merge precedence for every claim: user > lyric > audio > external > speculative; draft claims never overwrite user claims.
Every per-section entry stores `section_id`, `t0`, `t1` and `occurrence_label`, so `mvh meaning` can re-anchor it by time overlap;
claims that lose their section go to `orphans.json` and a warning in brief.md.

**Tables** (*generated*):

<!-- BEGIN GENERATED: tables -->
- `tables/beats.csv` (comma, by **choreo**): `beat_index`, `t` [s], `bar`, `beat_in_bar`, `beats_in_bar`, `in_pulse`, `strength` [0..1], `section_id`, `phrase_id`, `eight_id`, `count`, `accent` [0..1]. one row per beat (from events/beats.json, joined with sections, phrases and counts).
- `tables/bars.csv` (comma, by **choreo**): `bar`, `t` [s], `d` [s], `beats_in_bar`, `n_beats`, `pickup`, `in_pulse`, `section_id`, `phrase_id`, `groove_id`, `swing` [ratio], `syncopation` [0..1]. one row per bar (from events/bars.json, joined with sections, phrases and grooves).
- `tables/sections.csv` (comma, by **choreo**): `id`, `t` [s], `d` [s], `label`, `occurrence`, `repeat_group`, `start_bar`, `n_bars`, `edm_role`, `level`, `mean_lufs` [LUFS]. one row per section (from events/sections.json).
- `lyrics/lines.tsv` (TAB, by **meaning**): `id`, `t` [s], `d` [s], `section_id`, `singer`, `repeat_group`, `grade`, `text`. lyric lines, safe for an agent's context (PLAN §4.1 column order).
- `frames/{fps}fps.csv` (comma, by **frames**): `frame`, `t` [s]. mvh frames: one row per video frame (frame, t = time_of(frame), then one column per requested channel).
<!-- END GENERATED: tables -->

`frames/{fps}fps.csv` naming: `{fps}` = the rate (`24`, `23.976` with up to 3 decimals, rationals as `24000-1001`), then `_f<frame0>`
when frame0 != 0 and `_early` for the early rule: `24fps.csv`, `24000-1001_f1fps.csv`, `30_earlyfps.csv`. Columns: `frame` (n, including
frame0), `t` (= time_of(n)), then one column per channel id with `curve_frame` values under the channel's policy (never NaN).

**Envelope documents**: `manifest.json` (`mvh/envelope/manifest`), `curves/index.json` (`mvh/envelope/curves_index`), `run.json`
(`mvh/envelope/run`), `overrides.json` (`mvh/envelope/overrides`), repo-root `models.lock.json` (`mvh/envelope/models_lock`: `{id,
envs[], files[{path, url, revision, sha256, size}], licence, used_by[]}`), and the per-run `result.json` of a stage or worker
(`mvh/envelope/stage_result`). Override keys (dotted `<section>.<field>`; a stage declares the ones it reads in `override_keys`):
`rhythm.beat_offset_s`, `rhythm.bpm`, `rhythm.downbeat_phase` (rhythm, applied after tracking and before fusion);
`structure.boundaries`, `structure.labels` (structure; anchored by **time**, since section IDs move); `lyrics.lines`, `lyrics.words`
(lyrics; keyed by line/word id); `voices.lines` (voices; line id -> voice id); `cues.pinned` (cues). Singer assignments made in the
viewer go to `meaning/intent.md` (an external input of voices and meaning).

---

## 8. File catalogue (*generated*)

Producer `_runner` = the runner's finalize step; `_user` = user/agent-authored input. Cache-only intermediates are not listed.

<!-- BEGIN GENERATED: catalogue -->
| Path | Kind | Producer | Schema | Req | Description |
|---|---|---|---|---|---|
| `curves/chroma12.f32` | curve | _runner | - | yes | 12 pitch classes (C=0) at 100 Hz; channels from harmony (packed by the runner) |
| `curves/core.f32` | curve | _runner | - | yes | Mix-level curves at 100 Hz; channels from choreo, drums, dynamics, loudness, rhythm, spectral (packed by the runner) |
| `curves/index.json` | json | _runner | `mvh/envelope/curves_index` | yes | curve registry with byte offsets |
| `curves/instruments_1hz.f32` | curve | _runner | - | yes | Instrument and vocal-style probabilities at 1 Hz; channels from instruments (packed by the runner) |
| `curves/mood_1hz.f32` | curve | _runner | - | yes | Valence, arousal and mood/theme tags at 1 Hz; channels from mood (packed by the runner) |
| `curves/spectrum128.u8` | matrix | _runner | - | yes | [frames x 128] viz band values (u8/255 = viz bands[k]); same layout as viz bandBytes R channel; channels from spectral (packed by the runner) |
| `curves/stems.f32` | curve | _runner | - | yes | Per-stem levels and activity at 100 Hz; channels from stem_activity (packed by the runner) |
| `curves/vocal.f32` | curve | _runner | - | yes | Lead-vocal pitch and mouth_open at 100 Hz; channels from lipsync, vocals (packed by the runner) |
| `lib/mvh.glsl` | text | _runner | - | yes | GLSL sampler mvhCurve |
| `lib/mvh.js` | text | _runner | - | yes | JS loader (ES module, no dependencies) |
| `lib/mvh_load.py` | text | _runner | - | yes | Python loader (numpy only) |
| `manifest.json` | json | _runner | `mvh/envelope/manifest` | yes | index only |
| `run.json` | json | _runner | `mvh/envelope/run` | yes | volatile run facts |
| `schema/{name}.schema.json` | json | _runner | - | yes | copies of the contract schemas |
| `meaning/authored.json` | json | _user | `mvh/files/meaning` | opt | a meaning draft written by an agent or LLM (status draft); an input, never overwritten |
| `meaning/intent.md` | text | _user | - | opt | the user's answers (free text or the YAML template); never overwritten |
| `overrides.json` | json | _user | `mvh/envelope/overrides` | opt | user corrections (viewer edit mode or by hand) |
| `artwork/cover.jpg` | audio | ingest | - | opt | embedded cover art (absent when the file has none) |
| `audio/mix.flac` | audio | ingest | - | yes | THE soundtrack and timebase: 24-bit FLAC of the canonical decode |
| `audio/mix.wav` | audio | ingest | - | opt | float32 WAV twin, written only when the decode exceeds full scale |
| `audio/preview.opus` | audio | ingest | - | yes | preview for the viewer |
| `meta/source.json` | json | ingest | `mvh/files/source` | yes | decode facts, raw tags, palette |
| `meta/identity.json` | json | identity | `mvh/files/identity` | yes | title, artist, album, credits, MusicBrainz/AcoustID ids |
| `meta/loudness.json` | json | loudness | `mvh/files/loudness` | yes | integrated loudness, LRA, true peak, PLR |
| `meta/separation.json` | json | separate_hq | `mvh/files/separation` | yes | separator variant, models, lead/backing split, invariants |
| `stems/backing_vocals.flac` | audio | separate_hq | - | yes | backing_vocals stem, sample-aligned with the mix, same length (24-bit; plus stems/backing_vocals.wav float when \|x\| > 1) |
| `stems/bass.flac` | audio | separate_hq | - | yes | bass stem, sample-aligned with the mix, same length (24-bit; plus stems/bass.wav float when \|x\| > 1) |
| `stems/drums.flac` | audio | separate_hq | - | yes | drums stem, sample-aligned with the mix, same length (24-bit; plus stems/drums.wav float when \|x\| > 1) |
| `stems/drums/crash.flac` | audio | separate_hq | - | opt | drum sub-stem crash (DrumSep; Should) |
| `stems/drums/hihat.flac` | audio | separate_hq | - | opt | drum sub-stem hihat (DrumSep; Should) |
| `stems/drums/kick.flac` | audio | separate_hq | - | opt | drum sub-stem kick (DrumSep; Should) |
| `stems/drums/ride.flac` | audio | separate_hq | - | opt | drum sub-stem ride (DrumSep; Should) |
| `stems/drums/snare.flac` | audio | separate_hq | - | opt | drum sub-stem snare (DrumSep; Should) |
| `stems/drums/toms.flac` | audio | separate_hq | - | opt | drum sub-stem toms (DrumSep; Should) |
| `stems/guitar.flac` | audio | separate_hq | - | yes | guitar stem, sample-aligned with the mix, same length (24-bit; plus stems/guitar.wav float when \|x\| > 1) |
| `stems/instrumental.flac` | audio | separate_hq | - | yes | instrumental stem, sample-aligned with the mix, same length (24-bit; plus stems/instrumental.wav float when \|x\| > 1) |
| `stems/lead_vocals.flac` | audio | separate_hq | - | yes | lead_vocals stem, sample-aligned with the mix, same length (24-bit; plus stems/lead_vocals.wav float when \|x\| > 1) |
| `stems/other.flac` | audio | separate_hq | - | yes | other stem, sample-aligned with the mix, same length (24-bit; plus stems/other.wav float when \|x\| > 1) |
| `stems/piano.flac` | audio | separate_hq | - | yes | piano stem, sample-aligned with the mix, same length (24-bit; plus stems/piano.wav float when \|x\| > 1) |
| `stems/vocals.flac` | audio | separate_hq | - | yes | vocals stem, sample-aligned with the mix, same length (24-bit; plus stems/vocals.wav float when \|x\| > 1) |
| `events/hits.high.json` | events | spectral | `mvh/events/hits.high` | yes | events `hits.high` (event): high hit events from the viz hit envelope (refined on a 2.5 ms envelope) |
| `events/hits.kick.json` | events | spectral | `mvh/events/hits.kick` | yes | events `hits.kick` (event): kick hit events from the viz hit envelope (refined on a 2.5 ms envelope) |
| `events/hits.mid.json` | events | spectral | `mvh/events/hits.mid` | yes | events `hits.mid` (event): mid hit events from the viz hit envelope (refined on a 2.5 ms envelope) |
| `events/onsets.bass.json` | events | spectral | `mvh/events/onsets.bass` | yes | events `onsets.bass` (event): bass-band flux onsets (centred threshold) |
| `events/onsets.high.json` | events | spectral | `mvh/events/onsets.high` | yes | events `onsets.high` (event): high-band flux onsets (centred threshold) |
| `events/onsets.mid.json` | events | spectral | `mvh/events/onsets.mid` | yes | events `onsets.mid` (event): mid-band flux onsets (centred threshold) |
| `events/bars.json` | events | rhythm | `mvh/events/bars` | yes | events `bars` (segment): bars (downbeat to downbeat); section/phrase/groove links are in tables/bars.csv |
| `events/beats.json` | events | rhythm | `mvh/events/beats` | yes | events `beats` (event): the beat grid: every beat, virtual beats (in_pulse false) continue through no-pulse regions |
| `events/pulse_regions.json` | events | rhythm | `mvh/events/pulse_regions` | yes | events `pulse_regions` (segment): regions with / without a perceptible beat, covering the whole song |
| `events/tempo_segments.json` | events | rhythm | `mvh/events/tempo_segments` | yes | events `tempo_segments` (segment): piecewise tempo grid |
| `meta/tempo.json` | json | rhythm | `mvh/files/tempo` | yes | tempo, alternatives, feel, meter, rhythm QA |
| `events/decay_tails.json` | events | dynamics | `mvh/events/decay_tails` | yes | events `decay_tails` (segment): ringing-out tails after hits or section ends |
| `events/dynamics.json` | events | dynamics | `mvh/events/dynamics` | yes | events `dynamics` (segment): loud and quiet parts, boundaries snapped to downbeats |
| `events/impacts.json` | events | dynamics | `mvh/events/impacts` | yes | events `impacts` (event): sudden energy increases |
| `events/silences.json` | events | dynamics | `mvh/events/silences` | yes | events `silences` (segment): silent stretches |
| `events/stops.json` | events | dynamics | `mvh/events/stops` | yes | events `stops` (event): sudden cuts to (near) silence |
| `events/chords.json` | events | harmony | `mvh/events/chords` | yes | events `chords` (segment): chord timeline snapped to beats |
| `events/key.json` | events | harmony | `mvh/events/key` | yes | events `key` (segment): key regions (one item when the key never changes) |
| `meta/key.json` | json | harmony | `mvh/files/key` | yes | global key and method agreement |
| `events/stem_activity.json` | events | stem_activity | `mvh/events/stem_activity` | yes | events `stem_activity` (segment): active segments per stem |
| `meta/stems.json` | json | stem_activity | `mvh/files/stems` | yes | per-stem presence and level statistics |
| `events/drum_hits.json` | events | drums | `mvh/events/drum_hits` | yes | events `drum_hits` (event): classified drum hits |
| `events/instruments.json` | events | instruments | `mvh/events/instruments` | yes | events `instruments` (segment): instrument timeline segments |
| `events/vocal_style.json` | events | instruments | `mvh/events/vocal_style` | yes | events `vocal_style` (segment): lead-vocal style segments |
| `meta/instruments.json` | json | instruments | `mvh/files/instruments` | yes | instrument summary and vocal style |
| `events/notes.{src}.json` | events | notes | `mvh/events/notes` | yes | events `notes.{src}` (event): note events of one pitched stem (src = bass, piano, guitar, other) |
| `notes/notes.json` | json | notes | `mvh/files/notes_index` | yes | per-source note statistics and file index |
| `notes/notes.mid` | midi | notes | - | yes | one track per source (bass, piano, guitar, other); tempo map from the beat grid |
| `notes/{src}.mid` | midi | notes | - | opt | one MIDI file per source |
| `events/edm_roles.json` | events | structure | `mvh/events/edm_roles` | yes | events `edm_roles` (segment): THE definition of builds, drops and breakdowns (snapped to downbeats) |
| `events/phrases.json` | events | structure | `mvh/events/phrases` | yes | events `phrases` (segment): 4/8/16-bar phrases aligned to section starts |
| `events/sections.json` | events | structure | `mvh/events/sections` | yes | events `sections` (segment): CANONICAL sections; boundaries on downbeats; segments shorter than 2 bars are merged |
| `meta/structure.json` | json | structure | `mvh/files/structure` | yes | repeat groups and phrase length |
| `lyrics/lyrics.ass` | text | lyrics | - | yes | ASS karaoke (\k tags) |
| `lyrics/lyrics.json` | json | lyrics | `mvh/files/lyrics` | yes | CANONICAL lyrics: lines and words with timing and confidence |
| `lyrics/lyrics.lrc` | text | lyrics | - | yes | LRC with A2 word tags |
| `lyrics/lyrics.srt` | text | lyrics | - | yes | SRT (line level) |
| `lyrics/lyrics.vtt` | text | lyrics | - | yes | WebVTT with inline word timestamps |
| `events/mood.json` | events | mood | `mvh/events/mood` | yes | events `mood` (segment): mood per section |
| `meta/mood.json` | json | mood | `mvh/files/mood` | yes | global mood |
| `events/notes.vocals.json` | events | vocals | `mvh/events/notes` | yes | events `notes.vocals` (event): lead-vocal notes (from f0) |
| `events/vocal_phrases.json` | events | vocals | `mvh/events/vocal_phrases` | yes | events `vocal_phrases` (segment): voiced phrases of the lead vocal |
| `meta/vocal_range.json` | json | vocals | `mvh/files/vocal_range` | yes | vocal range, tessitura, register |
| `notes/vocals.mid` | midi | vocals | - | yes | lead-vocal notes as MIDI (tempo map from the beat grid) |
| `events/counts.json` | events | choreo | `mvh/events/counts` | yes | events `counts` (segment): eight-counts; restart at every phrase and section start; E000 = synthesised 5-6-7-8 lead-in |
| `events/grooves.json` | events | choreo | `mvh/events/grooves` | yes | events `grooves` (segment): per-bar 16-step groove matrix |
| `events/hit_points.json` | events | choreo | `mvh/events/hit_points` | yes | events `hit_points` (event): ranked coinciding accents |
| `events/holds.json` | events | choreo | `mvh/events/holds` | yes | events `holds` (segment): sustained moments to hold a pose |
| `meta/grooves.json` | json | choreo | `mvh/files/grooves` | yes | groove clusters G01.. |
| `tables/bars.csv` | table | choreo | `mvh/tables/bars` | yes | one row per bar (from events/bars.json, joined with sections, phrases and grooves) |
| `tables/beats.csv` | table | choreo | `mvh/tables/beats` | yes | one row per beat (from events/beats.json, joined with sections, phrases and counts) |
| `tables/sections.csv` | table | choreo | `mvh/tables/sections` | yes | one row per section (from events/sections.json) |
| `events/cues.json` | events | cues | `mvh/events/cues` | yes | events `cues` (event): THE list agents cut from; ONE cue per time (D37: co-timed cues merge, kinds[]/sources[] list them); tier-4 beats are references to events/beats.json: strength/lead_in_s null |
| `events/moments.json` | events | cues | `mvh/events/moments` | yes | events `moments` (event): top moments (the brief shows the top 15) |
| `events/voice_activity.json` | events | voices | `mvh/events/voice_activity` | yes | events `voice_activity` (segment): when each voice sings |
| `events/voice_spans.json` | events | voices | `mvh/events/voice_spans` | yes | events `voice_spans` (segment): proposed voice per line or word span (a line may have several spans) |
| `meta/voices.json` | json | voices | `mvh/files/voices` | yes | voice clusters V1..Vn |
| `lipsync/phonemes.json` | events | lipsync | `mvh/events/phonemes` | opt | events `phonemes` (segment): phonemes |
| `lipsync/visemes.json` | events | lipsync | `mvh/events/visemes` | opt | events `visemes` (segment): Rhubarb mouth shapes A-H, X (Preston Blair mapping in CONTRACT.md) |
| `events/singing.json` | events | meaning | `mvh/events/singing` | yes | events `singing` (segment): who sings when: lines joined with voices and characters (singerAt reads this) |
| `lyrics/lines.tsv` | table | meaning | `mvh/tables/lines` | yes | lyric lines, safe for an agent's context (PLAN §4.1 column order) |
| `meaning/input.json` | json | meaning | `mvh/files/meaning_input` | yes | facts bundle for the drafting agent |
| `meaning/interview.md` | text | meaning | - | yes | questions for the user, generated from the facts |
| `meaning/meaning.json` | json | meaning | `mvh/files/meaning` | yes | MERGED meaning (user > lyric > audio > external > speculative) |
| `meaning/meaning.md` | text | meaning | - | yes | human-readable meaning |
| `meaning/orphans.json` | json | meaning | `mvh/files/orphans` | yes | claims that lost their section after a re-anchor |
| `meaning/request.md` | text | meaning | - | yes | instructions for the drafting agent |
| `meaning/schema.json` | json | meaning | - | yes | JSON Schema the draft must satisfy (copy of mvh/files/meaning) |
| `brief.md` | text | brief | - | yes | the LLM entry point (<= 4k tokens) |
| `frames/{fps}fps.csv` | table | frames | `mvh/tables/frames` | yes | mvh frames: one row per video frame (frame, t = time_of(frame), then one column per requested channel) |
| `viewer.html` | text | viewer | - | yes | the viewer (file:// read-only with inlined preview data; mvh view for edit mode) |
<!-- END GENERATED: catalogue -->

---

## 9. Helpers (`lib/mvh.js` ES module, no deps · `lib/mvh_load.py`, numpy only)

Both implementations behave identically (Python = snake_case of the JS name; options objects become keyword arguments). Every helper is
a pure function of t or of the frame number; once loaded, everything is synchronous. Reference column = the function in
`conventions.py` that defines the semantics; the golden vectors cover every row.

| JS | Python | Args | Returns | Reference |
|---|---|---|---|---|
| `await load(base, {fetch?, include?})` | `load(base, include=None)` | base: URL (browser) or folder path; include: groups to load eagerly (`"curves:core"`, `"events:beats"`, `"lyrics"`, ...); the rest loads lazily | `Song` | - |
| `loadSync(path)` (Node) | `load(path)` | folder path | `Song` (everything readable synchronously; lazy parts read on first use) | - |
| `await song.ensure(id)` | `song.ensure(id)` | curve file id, events name, `"lyrics"`, `"meaning"` | void (makes the next sync call safe in Remotion/browsers) | - |
| `song.curve(id).at(t)` | `song.curve(id).at(t)` | t (s) | number, never NaN | `curve_at` |
| `song.curve(id).frame(n, fr)` | `song.curve(id).frame(n, fr)` | n, fr `{fps, frame0, early}` | number, never NaN | `curve_frame` |
| `song.curve(id).values / .rate / .meta` | same | - | Float32Array / np.float32 view, Hz, index entry | - |
| `song.events(name).at(t)` | `song.events(name).at(t)` | t | `{item, progress, t_in, t_left}` or null (items with d > 0; latest start wins) | `event_at` |
| `.allAt(t)` | `.all_at(t)` | t | **every** item with d > 0 containing t (`[t, t + d)`), sorted by t then file order; use it for overlapping files (duet `visemes`, `voice_spans`, `voice_activity`, `notes.other` chords, `instruments`, `stem_activity`), where `.at` shows only the latest start | `event_all_at` |
| `.next(t, {minTier})` | `.next(t, min_tier=None)` | t; keep tiers 1..minTier | first item with item.t > t, or null. `cues` has one cue per time (D37), so stepping `t = cue.t` reaches every cue | `event_next` |
| `.prev(t, {minTier})` | `.prev(t, min_tier=None)` | t | last item with item.t <= t, or null | `event_prev` |
| `.between(t0, t1, {minTier})` | `.between(t0, t1, min_tier=None)` | [t0, t1) | items | `event_between` |
| `.inFrame(n, fr, {minTier})` | `.in_frame(n, fr, min_tier=None)` | n, fr | items with frame_of(t) == n | `event_in_frame` |
| `.items` | `.items` | - | all items (sorted by t) | - |
| `frameOf(t, fr)` · `timeOf(n, fr)` | `frame_of(t, fr)` · `time_of(n, fr)` | | int · seconds | `frame_of`, `time_of` |
| `song.frameCount(fr)` | `song.frame_count(fr)` | fr | int (frames with t_n < duration) | `frame_count` |
| `song.pulse(src, t, {attack=0, decay=0.25, unit='s', shape='exp'})` | `song.pulse(src, t, attack=0, decay=0.25, unit='s', shape='exp')` | src: events name; unit `'s'` or `'beats'`; shape `exp`, `linear`, `smooth` | 0..1 flash (weighted by item.strength / vel) | `pulse` |
| `song.osc(t, {shape='sine', periodBeats=1, phase=0})` | `song.osc(t, shape='sine', period_beats=1, phase=0)` | shape `sine`, `saw`, `square`, `triangle` | 0..1, 1 on the beat | `osc` |
| `song.beatPos(t)` · `beatPhase(t)` · `barPhase(t)` | `beat_pos` · `beat_phase` · `bar_phase` | t | `{value, in_pulse}` | `beat_pos`, `beat_phase`, `bar_phase` |
| `song.count(t)` | `song.count(t)` | t | `{eight_id, count 1..8, sub 0..3 (1 e & a), phase, accent, partial, lead_in, in_pulse}`; count/eight_id/phase null outside every count | `count_at` |
| `song.lyricAt(t)` | `song.lyric_at(t)` | t | `{line, word, progress, word_progress}`; line = the lyrics.json line containing t (latest start) **joined with** `singer` (character ids) and `voice_ids` from singing.json; word = the word of that line containing t; nulls when silent | `event_at` on lines/words |
| `song.vocalAt(t)` | `song.vocal_at(t)` | t | `{voiced, midi, hz, conf, pitch01, phrase_id, note}` (never NaN; midi/hz held through gaps) | `vocal_at` |
| `song.singerAt(t)` | `song.singer_at(t)` | t | `[{character_id, voice_id, lead_backing, line_id, mouth_open}]`, lead first, then voice number | `singer_at` |
| `song.meaningAt(t)` | `song.meaning_at(t)` | t | `{section_id, meaning, feel, emotion, palette_hint, movement_hint, camera_hint, characters_present, do_not, provenance}` for the section containing t (nulls/empty when none) | `event_at` on sections + meaning.sections |
| `song.spectrumAt(t)` | `song.spectrum_at(t)` | t | `Uint8Array(128)` / `np.uint8[128]`: the nearest row (clamped) | `hold_at` per band |
| `song.spectrumWindow(t, s)` | `song.spectrum_window(t, s)` | t, history s | `Uint8Array(k·128)` rows oldest first, k = round(100·s) + 1, zero rows outside the song | `spectrum_rows` |
| `song.textureData(ids, {layout:'wrap', width:1024, format:'r32f'})` | `song.texture_data(ids, width=1024, format='r32f')` | channel ids; format `r32f` or `r8` (value·255) | `{data, width, height, layout:[{id, row0, rows, n, rate}]}` | `texture_data` |
| GLSL `float mvhCurve(sampler2D tex, float t, vec4 info)` | - | info = (rate, n, width, row0); uses texelFetch + manual lerp | value equal to `curve.at(t)` | `texture_sample` |
| `song.vizState(t, fr)` | `song.viz_state(t, fr)` | t; **fr `{fps, frame0, early}` is mandatory** (or set once with `load(base, {fr})` / `load(path, fr=...)`; without either the call throws) | the viz `audio` fields (section 5 mapping) computed for the video frame containing t: onset flags, beat pulses and frame-pooled hit values depend on the frame length, so a 24/30 fps renderer must say so (viz scenes use `{fps: 60}`) | - |

Notes, visemes and sections need no helpers of their own: `events('notes.bass').at(t)`, `events('sections').at(t)`. Where segments overlap by
design use `allAt(t)`: `events('visemes').allAt(t)` returns one item per voice (filter on `voice_id`; the lead character's voice
is `singerAt(t)[0].voice_id`), `events('notes.other').allAt(t)` every note of a chord.
Cue lookups: `events('cues').next(t, {minTier: 2})`; a cue that merges several kinds lists them in `kinds[]` and `sources[]` (D37); the
tier-4 beat references resolve through `events('beats')`. `lyrics/lines.tsv` `singer` lists every character singing the line (`C1+C2`, D38).

---

## 10. Stage interface (`src/mvh/runner/spec.py`)

```python
STAGE = StageSpec(name, deps, env, version, override_keys, outputs, params,   # positional order frozen
                  params_by_profile=..., external_inputs=..., models=..., network=..., uses_ffmpeg=..., gpu=...,
                  trigger="analyze" | "on_demand", module=..., description=...)
def run(ctx: Ctx) -> StageResult
```

- **Registration by convention**: package `mvh.stages.<name>` with `STAGE` (named like the package) and `run`. `load_stage_specs()`,
  `check_dag()`, `topo_order()` build the DAG. `mvh.stages` is a namespace package (no `__init__.py`).
- **Outputs** (`Output(path, kind, schema, required, public, events, channels)`): `outputs=catalog_outputs("<name>") + (extra, ...)`.
  Kinds: curve | matrix | events | table | audio | midi | text | json. Path placeholders `{src}`, `{stem}`, `{sub}`, `{voice}`, `{fps}`.
- **Ctx** (read-only upstream + services): `spec, slug, params, profile, threads, device, offline, scratch, log, overrides, writer`;
  `upstream(stage)` (raises `UndeclaredDependency` for undeclared stages), `events(name)`, `curve(id)`, `audio(name='mix', sr=None,
  mono=False)` (`'mix'` for every stage; stems need their producer in deps; `'fast:<stem>'` for separate_fast stems), `model(id)`
  (must be in `STAGE.models`), `external(name)`, `http()` (network stages), `ffmpeg()`.
- **Writer**: `events(name, items, kind=None, fields=None, extra=None)`, `json`, `text`, `table(rel, rows, columns)`, `bytes`, `copy`,
  `audio(rel, samples[ch, n], sr)` (the parent encodes FLAC), `midi`, `curves(file_id, {id: array}, meta=None)`, `matrix(file_id, array)`.
  Undeclared paths raise `UndeclaredOutput`; JSON is schema-validated; writes are atomic.
- **StageResult**: `status` ok | degraded | skipped | failed; `summary` (manifest.summary.stages.<name>); `warnings`; `fallbacks`
  (machine tags like `sep:cpu`, `lead_vocals:=vocals`); `provenance` extras; `confidence`. Timings are added by the runner to run.json.
- **Workers** (`env="sep"`): the worker runs only inference: it reads the float32 WAVs listed in `job.json`, writes float32 WAVs and
  `result.json` (`mvh/envelope/stage_result`) to scratch; the parent encodes, validates, records provenance and caches.
- **Stubs**: every §3.2 stage exists as a walking-skeleton stub whose `run` copies its outputs from `tests/contract/synth/`
  (`MVH_FIXTURE_DIR` overrides; non-public outputs under `_intermediate/<stage>/`; a missing required file raises `MissingFixture`).

---

## 11. Consumed-by matrix (*generated*)

Every listed field is **frozen**. Targets: `events:<name>`, `file:<path>`, `curve:<id>`, `matrix:<file>`, `audio:mix` (any stage),
`audio:<stem>` (stems/<stem>), `audio:fast:<stem>`, `intermediate:<stage>/<path>` (cache only), `ext:<path>` (external input, hashed
into the cache key). `curve:*` / `events:*` = everything. Each consumed producer is in the consumer's deps (tested).

<!-- BEGIN GENERATED: consumed -->
| Stage | Env | Deps (§3.2) | Reads (target: frozen fields) |
|---|---|---|---|
| **ingest** | main | - | `ext:param:input` |
| **identity** | main | ingest | `file:meta/source.json`: tags, duration_s, file_name<br>`audio:mix` |
| **loudness** | main | ingest | `audio:mix` |
| **separate_fast** | main | ingest | `audio:mix` |
| **allin1** | main | separate_fast | `audio:fast:{stem}`<br>`intermediate:separate_fast/fast/separation.json`: stems |
| **separate_hq** | sep | ingest | `audio:mix` |
| **spectral** | main | ingest | `audio:mix` |
| **rhythm** | main | ingest, allin1, spectral | `audio:mix`<br>`intermediate:allin1/allin1.json`: bpm, beats, downbeats, beat_positions<br>`intermediate:allin1/activations.f32`<br>`events:hits.kick`: t, strength<br>`events:onsets.bass`: t, strength<br>`curve:flux.bass`<br>`curve:hits.kick_raw` |
| **dynamics** | main | loudness, spectral, rhythm | `curve:loud.short_term_lufs`<br>`curve:loud.momentary_lufs`<br>`file:meta/loudness.json`: integrated_lufs<br>`curve:bands.bass_db`<br>`curve:bands.kick_db`<br>`curve:timbre.centroid_hz`<br>`curve:timbre.slope_db_oct`<br>`curve:stereo.width`<br>`events:hits.kick`: t, strength<br>`events:onsets.mid`: t<br>`events:onsets.high`: t<br>`events:bars`: t, bar, d |
| **harmony** | main | ingest, rhythm | `audio:mix`<br>`events:beats`: t, beat_index, in_pulse<br>`events:bars`: t, bar |
| **stem_activity** | main | ingest, separate_fast, separate_hq | `audio:mix`<br>`audio:fast:{stem}`<br>`audio:{stem}`<br>`file:meta/separation.json`: stems, lead_backing_split |
| **drums** | main | separate_hq, stem_activity | `audio:drums`<br>`audio:drums_{sub}`<br>`curve:stem.drums.active`<br>`file:meta/stems.json`: stems |
| **instruments** | main | ingest, separate_fast, separate_hq, stem_activity | `audio:mix`<br>`audio:{stem}`<br>`audio:fast:{stem}`<br>`curve:stem.{stem}.active`<br>`file:meta/stems.json`: stems |
| **notes** | main | separate_hq, stem_activity, rhythm | `audio:{stem}`<br>`curve:stem.{stem}.active`<br>`file:meta/stems.json`: stems<br>`events:beats`: t, beat_index, bar, beat_in_bar<br>`events:bars`: t, bar, beats_in_bar<br>`file:meta/tempo.json`: bpm, meter |
| **structure** | main | allin1, rhythm, harmony, dynamics | `intermediate:allin1/allin1.json`: segments, labels<br>`intermediate:allin1/activations.f32`<br>`intermediate:allin1/embeddings.f32`<br>`events:bars`: t, d, bar, beats_in_bar<br>`events:beats`: t, beat_index<br>`curve:chroma.{pc}`<br>`events:dynamics`: t, d, level, rel_lu<br>`curve:dyn.intensity`<br>`curve:dyn.novelty`<br>`events:impacts`: id, t, strength<br>`events:silences`: id, t, d |
| **lyrics** | main | identity, separate_hq, stem_activity, structure | `file:meta/identity.json`: title, artist, album, duration_s<br>`audio:lead_vocals`<br>`curve:stem.lead_vocals.active`<br>`events:sections`: id, t, d, repeat_group<br>`ext:param:lyrics`<br>`ext:http:lrclib` |
| **mood** | main | ingest, structure | `audio:mix`<br>`events:sections`: id, t, d |
| **vocals** | main | separate_hq, stem_activity, instruments, rhythm | `audio:lead_vocals`<br>`curve:stem.lead_vocals.active`<br>`file:meta/stems.json`: stems<br>`events:vocal_style`: t, d, style<br>`events:beats`: t, beat_index<br>`file:meta/tempo.json`: bpm |
| **choreo** | main | rhythm, structure, drums, spectral, vocals, harmony, dynamics | `events:beats`: t, beat_index, bar, beat_in_bar, beats_in_bar, in_pulse, strength<br>`events:bars`: t, d, bar, beats_in_bar, n_beats, first_beat, pickup<br>`file:meta/tempo.json`: bpm, meter<br>`events:sections`: id, t, d, start_bar, n_bars, label, occurrence, repeat_group<br>`events:phrases`: id, t, d, start_bar, n_bars, section_id<br>`events:edm_roles`: id, t, d, role<br>`events:drum_hits`: t, drum, vel<br>`curve:drums.{drum}`<br>`events:onsets.bass`: t, strength<br>`events:onsets.mid`: t, strength<br>`events:onsets.high`: t, strength<br>`events:hits.kick`: t, strength<br>`events:notes.vocals`: t, d, midi<br>`events:vocal_phrases`: id, t, d<br>`curve:vocal.voiced`<br>`events:chords`: t, d, label<br>`events:dynamics`: t, d, level, mean_lufs<br>`events:impacts`: id, t, strength<br>`events:stops`: id, t, strength<br>`events:silences`: id, t, d<br>`events:decay_tails`: id, t, d, strength |
| **cues** | main | choreo, structure, dynamics, rhythm, drums | `events:counts`: id, t, len<br>`events:hit_points`: id, t, strength, rank<br>`events:holds`: id, t, d<br>`events:sections`: id, t, d, label<br>`events:phrases`: id, t, d<br>`events:edm_roles`: id, t, d, role, n_bars<br>`events:impacts`: id, t, strength<br>`events:stops`: id, t, strength<br>`events:silences`: id, t, d<br>`events:beats`: t, beat_index, beat_in_bar<br>`events:bars`: t, d, bar<br>`events:drum_hits`: t, drum, vel<br>`ext:overrides.json#cues.pinned` |
| **voices** | main | lyrics, separate_hq, stem_activity | `file:lyrics/lyrics.json`: lines, words, source<br>`audio:vocals`<br>`audio:lead_vocals`<br>`audio:backing_vocals`<br>`curve:stem.vocals.active`<br>`ext:meaning/intent.md` |
| **lipsync** | main | lyrics, voices, separate_hq | `file:lyrics/lyrics.json`: lines, words<br>`events:voice_spans`: t, d, line_id, voice_id<br>`file:meta/voices.json`: voices<br>`audio:lead_vocals`<br>`audio:vocals` |
| **meaning** | main | identity, lyrics, voices, structure, mood, vocals, instruments, cues | `file:meta/identity.json`: title, artist, album, credits, duration_s<br>`file:lyrics/lyrics.json`: lines, words, grade, instrumental, language<br>`events:voice_spans`: t, d, line_id, voice_id, conf, review<br>`file:meta/voices.json`: voices, n_voices<br>`events:sections`: id, t, d, label, occurrence, occurrence_label, repeat_group<br>`events:mood`: section_id, valence, arousal, tags<br>`file:meta/mood.json`: global<br>`file:meta/vocal_range.json`: present, lowest, highest, register<br>`file:meta/instruments.json`: summary, vocal_style<br>`events:moments`: rank, t, cue_id, kind<br>`events:cues`: id, t, kind, tier<br>`ext:meaning/intent.md`<br>`ext:meaning/authored.json` |
| **brief** | main | all analysis stages | `file:meta/source.json`: duration_s, palette<br>`file:meta/identity.json`: title, artist, album<br>`file:meta/tempo.json`: bpm, feel, meter, confidence, qa<br>`file:meta/key.json`: global<br>`file:meta/loudness.json`: integrated_lufs, lra_lu, true_peak_dbtp<br>`file:meta/vocal_range.json`: present, lowest, highest, p10, p90, register<br>`file:meta/instruments.json`: summary<br>`file:meta/separation.json`: degraded, lead_backing_split<br>`file:meta/stems.json`: stems<br>`file:meaning/meaning.json`: status, logline, characters, do_not, palette, sections<br>`file:lyrics/lyrics.json`: grade, lines<br>`events:sections`: id, t, d, label, occurrence_label, repeat_group, start_bar, n_bars<br>`events:dynamics`: t, d, level, mean_lufs<br>`events:instruments`: t, d, instrument<br>`events:vocal_phrases`: t, d, min_midi, max_midi<br>`events:hit_points`: id, t, strength, rank<br>`events:mood`: section_id, valence, arousal, tags<br>`events:edm_roles`: id, t, d, role<br>`events:counts`: id, t, section_id, len, partial<br>`events:grooves`: bar, groove_id<br>`events:holds`: id, t, d, kind<br>`events:moments`: rank, t, cue_id, kind, description<br>`events:cues`: id, t, kind, tier<br>`events:singing`: t, d, character_id, voice_id<br>`file:meta/voices.json`: voices<br>`file:meaning/orphans.json`: orphans<br>`events:visemes`: t |
| **frames** | main | all analysis stages | `curve:*`<br>`events:*` |
| **viewer** | main | all analysis stages | `curve:*`<br>`matrix:spectrum128`<br>`events:*`<br>`file:lyrics/lyrics.json`: lines, words<br>`file:meaning/meaning.json`: sections, characters, do_not<br>`audio:preview`<br>`audio:{stem}` |
<!-- END GENERATED: consumed -->

---

## 12. brief.md

Written by the brief stage; <= 4k tokens (target 2.5k), enforced by the gate (token estimate: characters / 4). Times as seconds and
`m:ss.s`. Every number can be traced to a file (the brief names it once per block, e.g. `(meta/tempo.json)`). Lyric quotes <= 10 words.
Order:

1. **Status line**: `meaning: user|draft|pending · lyrics: grade A-D|none · stems: hq|degraded · visemes: yes|no · flags: ...`
   (low-confidence flags from manifest.status.flags; orphaned meaning claims produce a warning here).
2. **Header table**: title, artist, duration, BPM and feel, meter, key (with confidence), integrated LUFS and LRA, vocal range
   (low-high, register), instrumentation (top instruments by coverage).
3. **Meaning**: logline; characters table `| ID | description | voice | sections |`; the do-not rules **verbatim** (the user's words);
   palette swatches (hex). When meaning is pending: a single line pointing to `meaning/interview.md` and the SKILL rule.
4. **Section cue sheet**: one row per section `| ID | t (s, m:ss.s) | bars | label | repeat group | energy / loudness class | instruments |
   vocals (active, range) | notable hits | lines (L007-L012) | mood | feel / meaning |`. When the brief would overflow, repeats collapse
   into one row per repeat group (`S03, S06, S09 (chorus A)`).
5. **Choreography**: counts per section (n eight-counts, partials), the dominant grooves (G ids, swing, syncopation), the strongest hit
   points (H ids), holds.
6. **Top 15 moments**: `| rank | t | cue | kind | description |` from `events/moments.json`.
7. One line: `Loaders and file catalogue: SKILL.md and CONTRACT.md (lib/mvh.js, lib/mvh_load.py).`

`mvh brief --section S05` prints the same blocks for one section (<= 1.5k tokens): its rows, lines (ids only unless lyrics are allowed),
counts, hits, cues, meaning.

---

## 13. Change control

| Class | Examples | Process |
|---|---|---|
| **Free** | params, models, internal code, thresholds, new tests | none |
| **Additive** (minor bump, listed in the module report under "contract additions") | a new *optional* field in an item or document your stage produces (documented in `fields`/the schema); a new *optional* file, events name or curve channel owned by your stage (declare it in `STAGE.outputs`; the integrator folds it into `catalog.py`/`registry.py` in W3); new values in open vocabularies (section labels, instrument slugs, mood tags, cue kinds) | no approval; never consumed by another module until merged |
| **Change request** (in the agent's report; the orchestrator decides) | anything in the envelope schemas (manifest, curves index, events envelope, provenance); renaming, removing or retyping a frozen field; units, resample policy, norm method; ID formats; time/frame rules; a stage's deps, env or producer of a file; making a required output optional or the reverse; anything in the Consumed-by matrix; `pyproject.toml` and locks | do not implement until approved; the integrator applies approved CRs in W3 |

A frozen field may never silently change meaning. If a producer cannot fill a frozen field it writes `null` only where the schema allows
it, otherwise it raises a CR. `python -m mvh.contract.gen --check` and `python -m mvh.contract.golden --check` must pass after every
change to `src/mvh/contract/`.

---

## 14. Decisions

Where PLAN.md was silent or self-contradictory, this contract decides (each is also listed in the W1a report as a deviation):

- **D1 `meta/` documents.** §4.1 has no home for per-stage scalars (identity, decode facts, loudness, tempo/meter/QA, key, structure,
  stems, separation, instruments, vocal range, mood, voices, grooves); they go to `meta/<topic>.json`. The manifest summary is assembled
  from them (and from `StageResult.summary`).
- **D2 Tables are produced by choreo.** §4.3 says bars carry section_id, phrase_id and groove_id, but rhythm (which writes
  `events/bars.json`) runs before structure and choreo. `events/bars.json` carries rhythm fields only; the joined links live in
  `tables/bars.csv` (and beats.csv, sections.csv), written by choreo, which depends on rhythm, structure and dynamics.
- **D3 Singers are joined by meaning.** The lyrics stage runs before voices and before the user's character mapping, so
  `lyrics/lyrics.json` lines carry `speaker_hint` (from source labels), not `singer`. The meaning stage writes `events/singing.json`
  and `lyrics/lines.tsv` (with the `singer` column); `lyricAt` joins singer/voice ids at read time.
- **D4 No back-links to cues.** "Dynamics events carry a cue_id" (§5) is impossible in the DAG (cues is downstream). Dynamics events
  carry their own ids (`I`, `X`, `Z`, `Y`) and cues cite them via `source {file, id}`; reverse lookups are a helper concern.
- **D5 `voice_id`, not `voice`.** singing.json, voice_spans, visemes and lines use `voice_id` (§8 writes `voice`); `singer` is a
  character id.
- **D6 Vocal notes come from the vocals stage.** `events/notes.vocals.json` and `notes/vocals.mid` are produced by vocals (f0-based);
  notes produces bass, piano, guitar and other (`notes.mid` has those four tracks), because notes does not depend on vocals in §3.2.
- **D7 Authored drafts at `meaning/authored.json`.** §8 calls both the agent's draft and the merged result `meaning.json`; to never
  overwrite authored input, drafts go to `meaning/authored.json` and the merged output is `meaning/meaning.json`.
- **D8 Every stage may read the canonical mix.** Every stage transitively depends on ingest; `ctx.audio('mix')` is allowed everywhere.
  Direct deps stay exactly as in §3.2 (structure, for example, needs no ingest edge to compute MFCCs).
- **D9 Early mode shifts the sampling instant** to the window centre t_n + 1/(2F) ("all three rules shift together"). Numeric fps are
  literal (23.976 is not snapped to 24000/1001).
- **D10 One membership rule** for events and curve samples (`frame_of`), with EPS = 1e-9 frames, and the flash rule for event-driven
  `max` channels; together they make "a flash and its event land on the same frame" exact at <= 100 fps.
- **D11 Virtual beats are stored.** The no-pulse virtual grid is written into beats.json (`in_pulse: false`); the helpers only extrapolate
  before the first and after the last beat. in_pulse is false outside [first beat, last beat).
- **D12 Pickup bar = bar 0**, its beats numbered at the end of the bar (a one-beat pickup in 4/4 is beat_in_bar 4), so bar_phase reads
  the pickup as the tail of a virtual bar.
- **D13 Counts are addressed by beat position.** counts.json items carry `start_beat`, `len`, `first_count`; `E000` is the synthesised
  lead-in with `first_count` 5 covering the 4 beats before E001 (start_beat may be negative). Pickup beats before the lead-in have no count.
- **D14 Sub-counts** are 16ths in the order `1 e & a` (sub 0..3); PLAN's "1 & e a" is read as an informal list.
- **D15 Tier-4 beat cues** are items in cues.json that carry only reference fields (`kind: beat`, `source = beat:<i>`, strength and
  lead-in null) - references, not copies.
- **D16 `vocal.mouth_open` always exists** (max over voices); `vocal.mouth_open.<V>` channels are added when there are >= 2 voices.
- **D17 `backing_vocals` always exists** (digital silence when `lead_backing_split=false`); drum sub-stems are optional.
- **D18 Cache-only intermediates.** separate_fast stems, the canonical WAV and allin1 activations/embeddings are not in the song folder;
  fixtures hold them under `_intermediate/<stage>/`.
- **D19 Final stages.** brief and viewer depend on every analysis stage; frames is `trigger="on_demand"` and depends on every analysis
  stage too (it reads curves and events).
- **D20 The runner packs curve files** from the channels stages hand to `writer.curves`; stages never write `curves/*` directly. The
  runner also writes manifest, run.json, curves/index.json, lib/ and schema/ (finalize step).
- **D21 spectrum128 stores viz values**, not linear dB (u8/255 = viz band value; scale 1/255, offset 0), because spectrumAt must equal
  viz `bandBytes`; the dB mapping parameters are in the registry description and `band_edges_hz`.
- **D22 Floors.** dB channels floor at -120 dBFS and LUFS at -70 LUFS; inf is invalid.
- **D23 `mix.wav` twin.** mix.flac always exists; when the decode exceeds full scale, `audio/mix.wav` (float) is written too and
  `manifest.timebase.soundtrack` / `meta/source.json.soundtrack` name it. Stems follow the same rule.
- **D24 Extra ID kinds** (`R`, `H`, `O`, `I`, `X`, `Z`, `Y`, `VP`, `T`, `LG`, letter repeat groups) and reference keys
  (`beat:<i>`, `bar:<n>`) so every cited item is addressable.
- **D25 Dotted events names**; visemes and phonemes keep the §4.1 paths under `lipsync/` and are resolved by name through the manifest.
- **D26 StageSpec keyword extras** (`params_by_profile`, `external_inputs`, `models`, `network`, `uses_ffmpeg`, `gpu`, `trigger`,
  `module`, `description`) carry the NF2 cache-key inputs; the §3.2 positional fields are unchanged.
- **D27 Overrides are anchored by time** for structure (IDs move when boundaries move) and by id for lyrics and voices.
- **D28 Helper semantics not spelled out in §4.5** are fixed here: `events.at` = latest-starting segment containing t; `next` strictly
  after, `prev` at or before; `between` half-open; `minTier` keeps tiers 1..minTier; `pulse` defaults (attack 0, decay 0.25 s, exp to 1%
  at one decay length); `osc` peaks on the beat; `spectrumWindow` has k = round(100·s) + 1 rows.

**W1b runtime decisions** (the runtime builder; additive, listed in docs/build/reports/runtime.md as deviations):

- **D29 `ctx.worker` for env='sep' stages** (additive `Ctx.worker` in `spec.py`). Every stage's `run(ctx)` runs in a main-env
  child process; an env='sep' stage calls `ctx.worker(inputs, params=, models=, variants=)`, which writes the inputs as float32
  WAVs, launches `envs/sep/.venv-<variant>/Scripts/python.exe -X utf8 -m mvh.worker <stage> job.json` (`PYTHONPATH=<repo>/src`,
  ffmpeg bin first on PATH, thread variables, `HF_HUB_OFFLINE=1`, kill-on-close Job Object) and returns a `WorkerResult`
  (`.outputs`, `.read(rel)`, `.variant`, `.fallbacks`). The worker calls `mvh.stages.<stage>.worker.run_job(job, out_dir)` and
  writes `result.json` (`mvh/envelope/stage_result`). Variant order: rocm, then cpu (`MVH_SEP_VARIANTS`, config.json
  `sep_variants` or the stage param `variant_order`); using a later variant adds the fallback `sep:<variant>`. By default
  `ctx.worker` holds one heavy slot (plus `gpu.lock` for rocm) for the whole worker run; `hold_slot=False` lets the worker take
  per-model slots itself.
- **D30 Cache layout and publication.** `out/<slug>/.cache/<stage>/<key>/` holds every output of the stage (public ones at
  their song-folder paths, cache-only ones at their declared paths) plus the reserved `_mvh/` (done.json, curves, matrices).
  Public outputs are copied into the song folder (files of 8 MiB or more are hard-linked, size-checked on a cache hit; D43); `.cache/_published.json` tracks them, and a file a stage
  no longer produces is removed on its next publish. Network stages: the cache dir is named by the key without responses
  (`pre_key`); the effective key that downstream keys and provenance use is sha256(pre_key + hashes of the responses used).
- **D31 Threads and slots.** n (threads per stage) is fixed: `--threads` / `MVH_THREADS` (default 3), clamped to 6 for heavy
  stages, and is part of the key. Concurrency, not n, adapts to load: stages run while the sum of their n fits the core budget
  (`--cores`, default 8). The runner takes a heavy slot for non-stub main-env stages that declare models (a stub = a version
  whose prerelease contains `stub`); `MVH_HEAVY_LOCKS=0` / `--no-heavy-locks` disables slots.
- **D32 Ingest and lyric tags (NF5).** Tags whose key starts with `lyrics`, `unsyncedlyrics`, `syncedlyrics`, `uslt`, `sylt` or
  `lyric` are not copied into `meta/source.json.tags`; their text goes to the cache-only optional output
  `embedded_lyrics.json` of ingest. `meta/source.json` gains the optional fields `missing_samples` (container duration minus
  the decode, e.g. 2291 for Versatile) and `embedded_lyrics_tags` (key names only).
- **D33 Writer rules.** After `run(ctx)` returns, the runner re-stamps the provenance of every envelope the stage wrote (events,
  and JSON documents whose schema has a `provenance` property, which the writer fills in automatically) with the
  StageResult extras, the fallbacks, the effective key and the device actually used. `overrides_applied` defaults to every
  override key handed to the stage unless the stage reports its own list. Curve channels must have exactly
  ceil(n_samples * rate / sample_rate) frames. A float `.wav` twin is written next to any declared `.flac` when |x| > 1.
- **D34 Manifest assembly.** `files[]` lists the published stage outputs, the curve files and `curves/index.json`, `lib/*`, and the
  user inputs that exist (stage `_user`); `schema/**` is copied (`schema/<group>/<name>.schema.json`) but not listed. Each
  `files` entry is one compact line. When the manifest would exceed about 2.9k tokens the largest `summary.stages` entries are
  dropped first and `manifest:stage_summaries_trimmed` is flagged. `status.stages` covers the analyze stages (and on-demand
  stages that ran); `status.stems` = separation present and not degraded.
- **D35 CLI.** Core verbs `analyze`, `status`, `validate`, `doctor`, `models`; module verbs come from optional
  `mvh.stages.<name>.cli` modules exposing `register(subparsers)` (each parser sets `func(args) -> int`).
  `mvh analyze <song-folder>` re-runs with the input recorded in `.cache/_run.json`.
- **D36 `mvh status` semantics.** done (cached for the current key); stale (a previous run exists and its key inputs changed, or
  an upstream is not current; the reason names the changed inputs, e.g. `overrides changed: rhythm.bpm`); pending (never run,
  or an upstream never ran); failed (the last attempt for the current key failed; `.cache/<stage>/failed.json`).
- **D37 One cue per time.** `events/cues.json` holds at most one cue per instant. Candidates whose `t` rounds to the same microsecond are merged
  (`conventions.merge_cues`): `tier` = the best tier, `kind` = the highest-priority kind (drop, build_start, breakdown, section, stop,
  silence, impact, phrase, hit_point, downbeat, beat, pinned), optional `kinds[]` and `sources[]` list every merged candidate in that order
  (`kinds[0] == kind`, `sources[0] == source`), `strength` = the largest, `lead_in_s` = the primary's. So `next(t, minTier)` (strictly after
  t) reaches every cue by stepping `t = cue.t`, and `prev`/`next` are symmetric. Moments reference the merged cue. (Review w1b-r-contract F1.)
- **D38 `lines.tsv` singer cell.** `singer` lists every character singing the line, lead first (then by voice number), joined with `+`:
  `C1`, `C1+C2`. Pattern `^C[1-9]\d*(\+C[1-9]\d*)*$`, or empty. (F2.)
- **D39 One producer per path.** A `{src}` output pattern never claims a path another stage declares exactly: `notes.{src}` outputs are
  restricted to bass, piano, guitar and other (`Output.restrict`); `notes.vocals` and `notes/vocals.mid` belong to `vocals` (D6).
  `check_dag` rejects two stages declaring or matching the same path; `publish` never deletes a path another stage publishes. (F3.)
- **D40 vizState needs a frame rule.** `vizState(t, fr)` / `viz_state(t, fr)` throws without `fr` unless the song was loaded with a default
  (`load(base, {fr})` / `load(path, fr=...)`). There is no silent 60 fps default. (F4.)
- **D41 `allAt`.** `events(name).allAt(t)` / `.all_at(t)` returns every item with d > 0 containing t, sorted by t then file order
  (`conventions.event_all_at`, golden rows `events.all_at`). `at(t)` keeps its latest-start rule. (F5.)
- **D42 Runtime error text (NF5).** Schema error messages never quote string, object or array values (`schemas.safe_message`): they name the
  JSON path and the rule (`lines/0: is not of type 'object'`). Numbers, booleans and null keep jsonschema's wording.
- **D43 Publication by copy.** Public outputs below 8 MiB are copied from the cache, so an editor that saves a song-folder file in place
  cannot rewrite the cache entry; the next run re-publishes the clean copy. Larger files (stems, mix) are hard-linked; on a cache hit the
  runner checks every output's size against `done.json` and re-runs the stage on a mismatch ("cache entry damaged"). A published file held
  open by another program (Windows) is kept at its previous version with a warning in `run.json`; the stage stays cached and the run
  finishes. A publish problem never deletes a finished cache entry.
- **D44 Status predicts analyze.** `mvh status` computes the keys the next `mvh analyze` would use: threads come from `--threads` or
  `MVH_THREADS` (default 3), not from the last run, so a changed thread count shows `stale` with `threads changed: 3 -> 4`.
- **D45 Default slugs and folders.** A default folder (no `--out`, no `--slug`) belongs to one input. Titles with no ASCII letters (CJK,
  Cyrillic, Greek, Arabic) get a short hash of the input path (`song-1a2b3c`), and a folder whose `_run.json` records another input is never
  reused: the slug gets the hash suffix instead.
- **D46 Separator models.** `AUDIO_SEPARATOR_MODEL_DIR` is always `<models>/separator` (where `mvh models fetch` puts the SHA-pinned
  files). The runner sets it for stage children and the sep worker (audio-separator lets it override `model_file_dir`), the env scripts export
  it, and `mvh doctor` fails when the variable points at a folder lacking those files. For `HF_CACHE_IDS` models, `fetch` re-links an
  HF snapshot that is not the verified file, and `verify`/`doctor` check the snapshot too.
