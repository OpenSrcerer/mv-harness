---
name: mv-harness
description: Use when building a music video (Remotion, three.js, Blender, ComfyUI, ffmpeg, the viz/ scenes or any engine) from a song analysed by mv-harness, or when asked to analyse a song for a video. Gives choreography (eight-counts, grooves, hit points, holds), characters and per-singer lip-sync, lyrics with word timing, cues to cut on, and the user's meaning, all on one clock. Plans the video first (concept, storyboard, tools, agent split) and builds only after the user approves the plan. Read brief.md first; load data through lib/, never by pasting files into context.
---

# mv-harness: one song folder -> an art-piece music video

mv-harness analyses **one song** into `out/<slug>/`: timestamped metadata for choreography, characters and
stylisation. It does not make videos; you do, in any technology, from this folder. The user authors the meaning.

**Order: status -> read -> meaning -> plan -> the user's yes -> build -> check.** Never build before the user has
approved the plan (§4 below).

## 1. Run it, check it, pack it

```powershell
# <repo> holds skill\mv-harness (if linked: (Get-Item <skill folder>).Target)
Set-Location <repo>; . .\scripts\mvh-env.ps1
uv run --frozen --no-sync mvh analyze "<song.flac>" --out out\<slug> [--lyrics lyrics.txt]   # new song only
uv run --frozen --no-sync mvh status out\<slug>          # ALWAYS first: anything stale?
uv run --frozen --no-sync mvh analyze out\<slug>         # refresh: re-runs only what changed
uv run --frozen --no-sync mvh pack out\<slug> <project>\public\song   # what a page/video project loads
```
`analyze` prints one JSON line `{manifest, brief, viewer, warnings, pending}`. **If `status` shows a stale stage**
(the user edited intent.md or the viewer), refresh before reading: the brief is older than the user's answers. Never edit generated files; it never touches `meaning/intent.md` or `overrides.json`.

## 2. Read in this order (context budget)

1. **`brief.md`** (<= 4k tokens): status line, soundtrack, meaning, characters, sections, choreography, moments.
2. **`mvh brief out/<slug> --section S05`** (<= 1.5k tokens) when you work on one section.
3. **`lyrics/lines.tsv`** only if the video shows words: `id t d section_id singer repeat_group grade text`.
4. **API: `lib/mvh.d.ts`** (every method, option and field). `references/RECIPES.md` per engine;
   `references/CONTRACT.md` only §2 time, §3 IDs, §4 values, §9 helpers (never the whole 25k-token file).
   From `manifest.json` read only `status`, `summary`, `timebase`, `source`.

**Never cat curves, events or tables into context** (100 Hz curves, thousands of events). Load them in code with
`lib/mvh.js` (ES module, no deps) or `lib/mvh_load.py` (numpy), copied into every song folder.

## 3. The meaning rule (the user is the authority)

- `meaning: pending` (naming characters alone is no answer): **show the user the questions in
  `meaning/interview.md` and wait.** Write their answers to `meaning/intent.md` in their words only; anything to be
  obeyed goes in the template (YAML at the end: characters, `voices`, sections, `do_not`), the rest is free text
  (verbatim notes, never parsed into a rule). Then `mvh analyze out/<slug>`. While you wait, prepare the parts
  of the plan that need no meaning (timing, cuts); the look and story wait.
- Draft only after that, or when asked: follow `meaning/request.md`, write `meaning/authored.json` (`"status":
  "draft"`, cited claims, quotes <= 10 words), then `mvh meaning out/<slug>`. Never overwrite the user's claims.
  `# suggestion` lines in intent.md are not answers: never unmark them or copy a draft into `intent.md`.
- **`do_not` rules** (template only, verbatim in brief.md) are hard constraints on every frame. If brief.md says
  **template entries did not parse** (`intent_unparsed`), a rule may be missing: ask the user to fix it first.
- `notes` (`meaning.json`): the user's own words; direction, not rules. A note that reads like a rule is a question.
- The meaning is the whole song's. Sections are the music's parts and usually carry no answer: pick their look from
  the music and the song meaning. **`line_notes`** (`song.meaning.line_notes`) explain single lyric lines in the
  user's words (a reference, who a line is aimed at); `shared: true` = a repeat's note. Direction, not rules.
- `field_sources` (sections, characters, top level) says who wrote a field: `user`; `draft` = an agent's suggestion
  (tell the user); `audio` = measured, nobody's direction. brief.md marks `(draft)` / `(audio)`.
- Corrections (beats, sections, lyric timing, singers) go through the viewer (`mvh view out/<slug>`).

## 4. Plan first: build only after the user says yes

Before you build, install, generate or spend anything, write `<project>/PLAN.md` in the shape of
`references/PLAN.md`: concept, look, characters, storyboard per section from the data, hero moments, words,
**the tools you choose** (whatever serves the look best, not only the RECIPES engines; every install, key and cost
listed) and **the work split**: independent pieces go to other agents in parallel, each on the model tier its task
needs (most capable: concept, art direction, integration, review; balanced: scene and pipeline code; fastest:
mechanical batch work). Show a summary and ask: approve, or what to change. Build only after a yes; anything the
plan did not list needs a new yes.

## 5. Time, frames, IDs (the rules that bite)

- **Soundtrack = `song.soundtrack`** (`manifest.timebase.soundtrack`: `audio/mix.flac`, or `audio/mix.wav` when the
  mix clips). Play and mux exactly that file, never the original: every time is seconds from its first sample.
- Frame rule `{fps, frame0 = 0, early = false}`; NTSC is `[24000, 1001]` (23.976 is literal). Blender: `frame0: 1`.
  Frame n shows `timeOf(n, fr)`; an event belongs to `frameOf(t, fr)`.
- Curves are 0..1 with absolute twins (`bands.bass_db`); helpers never return NaN.
- IDs: section `S03`, phrase `P02`, eight-count `E012`, line `L007`, word `L007.03`, voice `V2`, character `C1`, cue
  `Q0034`, hit point `H004`, hold `O002`; repeats share `repeat_group` / `LG01`. `E000` is a 5-6-7-8 lead-in that may
  start before 0 s.

## 6. What to use for what

| Want | Use |
|---|---|
| Dance | `song.count(t)` -> `{eight_id, count 1..8, sub, accent, in_pulse}`; `beatPhase(t)`; `events('grooves')`, `curve('choreo.movement')` |
| Hits, poses | `events('hit_points')`, `events('holds')`, `song.pulse('hit_points', t)`, `curve('choreo.accent')` |
| **Cuts** | **cues define cuts**: `events('cues').next(t, {minTier: 2})`, `lead_in_s` to anticipate. Hero shots: `events('moments')` sorted by `rank` |
| Kick | flashes and shake only: `song.kicks()` / `song.pulse('kick', t)`. One frame off a cue: cut on the cue. `qa:kick_sources_disagree`: prefer bars, tier 1-2 cues |
| Characters, lip-sync | `song.meaning.characters` (array, by `id`); `song.singerAt(t)` -> `[{character_id, voice_id, lead_backing, line_id, mouth_open}]` |
| Karaoke | `song.linesAt(t)`: every line sounding (overlaps = two singers) with its `words`; `line.singer` is an array; notes: `song.meaning.line_notes` |
| Look | `song.meaningAt(t)` -> feel, emotion, palette_hint, movement/camera hints, characters_present, do_not, field_sources |
| Energy | `curve('dyn.intensity')`, `curve('loud.short_term')`, `events('edm_roles')` (build/drop) |
| Melody | `song.vocalAt(t)`, `events('notes.bass')`, `events('chords')` |
| Shaders | `song.spectrumAt(t)`, `song.textureData(ids)` + `lib/mvh.glsl` |
| Other tools | `mvh frames out/<slug> --fps 24 [--frame0 1] [--curves "*"] [--format deforum]` -> `frames/*.csv` |

Browsers/Remotion: `load()` has only what `include` lists (RECIPES) (Node reads lazily).

## 7. Check the result

Scrub `mvh view out/<slug>` against your render. Status-line flags (`singers:review`, lyrics grade C/D, `degraded:*`,
`fallback:*`, `qa:*`) mark shaky data: prefer coarser cues there; show grade C/D lines whole, without a word wipe.
