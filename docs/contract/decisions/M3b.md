# M3b contract decisions (notes, vocals, instruments) — builder-m3b

Additive changes and interpretations made by the M3b stages. Nothing here renames, removes or retypes a frozen field.
The W3 integrator folds the additive items into `catalog.py` / CONTRACT.md.

## Interpretations

- **I-M3b-1 instrument vocabulary.** `inst.<slug>` / `events/instruments.json.instrument` use the open vocabulary of
  `src/mvh/stages/instruments/vocab.py` (28 CED-backed slugs: voice, choir, beatbox, drums, drum_machine, percussion, bass,
  guitar, electric_guitar, distorted_guitar, acoustic_guitar, folk_strings, piano, electric_piano, organ, harpsichord,
  synth, synth_fx, strings, brass, woodwinds, saxophone, mallets, bells, harp, harmonica, accordion, turntable) plus the
  CLAP sub-types synth_pad, synth_lead, synth_arp, synth_bass and user terms `term_<slug>`. A curve is written for every
  slug (zeros when absent), so agents can rely on `inst.voice` etc. existing. `meta/instruments.json.vocabulary` lists them.
- **I-M3b-2 fusion rule.** For an instrument with a dedicated separator stem (voice -> vocals, drums, bass, guitar, piano):
  `p = s * (w + (1 - w) * tag) + (1 - s) * min(tag, 0.6)`, s = fraction of the 4 s window in which the stem is active,
  tag = CED evidence (max over the mix and the slug's stems, scaled lo..hi per slug), w = belief in the stem alone
  (drums/bass 0.7, guitar 0.45, piano 0.3, **voice 0.2**: a vocals stem alone is not a voice). Other slugs: p = tag;
  sub-types are capped by their parent. Segments: hysteresis 0.5 / 0.35, >= 2 s, gaps <= 2 s bridged; `evidence` = both
  (stem >= 0.5 and tag >= 0.5) | stem | tagger; `stem` = the anchor stem, or the stem the tag came from (null = mix).
- **I-M3b-3 1 Hz grid.** `instruments_1hz` sample i is the 4 s window [i - 2, i + 2) s (zero-padded at the edges), matching
  "sample i centred at i / rate". Segment times are frame-accurate (+-0.5 s) and snapped to the anchor stem's 100 Hz
  activity edges within 1.5 s.
- **I-M3b-4 CLAP curves are relative.** `inst.synth_*` = `inst.synth` x the softmax share (T = 0.01) of CLAP similarity to
  four sub-type prompts; `inst.term_*` = (cosine to the user term - mean cosine to neutral prompts) / 0.1, clipped. Their
  index entries carry a `description` saying "RELATIVE (CLAP) ... not a calibrated probability". They never produce
  segments or summary rows.
- **I-M3b-5 vocal style.** `vstyle.<s>` = `inst.voice` x the style share, so `sum(vstyle.*) <= inst.voice`. Shares come
  from CED on lead_vocals (singing / speech / rapping label groups); speech over a hip-hop context (CED Rapping or Hip hop
  music on the mix, per frame or the song's p75) counts as rap; a SwiftF0 pitch-sustain ratio on the lead stem moves
  weight to singing when notes are held (style only, never presence). `meta/instruments.json.vocal_style.shares` are the
  time shares of the `vocal_style` segments (so `dominant` agrees with the events); `dominant = "none"` with no voice.
- **I-M3b-6 notes conf / vel.** basic-pitch notes: `conf` = basic-pitch mean frame activation of the note; piano CRNN notes:
  0.85. `vel` = stem level at the onset (peak RMS in 60 ms), normalised per source p05..p99 -> 0.15..1, blended 80/20 with
  the model amplitude (CRNN: its own velocity / 127). Vocal notes: `conf` = mean pitch confidence x pitch stability.
- **I-M3b-7 MIDI tempo map.** tick 0 = t 0; every beat of events/beats.json is on a quarter-note boundary (the lead-in
  before the first beat is a whole number of quarters; a beatless gap longer than 1.5 median intervals spans
  round(gap / median) quarters); one `set_tempo` per beat whose interval changes; time signatures from bars
  (`beats_in_bar`/4). Note seconds survive within one tick. Tracks: `tempo map`, then bass, piano, guitar, other (notes.mid)
  or vocals (vocals.mid). Empty sources keep an empty track in notes.mid; `notes/<src>.mid` is written only when the source
  has notes (`notes.json.sources.<src>.midi = null` otherwise).
- **I-M3b-8 piano gate.** the piano floor is in SECONDS of activity (`notes.piano_min_active_s`, default 1.0; fixer-m3b, was 10 % of the song). piano_transcription runs when the stem is above the floor AND CED reports
  piano over its active windows (mean >= 0.05 or p95 >= 0.25, max of piano stem and mix). An active piano stem without
  piano tags is transcribed by basic-pitch (fallback tag `piano:basic_pitch`, status degraded); a stem active under the floor gets
  no notes and a warning.
- **I-M3b-9 vocal presence and range.** Voiced = RMVPE conf >= 0.3 AND lead stem active AND level > max(-55 dBFS, p99 - 35)
  AND `inst.voice` >= 0.35 (interpolated to 100 Hz). `present` = >= 8 voiced s and (>= 8 s of statistics frames, or a
  rap/speech-dominant lead with >= 15 spoken s). Statistics frames = every voiced frame for a singing-dominant lead (CED
  tags low sung verses as speech), only singing-labelled frames for a rap/speech-dominant lead; stats are null when those
  are < 8 s (rap: present true, range null). `lowest`/`highest` = the lowest/highest MIDI pitch held >= 0.3 s in total in
  notes >= 0.15 s (same-pitch notes split by a consonant gap <= 0.12 s count as one), with the time of its longest
  occurrence. `register` from CED female/male share on sung windows and the median sung pitch (male: < 50 bass, < 58
  baritone, else tenor; female: < 64 alto, < 69 mezzo, else soprano), low confidence.
- **I-M3b-10 pitch01 ease.** Exact `(midi - p2)/(p98 - p2)` (clipped) on voiced frames; held through gaps; the last
  min(150 ms, gap) of each gap ramps linearly to the next voiced value; before the first voiced frame the first value;
  0 everywhere when nothing is voiced. `norm.lo/hi` = p2/p98 of all voiced frames (also for rap, where meta stats are null).
- **I-M3b-11 vocal phrases.** Voiced runs joined across rests < 0.45 s, >= 0.3 s long; `min_midi`/`max_midi` are the lowest /
  highest note medians in the phrase (5th/95th percentile of frames when no note), `mean_db` the lead-stem RMS.

## Additive fields (optional; minor bump)

- `meta/vocal_range.json`: `basis` ("voiced frames" | "sung frames (rap/speech-dominant lead)" | null),
  `spoken_pitch` {seconds, p10, median_midi, p90} over speech/rap-labelled voiced frames, `style` (dominant style seen by
  vocals). 
- `meta/instruments.json.top_tags` (already optional in the schema): top 10 CED mix labels by mean probability.
- index-entry `description` overrides for the CLAP-derived `inst.*` channels.

## Reads beyond the Consumed-by matrix (CR-M3b-1 below)

- vocals reads `curve:inst.voice` (instruments, a declared dep) for the presence gate.
- notes, vocals and instruments run CED themselves where needed (notes: piano gate; vocals: male/female share), because
  the DAG gives notes no instruments dependency.

## Human-correction hooks (stage params; no frozen-contract change)

- **I-M3b-12.** `overrides.json` has no M3b section (frozen), so the corrections are stage params (`mvh analyze --param`),
  which the runner hashes into the cache key and records in provenance:
  - `notes.piano_mode` = `"auto"` (default: the I-M3b-8 gate) | `"crnn"` (force piano_transcription) | `"basic_pitch"` |
    `"off"` (no piano notes).
  - `vocals.present` = `null` (default) | `true` | `false`: forces `meta/vocal_range.json.present`; when forced true the
    range statistics need only 1 s of statistics frames.
  - `vocals.style` = `null` | `"singing"` | `"speech"` | `"rap"`: replaces the dominant lead style used for the statistics
    basis (e.g. a rapper who also sings hooks).
  - `instruments.vocabulary` = list of user terms -> `inst.term_<slug>` RELATIVE CLAP curves (I-M3b-4).
  Each applied correction is written to the stage's provenance notes ("set by the user").

## Change requests (for the W3 integrator)

- **CR-M3b-1 vocals <- lyrics.** PLAN/brief want vocal presence to combine stem activity, the tagger AND lyrics coverage.
  `lyrics` is not a dep of `vocals`. Adding it would not create a cycle (lyrics reads no vocals output), but lyrics is
  a heavy, possibly network-backed stage and vocals would wait for it. Proposal: add an optional read of
  `file:lyrics/lyrics.json` (`lines[].t/d`, `source`) to vocals, or let the `brief`/`meaning` stage combine
  `vocal.voiced` with lyric line coverage. Until then presence = activity x level x `inst.voice` x RMVPE.
- **CR-M3b-2 notes <- instruments.** The piano gate runs CED itself because notes has no instruments dep (one extra CED
  pass over piano stem + mix, ~10 s). Adding `instruments` as a dep of notes (read `curve:inst.piano`) removes it.
- **CR-M3b-3 overrides schema.** Promote the I-M3b-12 params to `overrides.json` keys (`notes.piano_mode`,
  `vocals.present`, `vocals.style`, `instruments.vocabulary`) so the viewer's edit mode can set them.
- **CR-M3b-4 vocal_range additive fields** (`basis`, `spoken_pitch`, `style`) and the `description` override for the CLAP
  `inst.*` channels: fold into catalog.py (minor bump).
