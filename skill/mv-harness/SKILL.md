---
name: mv-harness
description: Use when building a music video (Remotion, three.js/WebGL, Blender, ComfyUI/Deforum, ffmpeg, the viz/ scenes) from a song analysed by mv-harness, or when asked to analyse a song for a video. Gives choreography (eight-counts, grooves, hit points, holds), characters and per-singer lip-sync, lyrics with word timing, cues to cut on, and the user's meaning per section, all on one clock. Read brief.md first; load data through lib/, never by pasting files into context.
---

# mv-harness: one song folder -> an art-piece music video

mv-harness analyses **one song** and writes `out/<slug>/`: timestamped metadata for choreography, characters and
stylisation. It does not make videos; you do, in any technology, from this folder. The user authors the meaning.

## 1. Run it (only if the folder does not exist yet)

```powershell
Set-Location <mv-harness repo>; . .\scripts\mvh-env.ps1
uv run --frozen --no-sync mvh analyze "<song.flac>" --out out\<slug>     # add --lyrics song.lrc if you have them
```
stdout is one JSON line `{manifest, brief, viewer, warnings, pending}`. Other verbs: `mvh status|validate|view|brief|meaning|frames <folder>`.

## 2. Read in this order (context budget)

1. **`brief.md`** (<= 4k tokens): status line, header, meaning, characters, one row per section, choreography, top 15 moments.
   Every number in it names its source file.
2. **`mvh brief out/<slug> --section S05`** (<= 1.5k tokens) when you work on one section (lines, counts, hits, cues, meaning).
3. **`lyrics/lines.tsv`** only if the video shows or acts on words: `id t d section_id singer repeat_group grade text`;
   `singer` = characters on the line, lead first (`C1+C2`).
4. `references/CONTRACT.md` **only the parts you need**: §2 time and frames, §3 IDs, §4 values, §9 helpers.
   Do not read the whole contract (25k tokens) or `manifest.json` beyond `status`/`summary`.

**Never cat curves, events or tables into context.** They are large (100 Hz curves, thousands of events). Load them in
code with `lib/mvh.js` (ES module, no deps) or `lib/mvh_load.py` (numpy), which are copied into every song folder.
Recipes per engine: `references/RECIPES.md`.

## 3. The meaning rule (the user is the authority)

- Status line `meaning: pending` and `meaning/intent.md` empty or missing: **show the user the questions in
  `meaning/interview.md` and wait for their answers.** Write their answers to `meaning/intent.md` only in their words
  (free text, or the YAML template at the end of the interview).
- Draft only after that, or when the user asks: follow `meaning/request.md`, write **`meaning/authored.json`** with
  `"status": "draft"` (schema `meaning/schema.json`; every claim typed lyric|audio|external|speculative and cited by
  id or time; quotes <= 10 words), then run `mvh meaning out/<slug>`. Never overwrite the user's claims; conflicts go
  to `open_questions`. `mvh meaning out/<slug> --draft anthropic` drafts through the Claude API if the user wants that.
- **Do-not rules** (`meaning.json do_not`, in brief.md verbatim) are hard constraints on everything you render.
- `meaning.json` `notes` and `references` are the user's other words (free text not filed under a field; counted in
  brief.md). Read them before you design: they are direction, not drafts.
- `meaning: draft` = an agent's suggestion: say so to the user before building on it. `user` = authored.
- A `user` section or character can still hold draft text: `meaning.json` `sections[].field_sources` and
  `characters[].field_sources` (and the top-level `field_sources`, incl. `perspective.narrator`/`.addressee`) give
  each field's origin, `user` or `draft`.
  Treat every `draft` field as a suggestion, whatever `provenance.status` says (brief.md marks them `(draft)`).
- Never edit generated files. Corrections (beats, sections, lyric timing, singers) go through the viewer
  (`mvh view out/<slug>`) or `overrides.json`, then `mvh analyze out/<slug>` re-runs only what changed.

## 4. Time, frames, IDs (the rules that bite)

- **Soundtrack = `audio/mix.flac`** (or `audio/mix.wav` when the manifest says so); stems are sample-aligned. Never the
  original file: every time is seconds from the first sample of mix.flac.
- Frame rule `{fps, frame0 = 0, early = false}`; NTSC is `[24000, 1001]` (23.976 is taken literally). Blender: `frame0: 1`.
  Frame n shows time `timeOf(n, fr)`; an event belongs to `frameOf(t, fr)`, the same frame as its curve flash.
- Curves are 0..1 with absolute twins (`bands.bass` / `bands.bass_db`); helpers never return NaN.
- IDs link downstream to upstream: section `S03`, phrase `P02`, eight-count `E012`, line `L007`, word `L007.03`, voice `V2`,
  character `C1`, cue `Q0034`, hit point `H004`, hold `O002`. Repeats share a `repeat_group` (sections) or `LG01` (lines).

## 5. What to use for what

| Want | Use |
|---|---|
| Dance on the beat / counts | `song.count(t)` -> `{eight_id, count 1..8, sub, accent}`; `song.beatPhase(t)`; `events('grooves')` per bar |
| Hits and poses | `events('hit_points')` (ranked), `events('holds')`, `song.pulse('drum_hits', t)`, `curve('choreo.accent')` |
| Cuts and camera | `events('cues').next(t, {minTier: 2})` (tier 1 sections/drops/builds ... 4 beats), `lead_in_s` to anticipate |
| Who sings, lip-sync | `song.singerAt(t)` -> `[{character_id, voice_id, lead_backing, line_id, mouth_open}]`; `curve('vocal.mouth_open.V2')` |
| Karaoke / words | `song.lyricAt(t)` -> line, word, progress; `lyrics/lyrics.json` |
| Palette, mood, intent | `song.meaningAt(t)` -> feel, emotion, palette_hint, movement_hint, camera_hint, characters_present, do_not |
| Energy | `curve('dyn.intensity')`, `curve('loud.short_term')`, `events('dynamics')`, `events('edm_roles')` (build/drop) |
| Melody and pitch | `song.vocalAt(t)` (pitch01, midi), `events('notes.bass')`, `events('chords')` |
| Spectrum for shaders | `song.spectrumAt(t)`, `song.textureData(ids)` + `lib/mvh.glsl` |
| Non-JS/Python tools | `mvh frames out/<slug> --fps 24 [--frame0 1] [--curves "*"] [--format deforum]` -> `frames/24fps.csv` (`frames/24_f1fps.csv` with `--frame0 1`) |

## 6. Check the result

Open `viewer.html` (read-only) or `mvh view out/<slug>` and scrub the lanes against your render. Respect the flags in
the status line: low-confidence singers (`singers:review`), lyrics grade C/D, `degraded:*` stages and `fallback:*`
mean the data there is shaky; prefer coarser cues (sections, tier 1-2) where it is.
