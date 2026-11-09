# ud2-kick: user decision UD2, the kick source (W4 phase 0)

Normative: docs/CONTRACT.md **D79** (agent-facing kick, kick gate, meta/drums.json, manifest kick_source / kick_agreement,
QA flag, consumers) and **D80** (hits.kick precision). Evidence and test rewrites: docs/contract/decisions/UD2.md.
Contract bumped **1.0.0-rc.2 -> 1.0.0-rc.3** (the one bump for W4 phase 0; ud1-meaning took D78 and does not bump).
No lyric text appears here.

## What changed

| Area | Change |
|---|---|
| drums 1.1.0 -> 1.2.0 (`src/mvh/stages/drums/__init__.py`, new `kick.py`) | deps += `spectral` (reads hits.kick `t`, `kick_conf`). CR-M1-4 kick gate on the DrumSep path: kick-stem onsets without a 30-120 Hz rise (>= 3 dB), on a hat onset while quiet (< ref - 10 dB) or faint (< ref - 20 dB) are dropped (ref = p90 of the kick rows' 30-120 Hz level). Recovery: bass-dominant snare-stem hits relabelled `kick`; kick-level snare-stem bursts confirmed by hits.kick get an added kick row (layered); toms only when kick-shaped, fast-decaying and mix-confirmed. Per-song choice `kick.choose_source` (vel median >= 0.3, gaps < 100 ms <= 25 %, gate kept >= 40 %) -> `meta/drums.json`; param `kick_source = auto|drums|mix` overrides; `mix` adds fallback `drums:kick_source_mix`; a low agreement adds a warning. Summary gains `kick_source`, `kick_agreement`. |
| spectral 1.2.0 -> 1.3.0 (`dsp.py`, `__init__.py`) | hits.kick precision: clicky-body route off (`kick_click_route` 0), sweep click alternative needs a 12 dB burst, weak (< 0.5 x typical) AND ambiguous (kick_conf < 0.8) events dropped unless roll / duck / within 150 ms after a kept kick. The hits.kick curve is unchanged. |
| contract (`catalog.py`, `conventions.py`, `golden.py`, schemas, CONTRACT.md) | `meta/drums.json` (optional, schema `mvh/files/drums`); manifest `summary.kick_source`, `summary.kick_agreement`; CONSUMES: drums += hits.kick, brief += meta/drums.json / drum_hits / hits.kick, viewer += meta/drums.json; `conventions.kick_items` (reference); golden section 6b `kick`; D79, D80; version rc.3; schemas regenerated (`gen --check` passes). |
| runtime (`finalize.py`) | `kick_info()`: manifest summary.kick_source / kick_agreement from meta/drums.json, flag `qa:kick_sources_disagree` (threshold 0.75). |
| lib (`mvh.js`, `mvh_load.py`, `mvh.d.ts`) | `song.kickSource` / `kick_source`, `song.kicks()` (Events of {t, vel, conf, source}), `events('kick')`, `pulse('kick', t)`, `resolve('kick')`, helper `kicks`, exported `kickItems` / `kick_items`. Golden + parity + new kick.test.mjs / test_lib_kick.py. `mvh.glsl`: version only. |
| brief (`build.py`) | header row `kick` (source, count, agreement, QA warning) and a `kicks` column per section; `--section` zoom line. (ud1's `_meaning_block` untouched.) |
| viewer (`data.js`, `lanes.js`, `panels.js`) | data.js reads meta/drums.json and sets the song's kick source (viewer.html is built before the manifest); the hits lane's kick row draws `song.kicks()` with the other timeline as grey ticks; the value panel's pulse uses `pulse('kick')`. |
| frames 1.0.0 -> 1.1.0 | event column `kick`: loudest agent-facing kick vel in the frame (0 without one). |
| SKILL.md | "Cut on the kick" row (song.kicks(), kick_source, QA flag meaning). |
| tests | tests/review/M3a/r-ml/conftest.py stage list += spectral; new tests/unit/drums/test_kick_source.py (10), tests/unit/lib/test_lib_kick.py (3) + kick.test.mjs (4), golden kick tests (py + js), parity spec includes `kick`; tests/unit/spectral: held-acoustic precision target, new kick-free test (3); M1 review r4 held-bass and all r5 tests rewritten to precision targets; tests/integration/M1/test_real_kick_sources_agree.py rewritten for UD2 (5 tests); tests/unit/contract PLAN_DEPS drums += spectral; tests/unit/brief/test_skill.py accepts the `kick` alias. |

## kick_source and agreement per song (out/_wip/ud2-kick/<slug>: integrator max folders re-analysed, analyze 0 / validate 0)

| song | kick_source | kick rows raw -> agent-facing | vel median | gaps < 100 ms raw -> kept | mix_in_drums / drums_in_mix (30 ms) | flag |
|---|---|---|---|---|---|---|
| synth | drums | 85 -> 85 | 0.72 | 0.00 -> 0.00 | 0.977 / 0.988 | - |
| newton-vs-nye (easy) | drums | 200 -> 198 | 0.89 | 0.01 -> 0.00 | 1.000 / 0.995 | - |
| versatile | drums | 124 -> 109 | 0.82 | 0.11 -> 0.00 | 0.956 / 0.991 | - |
| jeremy | drums | 644 -> 548 | 0.77 | 0.05 -> 0.00 | 0.958 / 0.916 | - |
| megafauna (hard) | drums | 647 -> 342 (323 kept, 10 relabelled from the snare stem, 9 layered) | 0.46 | 0.43 -> 0.16 | 0.463 / 0.249 | qa:kick_sources_disagree |

MEGAFAUNA keeps the gated stem (it passes the check; the raw stem would fail it on vel and fast gaps) because the mix cannot
see the sidechained drop kicks. hits.kick (fallback) after the precision retune: Jeremy 559 -> 524 events, precision against
the drum-stem kick 0.89 -> 0.95 at the same recall 0.95; kick-free review textures 50 / 21 / 7 -> 0 / 0 / 0.

## Tests and gates
- `scripts\gate.ps1 M1`: **PASS, every step** (fixture, unit, review, ruff, contract, validate, e2e, lib-node, determinism);
  log out/_wip/ud2-kick/gate-M1.log.
- `scripts\gate.ps1 M3a`: every step PASS except review, which failed on 1 test + 2 setup errors because
  tests/review/M3a/r-ml/conftest.py ran `--only ingest,separate_fast,separate_hq,stem_activity,drums` and drums now needs
  spectral (D79), so drums never ran. Fixed by adding spectral to that stage list; the 3 tests then pass
  (out/_wip/ud2-kick/m3a-review-rerun.log). The other 13 M3a review tests passed in the gate run. Log: gate-M3a.log.
- `node --test tests/unit/lib`: 35 pass, 0 fail.
- `pytest tests/unit` (before the skill-test fix): 1534 passed, 1 failed (test_skill alias, fixed), 97 skipped, 1 xfailed.
- `pytest tests/review/M1 tests/unit/spectral`: all pass. `pytest tests/integration/M1`: 5 pass on the UD2 runs.
- ruff on src + tests: clean.

## Seams (W4 verification of my area)
- **S06: resolved** by D79 (one agent-facing kick, gate, QA flag); the integration test now checks the UD2 contract.
- **S17 (grooves, M2): still real.** The gate does not fix it: groove ids MEGAFAUNA 45 / 63 bars -> 48 / 62, Versatile 36 ->
  32 / 80, Jeremy 28 -> 25 / 124 (synth 9 / 26 unchanged). The clustering itself (M2 choreo) needs work.
- Not touched: S16, S18, S19, m3-m5, Newton lyrics grade.

## Open issues
- The integrator's reference folders (out/_wip/integrator/<slug>) are pre-UD2; the integration test falls back to
  out/_wip/ud2-kick/<slug>. My runs were made before the version bump (rc.2 + UD2 code); the bump changes no behaviour, but
  every cache key changes, so the post-E max analyze re-runs everything.
- Known limit of the hits.kick fallback: a staccato low piano chord with its fundamental in the kick band (E2) reads as an
  acoustic kick (body route); documented in UD2.md, not a test target.
- `drums.kick_kept_min` 0.4 vs MEGAFAUNA's 0.50: MEGAFAUNA passes with a margin of 0.1; the other checks pass with wide margins.
