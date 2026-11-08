# builder-m3a report: M3a Separation (separate_fast, separate_hq, stem_activity, drums)

Status: **done** (all four stages real, on all four real songs and the synthetic song; unit and real-song tests green).
Gate: see "Gate" below. Progress log: `docs/build/progress/builder-m3a.md`. Contract decisions: `docs/contract/decisions/M3a.md`.

## Files (owned paths only)

| Path | What |
|---|---|
| `src/mvh/stages/separate_fast/__init__.py` | htdemucs 4-stem (htdemucs_6s in draft) via demucs-onnx, array route, own ORT session |
| `src/mvh/stages/separate_hq/{__init__,worker}.py` | parent side: worker call, stem assembly, invariants, `meta/separation.json`, htdemucs degraded fallback |
| `src/mvh/sep/{demucs,fit,invariants,hq_worker}.py` | demucs-onnx array route; resample/fit to the mix; sum/gain/diff invariants; the sep-env worker job (lifted from `envs/sep/tools/separate_song.py`) |
| `src/mvh/stages/stem_activity/{__init__,core}.py` | per-stem curves, segments, presence with cross-model confidence |
| `src/mvh/stages/drums/{__init__,core}.py` | detector, DrumSep path, classifier path, velocities, envelopes |
| `src/mvh/contract/catalog.py` (models_lock schema only, explicit permission) | `mvh/envelope/models_lock` accepts what W0 wrote; regenerated with `python -m mvh.contract.gen` |
| `tests/unit/{separate_fast,separate_hq,stem_activity,drums}/` | 35 unit tests + 10 real-song / real-model tests (opt-in, `-m real` or `MVH_RUN_REAL=1`) |
| `tests/synth/m3a/` | in-process stage harness (`run_stage` via `mvh.runner.child`), fixture upstreams, the `real` marker hook |
| `docs/contract/decisions/M3a.md` | additive fields, interpretations M3a-1..15, models_lock note |

## What each stage does

**separate_fast** (`1.0.0`, main env). demucs-onnx `htdemucs` (4 stems; `htdemucs_6s` in draft) through
`_chunked_separate_single` with our own onnxruntime session on the fp16 weights from `models.lock.json` (arrays in,
never a path). The song is mean/std normalised like `demucs.separate` (allin1 was trained on that pipeline). Stems are
cache-only float32 WAV `fast/<stem>.wav` at the song's rate and length; `fast/separation.json` records the
informational sum residual (no gate, SPIKE: 2-10 % RMS).

**separate_hq** (`1.0.0`, sep worker, variants rocm -> cpu -> htdemucs degraded). The worker
(`mvh.sep.hq_worker.run_job`) runs four audio-separator models, each a separate load/separate/free cycle under its own
heavy slot + `gpu.lock` (`ctx.worker(..., hold_slot=False)`, like the reference script): BS-RoFormer-SW 6-stem on
the mix, Mel-RoFormer vocals on the mix, the karaoke model on the Mel vocals, MDX23C DrumSep on the SW drums.
`normalization_threshold = 100.0` is set as an attribute after `Separator()` (the constructor rejects > 1),
`amplification_threshold = 0.0`, float WAV, explicit model files from the job. The parent builds:
vocals = Mel; lead = karaoke vocals; backing = vocals - lead (exact; always written, D17); drums/bass/guitar/piano/other = SW;
instrumental = mix - vocals (exact); drum sub-stems = DrumSep (`hh` -> hihat). SW's own vocals are kept cache-only
(`sep/vocals_sw.flac`) as an independent vote for stem_activity. Invariants and checks go to `meta/separation.json`
(six-stem SW sum residual gate -20 dB, per-stem LS gain gate 0.1 dB within 6 dB of the mix / 0.5 dB within 20 dB,
inst+voc vs mix, lead+backing vs vocals, karaoke model's own backing vs computed, DrumSep sum vs drums, Mel vs SW
vocals); a failed gate is a QA flag (`sep:sum_residual`, `sep:gain`) and a warning. Non-44.1 kHz songs: separators
get the 44.1 kHz mix, stems are resampled back with ffmpeg and fitted (instrumental stays exact on the native mix).

**stem_activity** (`1.0.0`). Per stem (9 stems + 6 DrumSep sub-stems): `stem.{stem}.rms_db/rel_db/level/active`
at 100 Hz, `events/stem_activity.json` segments, `meta/stems.json`. Activity = > -45 dBFS and within 18 dB of the
reference (the mix, or the parent stem for split stems, M3a-4) on a 0.4 s decision RMS with 300/500 ms hysteresis.
**Presence is not energy alone** (SPIKE): `conf` = per-frame agreement with an independent separator (htdemucs from
separate_fast; plus SW's vocals for vocals); `present` needs energy AND `conf >= 0.4`; `present_energy`, `conf`,
`evidence[]` are exposed so M3b/M5 can combine them with the tagger and lyrics; unconfirmed stems get
`<stem>:unconfirmed` flags and warnings.

**drums** (`1.0.0`). DrumSep path: a 1 ms rise-ratio onset detector on each sub-stem (adaptive threshold from the
stem's own ODF spread), event time = the one-shot's first sample, then DrumSep artefact rules (M3a-14: cross-stem
bleed, kick/snare strike-rise floor, dull hi-hat bleed, open-hat copies in the cymbal stems, cymbal merge). A band
classifier on the full drum stem confirms hits (+0.15 conf, `classifier_agrees`) and is the degraded fallback when
no sub-stems exist. `vel` = peak / p98 peak of the same drum; hits outside `stem.drums.active` keep x0.6 confidence;
`drums.<drum>` 100 Hz envelopes follow the flash rule; `perc` stays empty (DrumSep has no percussion stem).

## Accuracy vs thresholds (synthetic song)

Drums, F1 at +-10 ms (PLAN §7: kick events >= 0.95; kick/snare/hat >= 0.9; tom/cymbal >= 0.7):

| Input | kick | snare | hat | tom | cymbal | onset error |
|---|---|---|---|---|---|---|
| Generator sub-stems (fixture stems; asserted in unit tests) | **1.000** | **1.000** | **1.000** | **0.800** | **1.000** | median 0.02-0.11 ms; toms 3.3 ms |
| Real ROCm DrumSep stems of the rendered song (stage output) | 1.000 | 0.979 | 0.749 | 0.800 | 0.615 | kick median 0.2 ms, p95 0.9 ms |
| Classifier fallback on the generator drum stem | 0.954 | 0.861 | 0.777 | 0.27 | 0 | (fallback only; asserted >= .9/.8/.7 kick/snare/hat) |

Before the M3a-14 rules the real-separated numbers were kick .939, snare .966, hat .688, tom .80, cymbal .40. The hat
and cymbal thresholds are **not** met on separated stems: 36 of 182 synthetic hats (soft closed hats 125 ms after an
open hat) produce no onset at all in the DrumSep hi-hat stem (recall ceiling 0.80), and DrumSep splits the synthetic
ride between ride and crash. Velocity: generator stems kick corr .999, snare .998, hat .867.

Separation on the synthetic song (real ROCm run): SW sum residual **-35.3 dB** (gate -20), gain gate pass (|gain| <=
0.022 dB on gated stems), inst + voc vs mix **-150 dB** (exact), lead + backing vs vocals **-150 dB**, karaoke model's
backing vs computed -150 dB, DrumSep sum vs drums -31.4 dB. separate_fast htdemucs sum residual -31.5 dB (info).

stem_activity on the synthetic song: guitar absent (none in the song), vocals/drums conf >= 0.99, vocal activity covers
>= 95 % of sung words (unit tests assert these).

Determinism: synthetic `ingest,separate_fast,separate_hq --force` twice on ROCm -> **0 of 94 files differ**.

## Real songs (all four, real upstream separation; no lyric text anywhere)

Separation (`meta/separation.json`, all variant rocm, not degraded, no flags):

| Song (s) | SW sum dB | gain gate | inst+voc / lead+back | DrumSep vs drums | Mel vs SW vocals | fast sum dB | hq worker wall s |
|---|---|---|---|---|---|---|---|
| newton-vs-nye (170) | -36.0 | pass | -150 / -150 | -31.4 | -18.4 | -33.6 | 550 (incl. slot waits) |
| megafauna (217) | -23.6 | pass | -150 / -150 | -23.6 | -0.02 (SW vocals at -47 dB) | -29.4 | 298 |
| jeremy (317) | -30.3 | pass | -150 / -150 | -29.0 | -16.0 | -29.0 | 422 |
| versatile (228) | -35.2 | pass | -150 / -150 | -20.9 | -7.2 | -30.3 | 567 |
| synth (57) | -35.3 | pass | -150 / -150 | -31.4 | -18.2 | -31.5 | 154 |

Pure model compute is about 1x real time on ROCm (jeremy: SW 130 s, Mel 95 s, karaoke 86 s, DrumSep 21 s). Wall
times include waits for heavy slots held by seven other agents (separate_fast waited up to 31 min for a slot).
Several songs exceed full scale in separated stems (peaks up to 1.85 on versatile drums): the float `.wav` twins are
written next to the FLACs as the contract allows.

stem_activity (present stems; vocals conf):

| Song | vocals | present (not present) | flags |
|---|---|---|---|
| newton-vs-nye | present, conf 0.99, 78 % active | vocals, lead, backing (3 % active), drums, bass, other, all drum subs but ride (guitar, piano, ride) | - |
| megafauna | **not present**, conf 0.30 (energy says yes: the Mel stem holds synth leads at -12.8 dB; SW sees vocals at -47 dB) | drums, bass, guitar, other, all drum subs (vocals, lead, backing, piano) | `vocals:unconfirmed`, `backing_vocals:unconfirmed` |
| jeremy | present, conf 0.99, 84 % active | everything but piano | - |
| versatile | present, conf 0.71, 9 % active (sparse vocal) | vocals, lead (0.99), backing (0.64), drums, bass, other, all drum subs (guitar, piano) | - |

drums (hits per drum; all DrumSep path, status ok):

| Song | kick | snare | hat | tom | cymbal | notes |
|---|---|---|---|---|---|---|
| newton-vs-nye | 200 | 322 | 752 | 77 | 59 | kick IOI median 0.65 s |
| megafauna | 632 | 508 | 804 | 382 | 137 | dull electronic hats (typical brightness -6.6 dB): the relative rule still works |
| jeremy | 656 | 356 | 478 | 93 | 510 | 534 hi-hat candidates dropped as bleed; ride/crash busy (cymbal-heavy mix) |
| versatile | 123 | 304 | 501 | 135 | 125 | |
| synth | 85 | 71 | 165 | 7 | 19 | truth 85/74/182/8/20 |

Real-song tests (`-m real`): stem_activity 4/4 (vocal presence + conf band per song), drums 4/4 (hit-rate snapshots
with tolerances) pass; separate_fast / separate_hq real tests: see Gate.

## Decisions (details in docs/contract/decisions/M3a.md)

M3a-1 backing = vocals - lead (exact); M3a-2 sum gate on the six SW stems is a flag, not a failure; M3a-3 0.4 s
activity decision window; M3a-4 split stems judged against their parent; M3a-5 presence = energy AND cross-model
confirmation; M3a-6 one shared level normalisation; M3a-7 velocity = peak / p98 per drum; M3a-8 event time = first
sample; M3a-9 `perc` empty; M3a-10 classifier only as fallback/confirmation; M3a-11 hits outside activity kept at x0.6;
M3a-12 separate_fast normalisation; M3a-13 non-44.1 kHz handling; M3a-14 DrumSep artefact rules; M3a-15 known
ceiling of hat/cymbal on separated stems; models_lock envelope schema widened (schema side only).

## Gate

`scripts\gate.ps1 M3a` (21:31-22:35, heavy slots contended by other agents):

| Step | Result | Detail |
|---|---|---|
| fixture | PASS | |
| unit | FAIL (external) | separate_fast, separate_hq, stem_activity, drums all pass; `tests/unit/contract::test_stub_files_are_stubs` fails because it asserts `rhythm` (M2) is still a stub |
| review | SKIP | no tests/review/M3a |
| ruff | PASS | |
| contract | PASS | `gen --check` |
| validate | PASS | |
| e2e | PASS | full 25-stage analyze of the synthetic song + validate (1894 s) |
| lib-node | PASS | |
| determinism | FAIL (external) | 23 of 179 files differ, **none of them M3a outputs**: tables/beats.csv, bars.csv, sections, phrases, counts, cues, moments, hit_points, edm_roles, mood, structure, lyrics, meaning, brief, viewer, manifest and the shared curves/core.f32. All stems, `meta/separation.json`, `meta/stems.json`, `curves/stems.f32`, `events/stem_activity.json`, `events/drum_hits.json` are identical. The cache-only htdemucs stems (`.cache/separate_fast/*/fast/*.wav`, which allin1 reads) are bitwise identical across three runs, so the divergence starts downstream (beats). |

Real-marked tests (`-m real`): separate_fast 1/1, separate_hq 1/1 (real worker on a synthetic excerpt), stem_activity
4/4, drums 4/4 pass.

## Change requests (W3 integrator)

1. `tests/unit/contract/test_catalog_dag.py::test_stub_files_are_stubs` must stop asserting that real stages are stubs.
2. Determinism: beats/bars (rhythm or allin1, M2) differ between two `--force` runs, and everything downstream with
   them (structure, cues, mood, lyrics, meaning, viewer). M3a outputs and the htdemucs stems allin1 reads are identical.
3. `mvh.runner.locks` heavy-slot waiters poll every 15 s while other holders re-acquire within 2 s: the runner's own
   stage-level waits (e.g. separate_fast) starve (31 min observed). A FIFO ticket or a shorter poll would fix it.
4. Optional: a `pytest.mark.real` registration in the project config (M3a registers it in its own conftests).

## Open issues

- Hat (0.749) and cymbal (0.615) F1 on real DrumSep stems of the synthetic song are below the PLAN thresholds
  (M3a-15); generator-stem thresholds pass. A spectral-flux onset path for the hi-hat stem could recover chokes.
- Vocal presence on MEGAFAUNA is decided by the cross-model vote (0.30, not present); M3b/M5 should combine `conf`
  with the tagger and lyrics as planned.
- `perc` is always empty (DrumSep has no percussion class).
