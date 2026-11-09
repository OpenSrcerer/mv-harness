# fixer-m1-r4: M1 Signal, W3 module fix round 2

Inputs: the R-DSP round-4 verify (docs/build/reports/r-dsp-m1-r4.md), its failing tests in
`tests/review/M1/r-dsp/test_rdsp_r4_kicks.py`, the minors m20-m24 (docs/review/M1-r-dsp.md) and seam S06
(`tests/integration/M1/test_real_kick_sources_agree.py`).

## What changed

### spectral: kick events (`src/mvh/stages/spectral/dsp.py`, stage version 1.1.0 -> 1.2.0)
The kick selector stays evidence-based (one physical signature per *route*), but every rule that the review showed was
tied to the one synthetic kick was widened, and the faint-thump filter was made scale invariant.

| Finding | Cause | Fix |
|---|---|---|
| R4-M1 acoustic kick over a held bass (F1 0.588) | the body route measures decay on the whole band (the bass cannot decay); no sweep | new route **`click`**: a beater click >= 15 dB on a low-band onset with a burst (attack >= 3.5, <= 400 Hz excess >= 3, 30-150 Hz onset >= 4.5, power +3 dB). A bass-note onset has no 1.5-5 kHz click |
| R4-M1 TR-808 over a held bass (F1 0.551, events 11-21 ms early) | the sweep route needs a burst above ~150 Hz; the early events were a hat click 21 ms before the kick winning the 20 ms NMS by 0.1 dB | new route **`808`** (pitch drop of the added energy >= 1.2 on a clear low-band onset: attack >= 3, body onset >= 5.5, power +5, <= 400 Hz excess >= 2.5); NMS priority = an own <= 400 Hz or 90-200 Hz step >= 2 dB first, then the onset score (a click alone cannot take a kick's slot) |
| R4-M2 sidechain-ducked sub bass (fixture 0.667 / 0.0, 909 0.118) | "every kick adds low-band energy" | new route **`duck`**: attack >= 4.5, click >= 15 dB and a pitch drop >= 1.6 on the added *or the whole* band (`glide_raw`: under a duck, subtracting the pre-onset bass removes more than is there), with no low-band rise required |
| R4-M3 quiet intro (0/16), fade-out | faint-thump filter relative to the song's median kick | body power **relative to the local mix level** (the quieter RMS of the 1.5 s before / after) must be within 12 dB of the median kick's; an event > 12 dB below the song's median kick body must also have kick_conf >= 0.7 (keeps Versatile's quiet-intro synth hits out) |
| m20 kick on the first sample | `find_peaks` skips array edges | the analysis prepends 0.1 s of silence (`kick_pad_s`) |
| m21 fixture kick, 16ths at 180 BPM under a crash (0.927) | each kick sits on the previous one's tail: the pitch drop reads 1.17-1.24 and the low band barely rises | new iterative route **`roll`**: attack >= 12 dB with glide >= 1.1, 40-150 ms after an accepted kick |
| m22 Jeremy snares (10 % of hits.kick) | - | not changed (see open issues); kick_conf now also has a clicky-body term |
| m23 role_score up to 1.2 | build score not clipped | `dynamics/stage.py`: ranked on the raw score, reported `min(1, score)` |

`KickEvidence` gains `glide_raw`; `kick_conf` = the strongest of the sweep / duck / body / clicky-body evidence
combinations; `dsp.KICK_ROUTES` lists the routes and the stage meta counts them (`hits.kick.routes`). New params (all
`kick_*` in `spectral/__init__.py`): `duck_click_db`, `cb_*`, `s808_*`, `roll_*`, `quiet_conf`, `level_win_s`,
`nms_low_step_db`, `pad_s`. Decisions: docs/contract/decisions/M1.md M1-S12 (revised), M1-S13 (revised), M1-D10,
CR-M1-4 (revised), CR-M1-5 (superseded), CR-M1-6 (new).

Tried and dropped (each made something else worse): a causal low-pass energy-ratio onset timer (+-10 ms jitter); a
forward fine-timing search to +25 ms (moved Versatile kicks onto later peaks); dedupe by kick_conf or by "primary
route" (events anchored 20 ms early by the 90-200 Hz band's zero-phase pre-ringing read *stronger* evidence, so
Versatile kicks moved 20 ms early); NMS on a no-Hilbert power step (broke the duck and 140 BPM groove cases).

### Tests
- `tests/synth/m1/kicks.py` (new): kick designs and mixes **independent of the review's generators** (other kick
  parameters, tempos, gains): acoustic / TR-808 / TR-909 / fixture kicks over a held bass, a 92 % sidechain-ducked
  sub, a 16 dB quiet intro, a 4 dB/bar fade-out, the fixture kick's 16ths at 180 BPM under a crash, a kick on sample 0.
- `tests/unit/spectral/test_spectral.py`: `test_kick_designs_and_mix_situations` (10 cases), `test_kick_on_the_first_sample`,
  `test_kick_routes_and_conf_are_reported`, and `test_clickless_808_over_a_held_bass_note` marked **xfail(strict)**: a
  second 808 design (82 -> 48 Hz) over the held bass scores F1 0.80 (known limit, see open issues).
- `tests/unit/dynamics/test_dynamics.py`: role_score within 0..1.

## Results

### Synthetic (scratch harness, PLAN §7 F1 at +-10 ms; before = the 1.1.0 selector)
| case | before | after |
|---|---|---|
| review R4: acoustic kick over a held bass (0.5) | 0.588 | 1.000 |
| review R4: TR-808 over a held bass (0.5) | 0.551 | 0.968 |
| review R4: ducked sub, fixture kick, bass 0.7 / 1.0 | 0.667 / 0.000 | 1.000 / 0.989 |
| review R4: ducked sub, 909, bass 0.7 | 0.118 | 1.000 |
| review R4: quiet intro -14 dB (recall of all 64) | 0.857 | 1.000 |
| fade-out 6 dB/bar (review's probe) | 0.884 | 0.957 |
| m21: fixture kick 16ths @180 BPM under a crash | 0.927 | 1.000 |
| contract fixture song | 0.982 | 0.982 |
| groove 140 BPM (builder unit test) | 0.953 | 0.953 |
All earlier review textures (round 1-3: groove variants, 16th riff, rock pairs 100-180 BPM, 16th rolls 150-220 BPM with
and without a crash, 8ths under a crash 130-190 BPM, kick-free piano / snare+hat songs) still pass (44 cases).
The independent signals of `tests/synth/m1/kicks.py`: 14 of 15 >= 0.95 (the xfail 808 design: 0.80).

### Real songs (re-run of spectral, loudness, dynamics on copies of the integrator's max folders,
`out/_wip/fixer-m1-r4/<slug>`, comparison `out/_wip/fixer-m1-r4/cmp.py` -> `cmp.log`)
hits.kick vs DrumSep kick rows within 30 ms (est->drum / drum->est), all rows and vel >= 0.5 rows:
| song | integrator (W2 selector) n, all, strong | fixer-m1-r4 n, all, strong |
|---|---|---|
| synth | 91, .84/.89, .84/.89 | 86, .98/.99, .98/.99 |
| newton-vs-nye | 206, .94/.97, .94/.98 | 200, .98/.98, .98/.99 |
| versatile | 183, .58/.85, .57/.96 | 113, .96/.88, .95/.99 |
| jeremy | 594, .82/.76, .81/.92 | 559, .90/.79, .89/.95 |
| megafauna | 335, .42/.23, .13/.27 | 188, .49/.15, .19/.22 |
Against fixer-m1-r3's selector (same comparison, scratch harness): synth .98/.99, newton .99/.97, versatile .97/.88,
megafauna .49/.14, jeremy .90/.79: no regression beyond +-0.01. The kick-stem recall unit tests (real: jeremy, newton,
versatile) pass.

No regression elsewhere: hits.mid / hits.high, silences, stops and meta/loudness.json are identical on all five songs;
impacts keep their count and strength (a few `t` move to a different transient: newton 2, versatile 2, megafauna 4).
dynamics: same boundaries and levels on synth, newton and versatile; role_score now <= 1 (newton 1.104 -> 1.0, versatile
1.071 -> 1.0). The kick-rate feature changes the segmentation on MEGAFAUNA (11 -> 12 parts; the weak 28.7 s drop hint,
score 0.74, goes: allin1 / edm_roles have no drop there, as the R-DSP r4 review noted) and Jeremy (10 -> 13 parts, the
19.5 s drop kept, two outro breakdown hints added), as with fixer-m1-r3.

### Tests and gate
- `pytest tests/review/M1 tests/unit/{spectral,loudness,dynamics}`: all pass (review: 31 passed; unit: 87 passed, 11 skipped
  (real-marked), 1 xfailed as intended). ruff on the M1 paths: clean.
- Real-marked: `tests/unit/spectral -k real_song` (kick-stem recall on jeremy, newton, versatile): 3 passed.
  `tests/integration/M1`: 1 failed (S06, see open issues).
- `scripts\gate.ps1 M1` (log `out/_wip/fixer-m1-r4/gate.log`), rc 1:
  fixture PASS, **unit FAIL only in tests/unit/contract** (spectral=0 loudness=0 dynamics=0), **review PASS**
  (tests/review/M1), ruff FAIL (at gate time also my `tests/synth/m1/kicks.py` import order, fixed afterwards; still
  `src/mvh/sep/determinism.py`, not M1), contract FAIL (CONTRACT.md generated region stale after the vocals dep change,
  not M1), validate PASS, e2e PASS (760 s), lib-node PASS, **determinism FAIL**: 34 of 181 files differ, rooted in
  the separation stems (`stems/{vocals,lead_vocals,backing_vocals,instrumental}.flac`, meta/separation.json) and what
  derives from them (vocals, lyrics, lipsync, instruments, stem curves, the shared curves/core.f32 / index / manifest /
  viewer). No M1 event file differs (hits.*, loudness, dynamics, impacts, silences, stops are byte-identical across the
  two runs). Not an M1 issue: the W3 S01 determinism fix covered the DrumSep sub-stems; the vocal / instrumental stems
  are now the non-reproducible ones (or a concurrent change to separation).

## Open issues
- **S06 (tests/integration/M1/test_real_kick_sources_agree.py) still fails, and cannot pass from M1's side.** It
  compares hits.kick with all 647 DrumSep kick rows of MEGAFAUNA; 482 of them are low-velocity hat bleed (CR-M1-4), so
  even a perfect detector of the 165 strong rows scores 0.26 the other way. On the strong rows the mix's low band does
  not show the kick (sidechain drop: the kick replaces the ducked bass, the mix 30-150 Hz level changes by -2.3..+0.7 dB
  median), so spectral matches 0.19 / 0.22 of them. The test also reads the integrator's pre-fix folder (m24).
  Proposed: CR-M1-4 (bleed filter in drums), CR-M1-6 (one fused kick timeline for consumers), and the test changed to
  vel >= 0.5 rows or to the fused timeline.
- Known limit (xfail unit test): a clickless 808 that starts below ~85 Hz over a held bass is anchored ~10 ms early (the
  90-200 Hz band's zero-phase pre-ringing) or missed (pitch drop 1.15-1.2). The review's 808 (80 -> 50 Hz at 120 BPM)
  passes at F1 0.968, a thin margin. Also not handled: a sine "sub thump" kick (no sweep, no click) over a bass, and kicks
  with neither click nor pitch drop under a sidechain duck (no mix-only evidence).
- m22 (Jeremy snares in hits.kick, ~10 %): unchanged. A snare whose hit coincides with a bass-note onset can pass the
  new `click` route too; on Jeremy hits.kick vs DrumSep improved (0.90 / 0.79 vs 0.82 / 0.76), so no new snares
  showed up there.
- Non-M1 gate failures: `tests/unit/contract` (test_deps_match_plan, test_generated_artifacts_up_to_date) and the
  `contract` step fail because the vocals stage gained a `lyrics` dep at 08:41 (another agent) and docs/CONTRACT.md's
  generated region was not regenerated; ruff flags `src/mvh/sep/determinism.py` (import order, not M1).
- By mistake I created an empty folder `C:\OPENSR~1` (a mistyped Write path; the one-byte file in it was removed, the
  folder removal needs a person's approval). Delete it by hand.

