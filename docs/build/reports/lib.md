# Report: lib (W1b helper libraries)

Status: **done**. Both loaders implement every row of the CONTRACT.md section 9 helper table, pass every case in
`docs/contract/golden-vectors.json`, pass the new addendum cases, and agree with each other within 1e-6 on two whole
song folders (a temp folder built with the contract writers, and the finished `tests/contract/synth/` fixture).

## Deliverables
| Path | What |
|---|---|
| `src/mvh/assets/mvh.js` | ES module, no dependencies. Browser (fetch), Node (`loadSync`, fs through `process.getBuiltinModule`, so there are no static `node:` imports and bundlers such as Remotion's webpack build it unchanged), Remotion (`await load` / `await song.ensure`, then everything is synchronous). It exports the Song API and the pure reference ports (`frameOf`, `curveFrame`, `eventAt`, `countAt`, `packTexture`, `textureSample`, ...) |
| `src/mvh/assets/mvh.d.ts` | declarations for every export. Type-checked in strict mode with TypeScript 6.0.3 (the copy bundled with VS Code) against a usage file: 0 diagnostics |
| `src/mvh/assets/mvh_load.py` | the same API in snake_case. It imports only the stdlib and numpy (a test checks this), never imports mvh, and works when copied into `lib/` |
| `src/mvh/assets/mvh.glsl` | `mvhCurve(sampler2D, t, vec4 info)` (manual lerp over `texelFetch`, wrap layout, R32F or R8) and `mvhCurveHold`. GLSL ES 3.00, no `#version` line, no uniforms |
| `src/mvh/assets/golden/golden-vectors.json` | byte copy of `docs/contract/golden-vectors.json` (checked current by both suites) |
| `src/mvh/assets/golden/addendum-vectors.json` | addendum cases for vizState, the lyricAt join, the meaningAt merge, the texture NaN fill and spectrumWindow |
| `docs/contract/golden-addendum.md` | vizState rules and the audio.js constants, the other lib-only rules, the loading API, how to run the tests |
| `tests/unit/lib/` | `golden.test.mjs`, `addendum.test.mjs`, `glsl.test.mjs`, `song.test.mjs` (node --test); `test_lib_golden.py`, `test_lib_addendum.py`, `test_lib_parity.py` (pytest); helpers `lib_synth_song.py`, `parity_dump.mjs`, `make_addendum.py`, `conftest.py` |

## Tests (all run on 2026-11-08)
- `node --test tests/unit/lib/` -> **30/30 pass**: golden 11, addendum 5, GLSL 6, Song API 8.
- `uv run --frozen --no-sync python -m pytest -q tests/unit/lib tests/unit/contract` -> **112 passed, 0 skipped** (lib 22,
  contract 90). The fixture parity test ran because `tests/contract/synth/.done.json` exists.
- `uv run --frozen --no-sync ruff check src/mvh/assets tests/unit/lib` -> clean. (`ruff check src tests` reports findings
  only in files other agents own.)
- `python tests/unit/lib/make_addendum.py --check` and `python -m mvh.contract.golden --check` -> up to date.

What parity covers: fps 23.976, [24000,1001], 24, 25, 29.97, [30000,1001], 30 and 60; frame0 0 and 1; centred and early
(32 frame rules); `curve.frame` on 13 channels covering every policy, NaN-aware pitch and a 1 Hz file; and, on a grid of
about 700 times plus event and boundary times ±1e-7, every other helper: `curve.at` for all channels,
`events.at/next/prev(minTier)/between/inFrame`, `beatPos/Phase/barPhase/count`, `pulse` (5 option sets, including beats
units), `osc` (12), `lyricAt`, `vocalAt`, `singerAt`, `meaningAt`, `spectrumAt/Window`, `textureData` (r32f and r8,
three widths) and `vizState` (4 frame rules plus the default). The test also checks that the dump is not vacuous: the
cases it needs (lead-in, partial count, duet and backing singers, held pitch, an onset frame) are present, the
comparer catches a 2e-6 difference, and no output is NaN or infinite.

The GLSL is checked by transpiling `mvh.glsl` to JS with a few regexes. The subset allows typed declarations, casts,
clamp/min/floor and texelFetch with bounds-checked texels. The result is compared with `curve.at` for widths 1 to 4096,
lengths 1 to 2500, rates 100 and 1 Hz, every row wrap, float32 time input over 5 minutes, and R8. A mutation test
(an off-by-one row index) shows the check catches errors.

## Decisions (beyond CONTRACT.md; all written down in golden-addendum.md)
1. **vizState(t, fr = {fps: 60})** works on the frame that contains t. Continuous fields are frame values under each
   channel's policy, so a kick flash is never lost between frames. The onset flags use the "an item in the current frame"
   rule. Pulses decay from the item time, and an onset inside the current frame reads a full pulse. Offline strengths
   (0..1) map onto the viz ranges: beat 0.55 + 0.45s, mid/high pulse 0.6 + 0.4s. Hit envelopes are clamped to [0, 1]
   (the stored range goes to 1.5; viz never exceeds 1). `recentBeats` holds song times. `peaks` is computed from 2.25 s of
   spectrum history at 0.45 per second. `bandBytes` is R = G = B = value, A = 255, as the contract says (viz puts raw and
   peaks in G and B). The JS object also has the viz accessors `bandAt`, `bandLow`, `bandMid` and `bandHigh`.
2. **lyricAt**: `line.singer` and `line.voice_ids` are **arrays** (lead first), because a line can have several singers.
3. **meaningAt**: the section's entry is looked up by id first, then by time range. `do_not` = the global rules plus the
   section's own. It also adds a `status` field.
4. **textureData**: NaN-aware channels are packed with the held pitch, so a texture never holds NaN. Each layout entry
   adds `width` and `info = [rate, n, width, row0]` (the vec4 for mvhCurve).
5. **Robustness**: events are stably sorted on load; a missing events file is an empty `Events` with `exists = false`; a
   missing channel reads 0 inside composite helpers; a non-finite t throws.
6. **ensure / include** accept `all`, `curves:*`, `events:*`, `curves:<file>`, `events:<name>`, `lyrics`, `meaning`,
   `spectrum`, `helper:<name>` (both JS and snake_case names), or a bare file id, channel id or events name. In URL mode a
   helper whose data is not loaded throws a message that names the exact `ensure` call. `HELPER_NEEDS` is exported.
7. JS rounds the spectrumWindow row count half to even (Python `round`), so the two loaders agree on .5 ties.

## Contract additions (additive, optional fields only)
- `meaningAt(t).status`; `lyricAt(t).line.singer` / `.voice_ids` as arrays (CONTRACT.md says "character ids" without fixing the shape).
- `textureData(...).format`; `layout[].width` and `layout[].info`.
- vizState also returns `t` (the frame centre) and `frame`.
- Exports beyond the table: the reference ports, `VIZ`, `HELPER_NEEDS`, `Song.isLoaded/resolve/hasCurve/eventNames/channelIds`, and `Events.byId/exists`.

## Open issues / notes for others
- **Runtime (finalize)**: copy `mvh.js`, `mvh.d.ts`, `mvh_load.py` and `mvh.glsl` into `<song>/lib/`. `golden/` is for
  tests only and does not need copying.
- **M6b / skill RECIPES.md**: Remotion should call `await load(staticFile('...'), {include: ['helper:vizState', ...]})`
  inside `delayRender` / `calculateMetadata`. three.js: `DataTexture(td.data, td.width, td.height, RedFormat, FloatType)`
  with NearestFilter, and each `layout[k].info` as a vec4 uniform. For viz scenes, drive `uTime` with song time so that
  `recentBeats` ages are right.
- `mvhCurveHold` rounds with `floor(x + 0.5)` without the 1e-9 epsilon (below float32 resolution). It can differ from
  `curve.at` only at exact half-sample ties.
- In gaps, the texture of a NaN-aware channel lerps between held samples. Within one sample of a voicing boundary this
  can differ from `curve.at`.

## Change requests
None. pyproject.toml, the locks and the frozen contract are unchanged.
