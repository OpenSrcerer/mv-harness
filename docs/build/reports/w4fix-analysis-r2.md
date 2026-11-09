# w4fix-analysis-r2: W4 fixer, analysis group, round 2

Progress log: docs/build/progress/w4fix-analysis-r2.md. Decisions: docs/contract/decisions/W4-analysis.md (W4-AN-9, -10, -11).
Numbers only; no lyric text.

## Findings

| ID | Result |
|---|---|
| W4V-GAIN-REAL (major) | **Fixed.** One fixed analysis level (W4-AN-9) + relative dynamics silence threshold. MEGAFAUNA and Jeremy at -12 dB: sections, labels, silences, EDM roles identical to the originals. |
| W4V-GAIN-BEATS (major) | **Fixed.** rhythm scales the mix to -10 LUFS before beat_this, madmom and its DSP features; plus a meter tie-break (W4-AN-11a). Beat F 1.000 and downbeat F 1.000 between each song and its -12 dB copy. |
| W4V-KICKCURVE-CHOREO (major) | **Fixed in the code; the test still fails on 2 hit points, and the test is too strict there.** Under `kick_source = mix`, choreo takes its kick rows from hits.kick (W4-AN-10). 98 % of the groove kick steps are now on agent kicks (before: 35 %). 2 of the 7 `drum` hit points (160.12 s, 194.40 s) have no agent kick. Each has a drum-stem SNARE at the same instant (vel 0.91 and 1.0). By definition a `drum` hit point is a kick or snare hit with vel >= 0.5. The snare is not the drum-stem kick that UD2 rejected. |
| N3 a cappella half-time (minor) | Passes on the re-run synth_acap and newton_acap (feel share 0). |
| N4 spurious half-time spans (minor) | **Fixed.** A half-time run now also needs a beat-3 snare body in the 150-4000 Hz flux (W4-AN-11b). MEGAFAUNA 89-100 s and Versatile's outro are removed. Newton (0-145 s) and Versatile's two true runs stay. |

### What changed in the code (all in owned paths)
- `src/mvh/stages/loudness/level.py` (new): `gain_db_for`, `mix_gain`, `ANALYSIS_LUFS = -10`. The level is measured on the stereo canonical mix with BS.1770.
- **allin1 1.2.0:**
  - `level_target_lufs` -10 replaces the [-16, -6] band;
  - the stems are scaled by the mix gain;
  - `allin1.json.level` = {measured_lufs, measured_on, target_lufs, gain_db}.
- **rhythm 1.2.0:**
  - `analysis_lufs` -10 (scales the mix before every tracker and DSP feature);
  - `meter_late_bias` 0.25 (`fusion.decode_meter(late_bias)`);
  - `backbeat_mid_min` 1.25 (`fusion.backbeat_feel(flux_mid, mid_min)`);
  - `meta/tempo.json.analysis_level` (additive).
- **harmony 1.2.0, structure 1.4.1:** `analysis_lufs` -10 (chroma and the chord model; the structure bar features and `silence_db`). structure also gets:
  - `drop_top_min_rise` -0.25;
  - the `verse_min_before_chorus` 0.25 form rule.
- **dynamics 1.2.0:** `silence_rel_lu` 35 and `silence_cap_lufs` null. The silence threshold is now relative only.
- **choreo 1.3.1:**
  - kick rows from hits.kick under `kick_source = mix` (`mix_kick_rows`, `mix_kick_vel_floor` 0.2);
  - `groove_min_hit_vel` 0.15 (bars whose hits are all ghost-level bleed are not groove bars);
  - `meta/grooves.json.kick_rows` (additive).

### Why the extra rhythm, structure and choreo rules (regressions found on the way, fixed)
- **MEGAFAUNA bar phase.** With identical levels, the meter HMM still put the -12 dB copy's three 3-beat bars at 62 s instead of 91 s. The cause was 4e-5 of allin1 activation noise in a drumless break with flat evidence (bar F 0.85). `late_bias` breaks such ties deterministically: the irregular bar(s) go just before the next strong downbeat. The unit test shows the noise-only placement wandering over 44-78 beats; with the bias it is always 80-82.
- **Synthetic edits under the -10 LUFS target:**
  - synth_tempo95 lost both EDM roles: the top-drive drop's rise was +0.01 z at the old level and -0.01 z at the new one, so the margin is now -0.25 z;
  - synth_sr32 labelled the verse `chorus` (allin1 verse 0.36, chorus 0.60): the new verse-before-first-chorus form rule fixes it;
  - newton_acap got 2 groove bars before 145 s made only of bleed hats (vel 0.04 / 0.1): the ghost floor fixes it.
- **Dev check.** I re-ran structure and choreo on all 18 folders. Only these targeted cases changed. The one side effect: Versatile lost 8 groove bars, all ghost-only.

### Real songs vs the round-1 folders (out/_wip/w4fix-analysis/<slug>), the cost of a fixed level
- **MEGAFAUNA (+0.81 dB):**
  - the intro bar phase moved: section starts 1.46, 19.55, 37.76, 53.06, 71.2 and 80.26 become 0.48, 18.40, 36.62, 52.49, 70.63 and 79.70;
  - the 3-beat bar(s) moved from 44.6 s to 91.0-96.1 s, ending on the 96.11 s impact or section start;
  - in 0-45 s, mix kicks fall on beat 1 7 times with the new phase and 4 times with the old one, so the new phase is at least as plausible;
  - labels, EDM roles and beats are unchanged (beat F 1.0);
  - the half-time span at 89-100 s is gone (N4).
- **Jeremy (-3.0 dB):**
  - the 94.66 s verse boundary merges, as allin1 itself does at this level;
  - the 176.1 s section becomes verse, which agrees with allin1's segment label;
  - 194.1 s moves to 185.07 s, and the outro start moves 306.39 → 307.75 s;
  - beat F 0.957 and bar F 0.947 against the old grid;
  - no review test on Jeremy fails.
- **Versatile (-3.9 dB):**
  - the label mode flips from allin1 to structural (labels build/drop/breakdown/inst/break; EDM roles unchanged). The allin1 verse+chorus share sits at the 0.3 threshold, and the round-1 dev run had flipped the same way;
  - beat F 0.964;
  - the outro half-time span is gone (N4).
- **Newton (+0.1 dB):** identical.
- **Synth:** identical, and still matches the truth.

## Tests
- **Unit:** allin1, rhythm, dynamics, structure, choreo, harmony all pass. New tests:
  - `tests/unit/allin1/test_level_band.py` (fixed target, loud master vs -12 dB copy);
  - `tests/unit/dynamics/test_w4_perturbations.py` (relative silence);
  - `tests/unit/rhythm/test_w4_backbeat.py` (hats-only beat 3, meter tie-break);
  - `tests/unit/choreo/test_w4v_mix_kick_rows.py`;
  - `tests/unit/structure/test_w4_stop_bar.py` (params).
- **Review, on my re-analysed folders:** 60 pass, 1 skip, 1 fail (the kick hit-point test above), for:
  - tests/review/W4/verify-analysis, tests/review/W4/adversary and tests/review/W3/critic;
  - 18 folders in out/_wip/w4fix-analysis-r2: 6 baselines, 5 adversary perturbations and 7 verifier runs, all analyze 0 / validate 0;
  - the skip: MEGAFAUNA now has no half_time segment.

  Command (Git Bash, from the repo root; the project venv python directly, because uv run drops PYTHONPATH):

  ```
  W4VA_RUNS=out/_wip/w4fix-analysis-r2 W4VA_BASE=out/_wip/w4fix-analysis-r2 W4FIX_RUNS=out/_wip/w4fix-analysis-r2 \
  MVH_REVIEW_RUNS=out/_wip/w4fix-analysis-r2 PYTHONPATH=out/_wip/w4fix-analysis-r2 \
  .venv/Scripts/python.exe -m pytest -q -p redirect_plugin tests/review/W4/verify-analysis tests/review/W4/adversary tests/review/W3/critic -m "slow or not slow"
  ```

  `redirect_plugin.py` now also patches conftest plugins. Before, the adversary's `perturbed` fixture still read out/_wip/r-adversary.
- **Other review runs:**
  - opt-in real M2/M4 review tests (`MVH_REAL_TESTS=1 -m real`): 14 pass;
  - W4 dogfood: 4 pass.
- **Gates:**
  - M1 -SkipE2E: PASS;
  - M4 -SkipE2E: PASS;
  - M2 -SkipE2E: PASS (before structure 1.4.1 / choreo 1.3.1);
  - M2 full gate (e2e + determinism) on the final code: PASS (`out/_wip/w4fix-analysis-r2/logs/gate-M2-full.log`).

## Run folders and tools (out/_wip/w4fix-analysis-r2)
- `run_queue.ps1 -NameList a,b -Tag rN` re-analyses the folders in place. It is resumable. Logs are in `logs/`.
- `devrun.py` / `dr.sh` chain stages on cached upstreams into `dev/<tag>/<stage>`.
- `devcmp.py` compares sections, beat/bar F, silences, EDM roles, 3-beat bars and feel.
- `phase.py` shows the beat-in-bar of kicks and snares.
- `bbproto.py` gives the band ratios on the half-time spans.
- `hpcheck.py` explains the `drum` hit points.
