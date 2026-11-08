# mv-harness recipes

Every recipe reads one song folder `out/<slug>/` through `lib/mvh.js` (browser/Node, no deps) or `lib/mvh_load.py`
(numpy). Python names are the snake_case of the JS ones (`singerAt` -> `singer_at`). Contract sections: §2 time and
frames, §3 IDs, §4 values, §9 helpers (references/CONTRACT.md).

## Loading

```js
import { load, loadSync, timeOf, frameOf } from './out/<slug>/lib/mvh.js';
const fr = { fps: 30 };                                   // or { fps: [24000, 1001] }, Blender { fps: 24, frame0: 1 }
const song = await load('out/<slug>/', { include: ['curves:core', 'curves:vocal', 'events:beats', 'events:counts',
                                                  'events:singing', 'events:cues', 'lyrics', 'meaning'], fr });
// everything included is synchronous from here; anything else: await song.ensure('<curve file id | events name>')
const t = timeOf(frame, fr);
```
```python
import sys; sys.path.insert(0, "out/<slug>/lib")
import mvh_load as mvh
song = mvh.load("out/<slug>", fr={"fps": 24, "frame0": 1})
```

## Dancing on counts and hits (choreography)

```js
const c = song.count(t);            // {eight_id, count 1..8, sub 0..3 (1 e & a), phase, accent, partial, lead_in, in_pulse}
if (c.count !== null) pose = keyPoseFor(c.eight_id, c.count) ; // restart choreography at every phrase/section start
const hit = song.pulse('hit_points', t, { attack: 0.02, decay: 0.3 });   // 0..1 flash, weighted by strength
const kick = song.curve('drums.kick').frame(frame, fr);                  // max-pooled: never misses a hit at 24 fps
const hold = song.events('holds').at(t);                                 // {item: {kind: vocal_note|chord|decay|silence}, progress}
const groove = song.events('grooves').at(t)?.item;                       // per bar: groove_id, swing, syncopation, 16-step pattern
```
- `count === null` outside counts; `partial` counts (len 4/6) close a phrase early; `E000` is the 5-6-7-8 lead-in.
- In `in_pulse: false` regions (silences, rubato intros) the grid is virtual: freeze or drift instead of dancing.
- Section energy: `song.events('edm_roles').at(t)?.item.role` (build/drop/breakdown), `song.curve('dyn.intensity').at(t)`,
  `song.curve('choreo.movement').at(t)` for how busy movement should be.

## Lip sync per singer (characters)

```js
for (const s of song.singerAt(t)) {   // lead first, then voice number
  const ch = characters[s.character_id];                     // C1, C2 ... from meaning.json characters
  ch.mouth = s.mouth_open;                                    // that voice's vocal.mouth_open.<V> (or vocal.mouth_open)
  ch.isLead = s.lead_backing === 'lead';
}
const vis = song.events('visemes').allAt(t).filter(v => v.voice_id === song.singerAt(t)[0]?.voice_id); // optional A-H/X
```
- Characters not in `singerAt(t)` are silent: close their mouths (`mouth_open` is gated by that voice's words).
- `events/singing.json` items carry `review: true` where the singer guess is weak; the user fixes those in the viewer.
- Words: `const { line, word, word_progress } = song.lyricAt(t)`; `line.singer` lists the characters (`C1+C2`).

## Camera on cues

```js
const next = song.events('cues').next(t, { minTier: 2 });     // tier 1 section/drop/build start, 2 phrase/impact/stop
if (next && next.t - t <= (next.lead_in_s ?? 0)) startMove(next);   // anticipate builds into drops
const cutsHere = song.events('cues').inFrame(frame, fr, { minTier: 3 });   // cut exactly on the frame of the cue
```
- A cue merges co-timed reasons (`kinds[]`, `sources[]`); `source` links to the section, impact, hit point ... it came from.
- `events/moments.json` = the top moments (the brief lists 15) with `cue_id`: plan hero shots there first.
- `camera_hint` / `movement_hint` from `song.meaningAt(t)` are the user's (or a draft's) directions per section; check `field_sources` (below) to tell which.

## Palette and meaning per section

```js
const m = song.meaningAt(t);   // {section_id, feel, meaning, emotion {lyric, audio, agree}, palette_hint[], movement_hint,
                               //  camera_hint, characters_present[], do_not[], provenance {source, status}}
const meaning = await (await fetch('out/<slug>/meaning/meaning.json')).json();   // characters, palette, do_not
const palette = m.palette_hint.length ? m.palette_hint : meaning.palette;          // hex
```
- `provenance.status === 'draft'` means an agent wrote it: keep it, but tell the user.
- `provenance.status` is per section, so it can say `user` while single fields are the draft's. Read the per-field
  origin from `meaning.json`: `sections[].field_sources` (`{feel: 'user', camera_hint: 'draft', ...}`),
  `characters[].field_sources` (name, description) and the top-level `field_sources` (logline, palette). A field marked
  `draft` is a suggestion: use it, but do not present it as the user's direction.
```js
const sec = meaning.sections.find(s => s.section_id === m.section_id);
const isDraft = f => (sec.field_sources?.[f] ?? (sec.provenance.status === 'user' ? 'user' : 'draft')) !== 'user';
const camera = isDraft('camera_hint') ? suggestion(m.camera_hint) : directive(m.camera_hint);
```
- `do_not` rules (user's words) apply to every frame: check them before you add any element.
- Repeated sections (`repeat_group`) usually want the same look, varied by `occurrence` (chorus#1 vs chorus#3).

## Remotion

```tsx
import { staticFile, delayRender, continueRender, useCurrentFrame, useVideoConfig, Audio } from 'remotion';
import { load, frameCount } from '../public/song/lib/mvh.js';
export const calculateMetadata = async () => {          // duration from the song, not hard-coded
  const man = await (await fetch(staticFile('song/manifest.json'))).json();
  return { durationInFrames: frameCount(man.source.duration_s, { fps: 30 }), fps: 30 };
};
export const Video = () => {
  const [song, setSong] = React.useState(null);
  const [handle] = React.useState(() => delayRender('mvh'));
  React.useEffect(() => { load(staticFile('song/'), { include: ['curves:core', 'helper:count', 'helper:singerAt',
      'helper:meaningAt', 'helper:lyricAt', 'events:cues'], fr: { fps: 30 } }).then(s => { setSong(s); continueRender(handle); }); }, []);
  const frame = useCurrentFrame();
  if (!song) return null;
  const t = frame / 30;                                  // = timeOf(frame, {fps: 30})
  return <><Audio src={staticFile('song/audio/mix.flac')} />{/* ...use song.count(t), song.singerAt(t)... */}</>;
};
```
Copy the song folder to `public/song/`. Everything after `load` is synchronous, so frames render deterministically.

## three.js / WebGL

```js
const td = song.textureData(['bands.bass', 'hits.kick', 'dyn.intensity'], { width: 1024, format: 'r32f' });
const tex = new THREE.DataTexture(td.data, td.width, td.height, THREE.RedFormat, THREE.FloatType);
tex.minFilter = tex.magFilter = THREE.NearestFilter; tex.needsUpdate = true;
material.uniforms.uKickInfo = { value: new THREE.Vector4(...td.layout[1].info) };   // (rate, n, width, row0)
// GLSL (paste lib/mvh.glsl): float kick = mvhCurve(uCurves, uTime, uKickInfo);
```
Clock for live playback: `t = ctx.getOutputTimestamp().contextTime - startedAt - ctx.outputLatency` with an
`AudioContext` playing `audio/mix.flac`; for offline renders use `timeOf(frame, fr)`.

## Blender

```python
song = mvh.load("out/<slug>", fr={"fps": 24, "frame0": 1})       # Blender frames start at 1
fr = {"fps": 24, "frame0": 1}
for n in range(1, song.frame_count(fr) + 1):
    t = mvh.time_of(n, fr)
    obj.scale.z = 1 + song.curve("bands.bass").frame(n, fr)
    obj.keyframe_insert("scale", frame=n)
```
Or without Python deps: `mvh frames out/<slug> --fps 24 --frame0 1` and read `frames/24_f1fps.csv`.
Add `audio/mix.flac` as the sound strip at frame 1.

## ComfyUI / Deforum / ffmpeg

- `mvh frames out/<slug> --fps 24 --curves "bands.*,hits.kick,dyn.intensity" --format deforum` writes
  `frames/24fps.deforum.json`: schedule strings `"0:(0.12), 1:(0.13), ..."` per channel for Deforum/ComfyUI nodes,
  plus the CSV (columns: frame, t, curves, then section_id, beat, count, eight_id, line_id, singer, cue_id ...).
- Prompt per section: join `meaningAt(t).feel`, the palette words (`meaning.palette_names`) and the section label.
- ffmpeg cuts: take tier 1-2 cue times from `events/cues.json` in code, then `-ss/-to` on the rendered clips; always mux
  `audio/mix.flac` (`-map` the mix, not the original file).

## The viz/ scenes offline (vizState)

```js
const fr = { fps: 60 };                           // viz scenes assume 60 fps; say yours
const state = song.vizState(t, fr);               // the fields of viz/js/audio.js: bass, mid, high, level, kick, kickRaw,
scene.update(state);                              // midHit, highHit, beat, beatPulse, onset, bpm, bandBytes ...
```
`vizState` needs a frame rule (pulses depend on the frame length); without one it throws.
