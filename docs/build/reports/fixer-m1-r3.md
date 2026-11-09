# fixer-m1-r3 report (W3 module fix, round 1, M1 Signal)

## What changed
hits.kick detection (spectral) was redesigned from first principles; loudness and dynamics are unchanged.

- `src/mvh/stages/spectral/dsp.py`: new `KickAnalysis`, `GlideMeter`, `KickEvidence`, `kick_route`, `select_kick_events`,
  `low_band_envelopes`, `max_step`. The round-1/2 kick helpers are removed: refractory, click roll rule, zero-crossing
  glide, `low_excess_db`, `kick_confidence`, `click_rise_db`, `click_peak_db`.
- `src/mvh/stages/spectral/stage.py`: kick path. `kick_conf` now comes from `KickEvidence.conf()`, and the summary gains
  `hits.kick.routes` (sweep / body counts).
- `src/mvh/stages/spectral/__init__.py`: new `kick_*` params. The old `kick_*` and `weak_kick_conf` params are gone.
  Stage version is now 1.1.0.
- `tests/unit/spectral/test_spectral.py`:
  - sub-bass groove at F1 >= 0.95 (PLAN §7, restored from 0.7) on 6 variants: default, seed 3, four-on-the-floor,
    seed 5, 140 BPM, dense;
  - 8 riff/rock/roll textures;
  - `GlideMeter` and `max_step` helper tests;
  - the real test now compares against the DrumSep kick stem (recall >= 0.93), not W0 viz counts.
- `docs/contract/decisions/M1.md`:
  - M1-S5 and M1-S8 revised;
  - new M1-S12 (kick events) and M1-S13 (precedence between hits.kick and drum_hits, seam S06);
  - new change requests CR-M1-4 and CR-M1-5.

## Design (M1-S12)
A kick is a low-band onset with physical kick evidence. The viz kick-band envelope alone no longer decides.

**Candidates.** Every step of three bands is a candidate:
- the <= 400 Hz band;
- the 90-200 Hz band, where a kick's pitch sweep starts;
- the 1.5-5 kHz beater-click band.

Each candidate is timed on a ripple-robust onset score: the post 10 ms mean minus the **max** of the 20 ms before, plus
half the click step. This is SuperFlux along time. Beating ripple from a held bass cannot step. Only one onset is kept
per 20 ms. The reported time is the steepest <= 400 Hz (+ click) step within +-5 ms.

**Evidence measured at each onset:**
- `attack`: the 90-250 Hz burst above the level before and above the level 55-85 ms after.
- `glide`: the pitch drop of the energy the onset *adds* to 30-160 Hz. It is the RMS frequency from the derivative
  power, early (2-25 ms) over late (40-75 ms), after subtracting the pre-onset power, capped at half of each window. A
  held bass note underneath cancels out. A bass-note onset reads ~1, a kick 1.4-2.5.
- `click`.
- The body onset (30-150 Hz) and its decay within 90 ms.
- The viz kick gate.

**Routes:**
- "sweep": burst plus pitch drop, or burst plus click. This covers electronic kicks and most modern kicks.
- "body": a strong 30-150 Hz onset that decays >= 8 dB within 90 ms and is centred >= 68 Hz. This covers acoustic rock
  kicks, whose click is masked by guitars and which have little sweep.

Faint thumps more than 12 dB below the median kick are dropped; these are vocal plosives. There is **no refractory**:
a bass-note onset can no longer swallow the kick after it, and rolls need none.

`viz` flag: true when the viz attack episode that the onset falls in (-30..+60 ms) registered a hit. Viz arms once per
attack. This keeps the viz-parity test, given that the real viz also registers bass-note hits, which hits.kick must not
contain.

## Results
See the structured summary: accuracy, tests, gate.

## Numbers

### Synthetic (F1 at +-10 ms)

| Signal | Before | After |
|---|---|---|
| Fixture song | 0.864 | 0.982 (P 0.977, R 0.988) |
| groove default | 0.754 | 0.992 |
| groove seed 3 | 0.739 | 0.992 |
| groove four-on-the-floor | 0.880 | 0.989 |
| 16th bass riff | 0.889 | 1.0 |
| 16th rolls at 170 BPM | 0.897 | 1.0 |
| 16th rolls at 180 BPM | 0.061 | 1.0 |
| 16th rolls at 160 BPM under a crash | 0.609 | 1.0 |
| Rock pairs over a held bass, 140 BPM | 0.769 | 1.0 |
| Rock pairs over a held bass, 160 BPM | 0.667 | 1.0 |

- The previously passing textures (kicks over bass, hats, crash 8ths, 16ths at 160 BPM) and kick-free material all
  still pass (0 events on kick-free material).
- I also checked 20 extra textures. The old code failed 15 of them; the new code fails none. Worst cases: dense groove
  F1 0.969, groove at 140 BPM 0.953. The extras are: other groove seeds, a quiet master, 100 and 140 BPM, rolls up to
  220 BPM, rolls under a crash, riffs at 100 and 150 BPM, rock pairs at 100-180 BPM.
- Timing error: median -1.25 ms, 95th percentile of |error| 2.4 ms.

### Real songs: re-run on copies of the integrator's max folders

Folders are under `out/_wip/fixer-m1-r3/<slug>`. The table shows hits.kick against the DrumSep kick rows (±30 ms
agreement), before and after.

| Song | Events | hits.kick -> drum kick | drum kick -> hits.kick |
|---|---|---|---|
| Jeremy | 594 -> 560 | 0.82 -> 0.90 | 0.76 -> 0.79 |
| Newton | 206 -> 197 | 0.94 -> 0.99 | 0.97 -> 0.97 |
| Versatile | 183 -> 112 | 0.58 -> 0.97 | 0.85 -> 0.88 |
| Synthetic | 91 -> 86 | 0.84 -> 0.98 | 0.89 -> 0.99 |
| MEGAFAUNA | 335 -> 179 | 0.42 -> 0.49 | 0.23 -> 0.14 |

- MEGAFAUNA's DrumSep kick stem is hat bleed (CR-M1-4).
- Recall of the unambiguous kick-stem onsets: Jeremy 0.953, Newton 0.99, Versatile 0.99.
- All other spectral events are unchanged, and so are loudness, impacts, silences and stops on every song.
- dynamics (driven by kick_rate):
  - unchanged on the synthetic song, Newton and Versatile (same parts and role hints);
  - MEGAFAUNA: the drops at 96.1 s and 141.8 s are kept; the weak drop hint at 28.7 s (score 0.74) is lost. The
    boundary moved to 31.0 s because the old kick density came from bass and percussion events.
  - Jeremy: 2 more parts (an intro split at 10.9 s, a peak at 265.4 s) and outro breakdown hints. The drop at 19.5 s is
    kept.

## Gate (scripts\gate.ps1 M1, rc=1)

| Step | Result |
|---|---|
| fixture, review (M1 = 0), validate, e2e, lib-node, determinism | PASS |
| unit | FAIL: spectral, loudness and dynamics pass; tests/unit/contract fails (not M1) |
| ruff | FAIL at run time: a vocals file; clean on re-check |
| contract | FAIL: docs/CONTRACT.md out of date (not M1) |

The tests/unit/contract failures are `test_deps_match_plan` (vocals deps now include lyrics) and
`test_generated_artifacts_up_to_date`.
