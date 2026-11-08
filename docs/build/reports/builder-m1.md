# builder-m1 report: M1 Signal (spectral, loudness, dynamics)

Status: **done** (all three stages real, unit + real-song tests green; gate: every M1 step passes, the two failing steps are outside M1, see "Gate" below).
Progress log: `docs/build/progress/builder-m1.md`. Contract decisions: `docs/contract/decisions/M1.md`.

## Files (owned paths only)

| Path | What |
|---|---|
| `src/mvh/stages/spectral/{__init__,dsp,stage}.py` | spectral stage: viz port (`dsp.py`, pure functions) and the ctx glue |
| `src/mvh/stages/loudness/{__init__,r128,stage}.py` | loudness stage: EBU R128 measurements (`r128.py`) and glue |
| `src/mvh/stages/dynamics/{__init__,detect,segment,stage}.py` | dynamics stage: detectors, segmentation/intensity, glue |
| `tests/unit/{spectral,loudness,dynamics}/` | 72 unit tests (12 of them real-song, opt-in) + `viz_parity.cjs` (runs the real viz/js/audio.js in Node) |
| `tests/synth/m1/{signals,fakectx,harness,markers}.py` | synthetic generators with exact truth, an in-process Ctx (real `StageWriter`), the M1 harness, pytest markers |
| `docs/contract/decisions/M1.md` | additive fields, interpretations, change requests |

## What each stage does

**spectral** (`1.0.0`). Offline, non-causal port of `viz/js/audio.js` on the canonical mix:
- AnalyserNode front end verbatim (Web Audio periodic Blackman, `|X|/N`, per-bin dB on the mono down-mix, 2048-point at
  44.1/48 kHz), the 128-band map (wide-band dB mean, narrow-band dB interpolation), 2.6 dB/oct tilt, -88..-18 dB, soft
  knee, 22/110 ms band smoothing (`spectrum128` = round(255·bands)), 30/140 ms bass/mid/high energies, `level`.
  **Parity test**: the real `audio.js` runs in Node (vm sandbox, stub analyser) and matches band edges, ranges, kick
  bins, raw bands (2e-5), the raw kick energy, `_hitEnvelope` (causal path, 1e-6) and `_flux` (1e-6) at 44.1 and 48 kHz.
- Offline: centred 100 Hz frames, per-song gain instead of the AGC, hit reference = centred ±8 s median of attack sizes,
  kick gate `max(p95 − 30, min(−46, p95 − 20))`, centred flux threshold.
- Hit events (kick/mid/high): viz attack episodes (re-arm ignored) plus weaker attacks with a crisp onset (weak kick-band
  hits must look like a drum: `kick_conf` ≥ 0.75), timed on 400 Hz zero-phase band envelopes (step contrast of the low band
  + the ≥ 1 kHz click band). Envelopes `hits.*`/`hits.*_raw` are shifted by the median detection lag and flashed at
  each onset (flash rule). Additive item fields `env`, `rise_db`, `viz`, `kick_conf`.
- Physical bands (viz bands, kick, 7 fine) in dBFS (mean square of mid + side, full-scale sine = −3.01) with p02-p99.5
  twins; flux + onsets per band (refined onsets); centroid, roll-off, flatness, slope; width, balance, correlation.

**loudness** (`1.0.0`). K-weighting (pyloudnorm filters), centred momentary/short-term LUFS curves, integrated
(BS.1770-4, pyloudnorm), LRA (own EBU 3342), true peak (4× oversampling), sample peak, PLR, clipping, RMS/peak/crest
curves; ffmpeg `ebur128=peak=true` as an independent cross-check. `meta/loudness.json` also names the loudest and
quietest moments, short-term percentiles and QA flags (`limited_master`, `clipping`, `ebur128_mismatch`).

**dynamics** (`1.0.0`). SPIKE fix for limited masters:
- silences (Z, edges on a 5 ms envelope of the mix), stops (X, abrupt ≥ 15 dB falls into a gap), impacts (I: sustained
  loudness/bass steps, hits, brightness bonus; `major` impacts), decay tails (Y).
- parts (`events/dynamics.json`): multi-feature Foote novelty (LU, bass, kick dB, kick and onset density, brightness,
  slope, width; robust per-song scaling, clipped) with adaptive prominence, local re-splitting of long parts, hard
  boundaries (silences, stops, major impacts, long decay tails), downbeat snapping, agglomerative same-level merging
  towards ~1 part per 20 s, a 4-bar-grid fallback (allin1 sections once CR-M1-1 lands). Levels by mean short-term LU vs
  integrated, thresholds scaled for small loudness ranges. Additive evidence per part (energy, bass, kick/onset rate,
  brightness, loudness trend, `role_hint` drop/build/breakdown) for structure, which alone defines EDM roles.
- `dyn.intensity` composite and `dyn.novelty`; additive `meta/dynamics.json` (readable loud/quiet summary).

## Measured accuracy vs thresholds

| Area | Threshold | Measured |
|---|---|---|
| Kick events on synthetic one-shots (F1 at ±10 ms, t = first sample) | ≥ 0.95 | straight 4/4 **1.000**; syncopated groove with snares/hats/pad **0.967**; −25 dB quiet master **0.992**; 96 BPM groove **0.990**; median error −1.1 ms, p95 \|err\| 2.2 ms (asserted ≥ 0.95/0.98 in tests) |
| Kick events, synth contract fixture | (report) | drums stem F1 0.977 (r 1.0, p 0.955); full mix recall **0.929** @10 ms (0.953 @30 ms), precision 0.55 — the synth bass line is a kick-band hit by viz design; `kick_conf` medians TP 1.0 vs FP 0.5 |
| Kick counts vs W0 offline reference (viz-strength hits, `viz: true`) | within 10 % (W0) | megafauna 488/464 (+5 %), versatile 211/208 (+1 %), jeremy 622/617 (+1 %), newton 205/199 (+3 %) — asserted in the real tests |
| viz parity (real audio.js) | exact port | band map exact; raw bands ≤ 2e-5; `_hitEnvelope`, `_flux` ≤ 1e-6 |
| onsets.bass on kicks (faded one-shots) | (report) | straight F1 1.00, syncopated 0.96 at ±20 ms, median error −1.2 ms |
| Band dBFS | — | full-scale sine −3.01 ±0.25 dB in every band; white slope 0, pink −3.0 dB/oct |
| Loudness, EBU Tech 3341 cases 1-4 (44.1 and 48 kHz) | ±0.1 LU | all within ±0.1 (integrated; momentary/short-term on cases 1-2) |
| LRA, EBU Tech 3342 cases 1-3 | ±1 LU | within ±0.2 LU |
| True peak, fs/4 at 45° | — | −6.0 ±0.2 dBTP (sample peak −9.03) |
| Loudness vs ffmpeg ebur128, real songs | ±0.5 LU | megafauna −0.01, versatile −0.08, jeremy −0.02, newton −0.08 LU (synth −0.08) |
| Dynamics, synthetic dynamics song (exact truth) | (tests) | silence edges ±20 ms, stop ±20 ms, drop impact ±0.2 s (major, after silence), decay tail at the final hit, part boundaries on 8/24/46/48/60 s ±50 ms, level ordering, drop/build/breakdown hints; same on a tanh-limited master (≥ 5 parts) |
| Dynamics, synth contract fixture truth | (tests) | Z001 32.5 s / 2.0 s / 49.62 dB matched (±0.02 s, ±0.5 dB); X001 matched; impacts 34.5 (major) and 52.5 found, 17.0 (crash, +0.47 LU) missed; Y001 matched; drop hint at 34.5 |

## Real songs (upstream bars from `tests/contract/real-<slug>`, harness `python -m tests.synth.m1.harness`)

Timings (harness, single process, shared machine): spectral 4.4-6.9 s, loudness 2.2-4.2 s, dynamics 2.3-4.6 s per song.

| Song | Loudness (I / LRA / TP / PLR) | ffmpeg diff | Spectral (kick hits / viz-strength / onsets b-m-h) | Dynamics |
|---|---|---|---|---|
| megafauna (217 s) | −10.81 LUFS / 17.9 LU / +0.24 dBTP / 11.0 | −0.01 LU | 545 / 488 / 757-391-783 | 11 parts (novelty); silences 38.7 s (1.3 s) and 94.6 s (1.4 s); **drop hints at 96.1 s (after the silence) and 141.6 s (+48 dB bass, major impact)**; breakdown/quiet 40-94.6 s at −15.9 LU; peak plateau 151-213 s |
| versatile (228 s) | −6.08 / 14.3 / **+3.86 dBTP** / 9.9 | −0.08 | 350 / 211 / 720-460-749 | 14 parts; major impacts 51.0, 84.0, 162.0 s; drop hint 162.5 s; breakdowns 44.3 s and 192 s; 13 369 samples over full scale (QA `loudness:clipping`, the decode exceeds ±1) |
| jeremy (317 s) | −7.02 / 6.5 / +0.15 / 7.2 | −0.02 | 659 / 622 / 1127-414-595 | `limited_master`; **11 parts** (the fixed-threshold prototype found 3): intro soft, verse/chorus edges at 19.5, 40.1, 76.5, 113.0 s (allin1: 21.8, 40.1, 76.5, 113.0), long loud body, outro medium 288 s, quiet fade 307 s; level scale 0.90 |
| newton-vs-nye (170 s) | −10.08 / 3.5 / +0.41 / 10.5 | −0.08 | 209 / 205 / 510-543-748 | 9 parts; LRA 3.5 so levels scaled ×0.5; intro soft 0-14 s, loud body, medium/soft run-out 149.6-165.8 s, trailing silence 4.7 s; 6 major impacts (bass entries) |

Synth (56.5 s): −20.38 LUFS (truth −20.376), LRA 7.17 (truth 7.165), TP −1.0 (truth −0.994).
Runner e2e on the synth song: `mvh analyze out/_wip/builder-m1/synth --only ...` ran spectral, loudness and (after the
real separate_fast → allin1 → rhythm chain) dynamics; `mvh validate`: 32 files, 0 errors.

## Decisions

See `docs/contract/decisions/M1.md` (M1-S1..S11, M1-L1..L6, M1-D1..D9). Highlights:
- band dBFS = mean square of mid + side; viz values from the mono down-mix only;
- kick gate keeps quiet masters working (`max(p95 − 30, min(−46, p95 − 20))`);
- hit events are offline (viz re-arm ignored, crisp-onset weak hits, `viz` flag keeps viz-identical semantics available);
- loudness curves centred, `curve_offsets_s = {0.2, 1.5}`; own true peak (ffmpeg is the cross-check);
- dynamics level thresholds scale with the song's loudness range; `role_hint` is evidence only; new optional
  `meta/dynamics.json`.

## Change requests

1. **CR-M1-1** dynamics deps: add `allin1` (or a re-published section list) so the SPIKE's allin1 fallback can run; the
   guarded code path exists.
2. **CR-M1-2** catalogue: fold the additive optional fields and `meta/dynamics.json` into `catalog.py`.
3. **CR-M1-3** registry wording: `hits.*` range 0..1.5 is unused headroom (the viz envelope is clamped to 1).

## Open issues

- `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` asserts that `rhythm` is still a stub; M2 replaced
  it, so the gate's `unit` step fails for every module until the test owner updates it (not an M1 file).
- The contract synth fixture's drum one-shots (`tests/synth/dsp.kick` etc.) end abruptly (a kick still has about −20 dB
  left at 0.45 s); the truncation adds a broadband click about 40 ms before the next kick that the viz flux reads as an
  onset. Onset comparisons against the fixture truth are therefore unreliable (F1 0.34-0.64); M1's own generators fade
  the one-shots (onsets F1 0.96-1.0). Suggest the fixtures owner fades them.
- Kick-band hits include bass-note attacks (viz semantics); consumers that want drum kicks only can filter on
  `kick_conf` (or `viz`). Versatile has 350 kick-band hits vs 208 viz-strength ones.
- mid/high hit envelopes are viz's band-wide envelopes: on the synth they catch snares/hats with recall 0.5-1.0 and
  respond to other instruments in the band (no drum-specific classification; that is the drums stage).
- The 17.0 s chorus impact of the synth fixture (+0.47 LU, crash) is not detected; impacts need a ≥ 4 LU or bass step,
  a hit, or brightness on top of a step.
- Real-song dynamics have no ground truth; the drop/part checks above are plausibility checks against W0 notes and allin1.

## Gate

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gate.ps1 M1` (2026-11-08, 21:03-22:22, shared machine):

| Step | Result | Notes |
|---|---|---|
| fixture | PASS | |
| unit | FAIL (not M1) | spectral 27 passed / 4 skipped, loudness 20 / 4, dynamics 13 / 4 (skips = real-song tests, opt-in `MVH_REAL_TESTS=1`, all green when enabled). The only failure is `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs`, which asserts that `rhythm` is still a stub (M2 replaced it). |
| review | SKIP | no review folders for M1 |
| ruff | PASS | |
| contract | PASS | |
| validate | PASS | |
| e2e | PASS | full real pipeline, 1616 s; spectral 3.0 s, loudness 2.8 s, dynamics 2.6 s |
| lib-node | PASS | |
| determinism | FAIL (not M1) | 36 of 179 files differ, none of them an M1 output (`events/dynamics.json`, `meta/loudness.json`, `meta/dynamics.json`, `curves/spectrum128.u8` all identical). The differing files come from upstream/downstream stages (rhythm tables, sections, notes, lyrics, mood, meaning...) and `curves/core.f32` (shared file with their channels). M1 stages alone were checked separately: `mvh analyze <song> --only spectral,loudness,dynamics --force ...` twice gives byte-identical output for all 175 files. |

Both failing steps are outside M1's owned paths; they are listed for the W3 integrator.
