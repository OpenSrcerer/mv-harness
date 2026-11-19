# mv-harness recipes

Every recipe reads one song folder `out/<slug>/` through `lib/mvh.js` (browser/Node, no deps) or `lib/mvh_load.py`
(numpy). Python names are the snake_case of the JS ones (`singerAt` -> `singer_at`, `linesAt` -> `lines_at`). The full
typed API is `lib/mvh.d.ts` in the song folder; contract §2 time and frames, §3 IDs, §4 values, §9 helpers
(references/CONTRACT.md).

## Loading

```js
// Node: import the loader by file URL (a relative import resolves against this script's folder, not the working
// directory; a bare Windows path C:/... is not a valid ES module specifier)
import { pathToFileURL } from 'node:url';
const SONG = 'C:/path/to/mv-harness/out/<slug>';
const { load, loadSync, timeOf, frameOf } = await import(pathToFileURL(SONG + '/lib/mvh.js').href);
const fr = { fps: 30 };                                   // or { fps: [24000, 1001] }, Blender { fps: 24, frame0: 1 }
const song = loadSync(SONG, { fr });                      // Node: synchronous, every part read on first use
// Browser / Remotion: await load(url, { include: [...], fr }); only what `include` lists is there (see Remotion)
const t = timeOf(frame, fr);
```
```python
import sys; sys.path.insert(0, "out/<slug>/lib")
import mvh_load as mvh
song = mvh.load("out/<slug>", fr={"fps": 24, "frame0": 1})
```
Node 20.16+ or 22.3+ (filesystem mode uses `process.getBuiltinModule`).

## Dancing on counts and hits (choreography)

```js
const c = song.count(t);            // {eight_id, count 1..8, sub 0..3 (1 e & a), phase, accent, partial, lead_in, in_pulse}
if (c.count !== null) pose = keyPoseFor(c.eight_id, c.count) ; // restart choreography at every phrase/section start
const hit = song.pulse('hit_points', t, { attack: 0.02, decay: 0.3 });   // 0..1 flash, weighted by strength
const kick = song.pulse('kick', t, { attack: 0.005, decay: 0.15 });    // song.kicks(): THE kick timeline (UD2)
const hold = song.events('holds').at(t);                                 // {item: {kind: vocal_note|chord|decay|silence}, progress}
const groove = song.events('grooves').at(t)?.item;                       // a bar's groove_id, swing, syncopation, 16-step pattern; null on bars without one
```
- Kicks: always `song.kicks()` / `song.pulse('kick', t)`: one timeline picked per song (`song.kickSource`:
  `drums` = the bleed-gated drum-stem kick, `mix` = `hits.kick`, the lower-quality fallback). Never mix `drum_hits`
  kicks with `hits.kick`, and never use the raw `drums.kick` stem curve as the kick (on some songs it is hat bleed).
- `count === null` outside counts; `partial` counts (len 4/6) close a phrase early. `E000` is the 5-6-7-8 lead-in and
  may start before 0 s: a video that starts at frame 0 sees only its last counts.
- In `in_pulse: false` regions (silences, rubato intros) the grid is virtual: freeze or drift instead of dancing.
- Section energy: `song.events('edm_roles').at(t)?.item.role` (build/drop/breakdown), `song.curve('dyn.intensity').at(t)`,
  `song.curve('choreo.movement').at(t)` for how busy movement should be.

## Lip sync per singer (characters)

```js
const chars = Object.fromEntries((song.meaning?.characters ?? []).map((c) => [c.id, c]));   // an array: index by id
for (const s of song.singerAt(t)) {   // lead first, then voice number
  const ch = chars[s.character_id];                         // {id, name, description, voice_ids, ...}
  rig[s.character_id].mouth = s.mouth_open;                 // that voice's vocal.mouth_open.<V> (or vocal.mouth_open)
  rig[s.character_id].isLead = s.lead_backing === 'lead';
}
const lead = song.singerAt(t)[0]?.voice_id;
const vis = song.events('visemes').allAt(t).find((v) => v.voice_id === lead)?.viseme;   // 'A'..'H' or 'X' (rest)
```
- Characters not in `singerAt(t)` are silent: close their mouths (`mouth_open` is gated by that voice's words).
- `visemes.allAt(t)` returns one item per voice (most are `X` while silent): always pick the voice you animate.
- `events/singing.json` items carry `review: true` where the singer guess is weak; the user fixes those in the viewer.

## Karaoke (words on screen)

```js
for (const row of song.linesAt(t)) {          // every line sounding at t; two rows where singers overlap
  const who = row.line.singer;                // character ids, lead first (an array; lines.tsv writes it C1+C2)
  const wipe = row.line.grade === 'C' || row.line.grade === 'D' ? null : row.word;   // weak timing: no word wipe
  drawLine(row.words, wipe, row.word_progress, colourOf(who[0]));
}
```
- The user's note on a line (optional, their words): `const noteOf = new Map((song.meaning?.line_notes ?? []).map((n) =>
  [n.line_id, n]))`, then `noteOf.get(row.line.id)?.note`. Use it to stage the line (a reference to show, who it is
  aimed at), not as on-screen text unless the user says so. `shared: true` marks a repeat's note.
- `song.lyricAt(t)` returns one line (the latest that started): fine for a single caption, wrong where lines overlap.
- `lyrics/lyrics.srt|.vtt|.ass|.lrc` are ready-made subtitle files on the same clock (ffmpeg can burn `.ass` in).

## Camera on cues

```js
const next = song.events('cues').next(t, { minTier: 2 });     // tier 1 section/drop/build start, 2 phrase/impact/stop
if (next && next.t - t <= (next.lead_in_s ?? 0)) startMove(next);   // anticipate builds into drops (tier 1 only)
const cutsHere = song.events('cues').inFrame(frame, fr, { minTier: 2 });   // cut on the frame of the cue
const heroes = [...song.events('moments').items].sort((a, b) => a.rank - b.rank);   // items are in time order
```
- **Cues define cuts; kicks drive flashes.** A cue and its kick can fall one frame apart: keep the cut on the cue frame.
- A cue merges co-timed reasons (`kinds[]`, `sources[]`); `source` links to the section, impact, hit point ... it came from.
- `moments` (the brief lists 15) carry `rank` and `cue_id`: plan hero shots there first.
- `camera_hint` / `movement_hint` from `song.meaningAt(t)` are directions per section; check `field_sources` (below).

## Palette and meaning per section

```js
const m = song.meaningAt(t);   // {section_id, feel, meaning, emotion {lyric, audio, agree}, palette_hint[], movement_hint,
                               //  camera_hint, characters_present[], do_not[], provenance {source, status}, field_sources}
const M = song.meaning;        // meaning.json: characters, palette, palette_names, do_not, notes, sections, field_sources
const palette = m.palette_hint.length ? m.palette_hint                              // hex: the section's
  : M?.palette?.length ? M.palette                                                  // the song's
  : song.manifest.summary.palette;                                                  // cover-art palette (placeholder)
```
- While the meaning is `pending` the only colours are the cover-art palette: use it as a placeholder and say so.
- Per field, `field_sources` says who wrote it: `user` (the user's direction), `draft` (an agent's suggestion: tell
  the user), `audio` (measured from the song: emotion, characters heard; a fact, nobody's direction). A section whose
  `provenance` is `{source: 'audio', status: 'draft'}` has nothing authored, only audio facts.
```js
const sec = M.sections.find((s) => s.section_id === m.section_id);
const who = (f) => sec.field_sources?.[f] ?? (sec.provenance.status === 'user' ? 'user' : sec.provenance.source);
const camera = who('camera_hint') === 'user' ? directive(m.camera_hint) : suggestion(m.camera_hint);
```
- `do_not` rules (user's words) apply to every frame: check them before you add any element.
- Repeated sections (`repeat_group`) usually want the same look, varied by `occurrence` (chorus#1 vs chorus#3).

## Remotion

```powershell
uv run --frozen --no-sync mvh pack out\<slug> <project>\public\song     # the web subset incl. the soundtrack
```
```tsx
import React from 'react';
import { staticFile, delayRender, continueRender, useCurrentFrame, Audio } from 'remotion';
import { load, frameCount, timeOf } from '../public/song/lib/mvh.js';
const FR = { fps: 30 };
const INCLUDE = ['curves:core', 'curves:vocal', 'events:beats', 'events:counts', 'events:sections', 'events:cues',
  'events:moments', 'events:singing', 'events:hit_points', 'events:holds', 'events:grooves', 'events:visemes',
  'events:edm_roles', 'kick', 'lyrics', 'meaning'];          // or 'all' (about 15 MB); anything else: song.ensure(...)
export const calculateMetadata = async () => {              // duration from the song, not hard-coded
  const man = await (await fetch(staticFile('song/manifest.json'))).json();
  return { durationInFrames: frameCount(man.source.duration_s, FR), fps: 30 };
};
export const Video = () => {
  const [song, setSong] = React.useState(null);
  const [handle] = React.useState(() => delayRender('mvh'));
  React.useEffect(() => { load(staticFile('song/'), { include: INCLUDE, fr: FR })
    .then((s) => { setSong(s); continueRender(handle); }); }, []);
  const frame = useCurrentFrame();
  if (!song) return null;
  const t = timeOf(frame, FR);
  return <><Audio src={staticFile('song/' + song.soundtrack)} />{/* song.count(t), song.singerAt(t), song.linesAt(t) ... */}</>;
};
```
Everything after `load` is synchronous, so frames render deterministically. A call whose data is not in `INCLUDE`
throws "not loaded" in the browser; Node reads lazily, so test the include list in Remotion itself.

## Serving a song folder to a browser page

- `mvh pack out/<slug> <dest>` copies the song folder without `.cache/`, `stems/` (about 600 MB) and `viewer.html`:
  everything a page reads, including both mixes; `--with-stems` adds the stems.
- `load(url)` fetches files: it does not work from `file://`. Serve over HTTP **with Range support**, or seeking the
  audio fails silently (`python -m http.server` has none; Vite's and Remotion's dev servers do).

## three.js / WebGL

```js
const td = song.textureData(['bands.bass', 'hits.kick', 'dyn.intensity'], { width: 1024, format: 'r32f' });
const tex = new THREE.DataTexture(td.data, td.width, td.height, THREE.RedFormat, THREE.FloatType);
tex.minFilter = tex.magFilter = THREE.NearestFilter; tex.needsUpdate = true;
material.uniforms.uKickInfo = { value: new THREE.Vector4(...td.layout[1].info) };   // (rate, n, width, row0)
// GLSL (paste lib/mvh.glsl): float kick = mvhCurve(uCurves, uTime, uKickInfo);
```
Clock for live playback: `t = ctx.getOutputTimestamp().contextTime - startedAt - ctx.outputLatency` with an
`AudioContext` playing `song.soundtrack`; for offline renders use `timeOf(frame, fr)`.

## Blender

```python
fr = {"fps": 24, "frame0": 1}                                     # Blender frames start at 1
song = mvh.load("out/<slug>", fr=fr)
for n in range(1, song.frame_count(fr) + 1):
    obj.scale.z = 1 + song.curve("bands.bass").frame(n, fr)
    obj.keyframe_insert("scale", frame=n)
```
Or without Python deps: `mvh frames out/<slug> --fps 24 --frame0 1` and read `frames/24_f1fps.csv`.
Add `song.soundtrack` (a path inside the song folder) as the sound strip at frame 1.

## ComfyUI / Deforum / ffmpeg

- `mvh frames out/<slug> --fps 24 --curves "bands.*,hits.kick,dyn.intensity" --format deforum` writes
  `frames/24fps.deforum.json`: schedule strings `"0:(0.12), 1:(0.13), ..."` per channel for Deforum/ComfyUI nodes,
  plus the CSV (columns: frame, t, curves, then section_id, beat, count, eight_id, line_id, singer, cue_id ...).
- Prompt per section: join `meaningAt(t).feel`, the palette words (`meaning.palette_names`) and the section label.
- ffmpeg cuts: take tier 1-2 cue times from `events/cues.json` in code, then `-ss/-to` on the rendered clips; always mux
  the soundtrack (`manifest.timebase.soundtrack`, the same as `song.soundtrack`), never the original file.

## The viz/ scenes offline (vizState)

The viz/ scenes are the user's audio-visualiser project (a `viz/` folder next to the mv-harness repo).
```js
const fr = { fps: 60 };                           // viz scenes assume 60 fps; say yours
const state = song.vizState(t, fr);               // the fields of viz/js/audio.js: bass, mid, high, level, kick, kickRaw,
scene.update(state);                              // midHit, highHit, beat, beatPulse, onset, bpm, bandBytes ...
```
`vizState` needs a frame rule (pulses depend on the frame length); without one it throws.
