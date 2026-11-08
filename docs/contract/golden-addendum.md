# Golden addendum: lib-only helper rules (contract v1.0.0-rc.1)

`docs/contract/golden-vectors.json` covers every helper whose semantics live in `src/mvh/contract/conventions.py`.
A few helpers in `lib/mvh.js` / `lib/mvh_load.py` have no reference function there: `vizState`, the singer join of
`lyricAt`, the merge in `meaningAt`, the NaN fill of `textureData` and the bytes of `spectrumWindow`. This page fixes
their rules (CONTRACT.md section 5 "vizState(t) mapping" says the constants are recorded here) and describes the extra
golden cases.

| File | What |
|---|---|
| `src/mvh/assets/golden/golden-vectors.json` | byte-identical copy of `docs/contract/golden-vectors.json` (both test suites check it is current) |
| `src/mvh/assets/golden/addendum-vectors.json` | the addendum cases: an inline synthetic song plus expected values |
| `tests/unit/lib/make_addendum.py` | generator (`--check` fails when the file is stale). It computes the expected values from `conventions.py` primitives and the rules below, **not** from either loader |
| `tests/unit/lib/addendum.test.mjs`, `test_lib_addendum.py` | both loaders against every addendum case (1e-6; ints, bools, ids, nulls exact) |

## 1. vizState(t, fr = {fps: 60})

`song.vizState(t, fr)` (Python `song.viz_state(t, fr=None)`) returns the fields of the `AudioEngine` in
`viz/js/audio.js`, so a viz scene can take it as its `audio` argument. It is a pure function of the frame that
contains t:

- `n = frameOf(t, fr)`, `tc = frameCentre(n, fr)` (the default rule is 60 fps, frame0 0, centred). The result carries
  `t = tc` and `frame = n`.
- Continuous fields are **frame values** under each channel's resample policy (`curve.frame(n, fr)`), so a hit flash is
  never lost between frames: `bass/mid/high` <- `bands.{b}_viz` (mean), `level` <- `bands.level` (mean),
  `kick`, `kickRaw`, `midHit`, `highHit` <- `hits.kick`, `hits.kick_raw`, `hits.mid`, `hits.high` (max) clamped to [0, 1]
  (viz never exceeds 1; the stored envelopes go to 1.5), `bpm` <- `tempo.bpm` (linear). A missing channel reads 0.
- Onsets: an item of `onsets.bass` (or `.mid`, `.high`) **has fired** at frame n when `frameOf(item.t) <= n`. Its age is
  `max(0, tc - item.t)`, so an onset inside the current frame reads a full pulse, exactly as viz sets the pulse in the
  frame that detects it.
  - `onset` / `midOnset` / `highOnset`: the last fired item lies in frame n (the "item in the current frame" rule).
  - `beatCount`: number of fired `onsets.bass` items.
  - `beatPulse = exp(-age_last / 0.11)` (viz: set to 1 on onset, `*= exp(-dt / 0.11)`).
  - `beat = max over fired bass items with age <= 10 s of amp * exp(-age / 0.3)`, `amp = 0.55 + 0.45 * s`
    (viz: `beat = max(beat, strength)` with `strength = clamp(0.55 + ..., 0.55, 1)`, `beat *= exp(-dt / 0.3)`).
  - `midPulse`, `highPulse = (0.6 + 0.4 * s) * exp(-age_last / 0.11)` of the last fired item of that band (viz sets
    the pulse to `clamp(0.6 + ..., 0.6, 1)`, it does not take a max).
  - `s = clamp(item.strength, 0, 1)`, 1 when the item has no strength. The offline onset strengths are per-song 0..1, so
    they are mapped linearly onto the viz ranges [0.55, 1] and [0.6, 1].
  - `recentBeats` (Float32Array 8): the last 8 fired bass onset times, oldest first, padded at the front with -100 (viz
    initial value). They are **song times**: drive the scene clock (`uTime`) with song time so `uTime - uBeats[i]` is the
    age, as in viz. `recentBeatAmp[i] = clamp(max(hits.kick_raw.at(t_i), hits.kick.at(t_i), 0.6 * amp_i), 0, 1)` (viz:
    `max(hit.bass.raw, kick, strength * 0.6)`).
- Spectrum: `bands` = `spectrumAt(tc) / 255` (Float32Array 128, the viz smoothed bands); `bandsRaw` = the same values
  (the pre-gain raw bands are not stored); `peaks[k] = clamp(max(bands[k], max over the rows j of spectrumWindow(tc,
  2.25) of row_j[k] / 255 - 0.45 * max(0, tc - j / 100)), 0, 1)` (viz peak hold falls 0.45 per second; 2.25 s covers a
  full-scale fall). `bandBytes` (Uint8Array 512) is RGBA per band with **R = G = B = the spectrum byte, A = 255**
  (CONTRACT.md section 5; viz puts raw and peaks in G and B, use `bandsRaw` / `peaks` for those). `wave` is 512 zeros and
  `waveBytes` is 512 x 128 (the waveform is not stored).
- Engine settings, as the `audio.js` defaults: `hitRelease 0.18`, `hitThreshold 0.35`, `kickGateDb -46`, `hitFloor 0.05`,
  `refFloor 0.075`, `rearmDb 4`, `gain 1`, `sensitivity 1`, `drive {bass 1, mid 1, high 1}`, `monitorVolume 0.6`,
  `silentFor 0`, `active true`, `sourceType 'offline'`, `sourceLabel 'mv-harness'`, and `ranges` computed with the viz
  band map (`bass [0, 32]`, `kick [2, 23]`, `mid [32, 87]`, `high [87, 127]`, `flux`, `fluxMid`, `fluxHigh`).
- JS only: the object also has the viz accessors `bandAt(t)`, `bandLow(x)`, `bandMid(x)`, `bandHigh(x)` (same code
  as viz) and no-op `update()` / `on()`. Python returns a dict with the same keys (numpy arrays for the typed arrays).

Constants taken from `viz/js/audio.js` (exported as `VIZ` in both loaders):

| Constant | Value | audio.js source |
|---|---|---|
| `NUM_BANDS`, `WAVE_LEN`, `F_MIN`, `F_MAX` | 128, 512, 32, 16000 | top-level constants |
| `BEAT_DECAY_S` | 0.3 | `decayB = Math.exp(-dt / 0.3)` |
| `PULSE_DECAY_S` | 0.11 | `decayP = Math.exp(-dt / 0.11)` (beatPulse, midPulse, highPulse) |
| `PEAK_FALL_PER_S` | 0.45 | `peaks[k] = max(peaks[k] - dt * 0.45, bands[k])` |
| `BEAT_STRENGTH_MIN` | 0.55 | `strength = clamp(0.55 + ..., 0.55, 1)` |
| `PULSE_STRENGTH_MIN` | 0.6 | `midPulse/highPulse = clamp(0.6 + ..., 0.6, 1)` |
| `RECENT_BEATS`, `RECENT_BEAT_EMPTY` | 8, -100 | `recentBeats = new Float32Array(8).fill(-100)` |
| `HIT_RELEASE`, `HIT_THRESHOLD`, `KICK_GATE_DB`, `HIT_FLOOR`, `REF_FLOOR`, `REARM_DB` | 0.18, 0.35, -46, 0.05, 0.075, 4 | engine settings |
| `RANGE_T` | bass [0, 0.25], mid [0.25, 0.68], high [0.68, 1] | band sub-ranges for bandLow/Mid/High |
| `BEAT_WINDOW_S`, `PEAK_WINDOW_S`, `DEFAULT_FPS` | 10, 2.25, 60 | lib choices (not in audio.js); DEFAULT_FPS is no longer a vizState default (D40: the frame rule is mandatory) |

## 2. Other lib rules

- **lyricAt(t)**: `line` is a copy of the lyrics.json line (latest start containing t) plus `singer` = the character ids
  and `voice_ids` = the voice ids of the `events/singing.json` items with that `line_id`, both **arrays**, de-duplicated,
  lead items first (then file order). `word` = the word of that line containing t (`event_at` on its words); in a gap
  between words, `word` and `word_progress` are null. Outside every line all four fields are null.
- **meaningAt(t)**: the section is `events('sections').at(t)`. Its entry in `meaning/meaning.json` `sections[]` is the
  one with the same `section_id`, else the one whose `[t0, t1)` contains t (claims that were re-anchored by time).
  `do_not` = the global `do_not` rules followed by the section's own, de-duplicated (the user's do-not rules apply to
  every section). Additive field `status` = meaning.json `status` (user, draft, pending) or null. Without a section:
  section fields null/empty, `do_not` = the global rules.
- **textureData(ids, {layout: 'wrap', width = 1024, format = 'r32f'})**: NaN-aware channels (`vocal.midi`,
  `vocal.f0_hz`) are packed with `nan_aware_at(v, i)` per sample (the held pitch), so a texture never holds NaN; inside a
  gap the GPU then lerps between held samples, which equals `curve.at` except within one sample of a voicing boundary.
  `r8` stores `round(clamp(value * 255, 0, 255))` (JavaScript rounding, half up; Python uses `floor(x + 0.5)`).
  Each layout entry also carries `width` and `info = [rate, n, width, row0]`, the vec4 that `mvhCurve` takes.
- **spectrumWindow(t, s)**: `k = round(100 s) + 1` rows ending at the nearest row of t, oldest first; rows outside the
  song are zero bytes. `round` is Python's half-to-even in both loaders (`roundHalfEven` in JS).
- **Events**: items are stably sorted by t on load (the writers already sort). A missing events file gives an empty
  `Events` with `exists = false`; helpers that read it return their "nothing here" value instead of throwing.
- **Missing optional data**: a missing curve channel reads 0 inside composite helpers (vizState, vocalAt, singerAt);
  `song.curve(id)` itself throws for an id that is not in `curves/index.json`. Non-finite `t` throws a TypeError.
- **mvh.glsl**: `mvhCurve` lerps manually between `texelFetch` texels (GLSL ES 3.00) and equals `curve.at` for
  linear/mean/max channels; `mvhCurveHold` takes the nearest sample (`floor(x + 0.5)`, without the 1e-9 epsilon, which is
  below float32 resolution). Times passed as float32 uniforms are exact to about 1e-4 s at 5 minutes.

## 3. Loading (JS and Python)

| JS | Python | Notes |
|---|---|---|
| `await load(base, {fetch, include})` | `load(base, include=None)` | JS: base is a URL (fetch) or, in Node, a folder path (fs) |
| `loadSync(path)` | `load(path)` | Node: lazy parts are read synchronously on first use |
| `await song.ensure(spec)` | `song.ensure(spec)` | spec: `all`, `curves:*`, `events:*`, `curves:<file>`, `events:<name>`, `lyrics`, `meaning`, `spectrum`, `helper:<name>`, or a bare file id / channel id / events name |
| `song.isLoaded(spec)`, `song.resolve(spec)` | `is_loaded`, `resolve` | |
| `HELPER_NEEDS` | `HELPER_NEEDS` | the resources each helper reads (`helper:vizState` = core, spectrum128, onsets.*) |

In URL mode (browsers, Remotion) a helper whose data is not loaded throws
`mvh: '<key>' is not loaded; call await song.ensure('<key>') first`; after `ensure` everything is synchronous. Node
does not need `ensure`. The JS module reaches `fs` through `process.getBuiltinModule` (no static `node:` imports), so
bundlers such as Remotion's webpack build it unchanged.

## 4. Tests

```
node --test tests/unit/lib/                                         # golden, addendum, GLSL, Song API (JS)
uv run --frozen --no-sync python -m pytest -q tests/unit/lib        # golden, addendum, JS-vs-Python parity
uv run --frozen --no-sync python tests/unit/lib/make_addendum.py --check
```

The parity test builds a song folder with the contract writers (`tests/unit/lib/lib_synth_song.py`), dumps every
helper with both loaders (`parity_dump.mjs` and `dump()` in `test_lib_parity.py`) on a dense time grid, all 32 frame
rules (8 fps values x frame0 0/1 x centred/early) and 13 channels covering every policy, NaN-aware pitch and a 1 Hz
file, and compares within 1e-6. When `tests/contract/synth/.done.json` exists it also runs on the contract fixture.
