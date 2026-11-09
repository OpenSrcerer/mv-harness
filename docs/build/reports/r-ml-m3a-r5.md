# r-ml-m3a-r5: R-ML review of M3a Separation, round 5 (W3 verify)

**Verdict: pass-with-fixes.** All three round-4 findings are fixed, verified on fresh runs. One new major (R5-1) is a regression
introduced by the fixer's extra rule M3a-R4-3. There are three minors.

## Round-4 findings
| id | status | evidence |
|---|---|---|
| R4-2 RoFormer steps not bit-reproducible on ROCm | **fixed** | Two newton-vs-nye module runs, `detB` with 12.6/15.8 GiB of GPU memory held plus matmul churn: every stem, sub-stem, drum_hits, stems.json and curves/stems.f32 byte-identical; the stems also match fixer det3 (1 h earlier). Quality unchanged vs the integrator (vocals -133 dB, drums -131 dB); separate_hq 534 s vs 552 s. |
| R4-1 crash-stem artefacts at the 4 dB floor | **fixed** | The input-event check is real. Independent of its own test: jeremy ride 139 -> 163 (79 % on the 16th grid, chance 28 %), crash 25 -> 22; megafauna crash 29 -> 28. |
| R4-1b 48 kHz synthetic cymbal gate | **fixed, thin margin** | Fresh end-to-end runs. 44.1 kHz: kick 1, snare .993, hat .929, tom 1, cymbal .895. 48 kHz: kick .994, snare .98, hat .921, tom .889, cymbal .737. `pytest -m "real or slow" tests/review/M3a/r-ml`: 5 passed. |

The round-4 test `test_r4_hq_vocals_determinism.py` compared two folders made by the old code, so it could never pass. It
now compares the two round-5 current-code runs (`out/_wip/r-ml-m3a-r5/detA`, `detB`) and passes.

## New findings
- **R5-1 (major)**: the coincidence-decay rule (M3a-R4-3) drops real ride strokes that land on a kick.
  - Test: `tests/review/M3a/r-ml/test_r5_drums_coinc_kick_rides.py`. It fails on megafauna (133.85, 161.97, 166.54,
    171.12 s) and jeremy (66.71, 191.86 s), and passes on synth44, synth48 and versatile.
  - On the synthetic song every hit the rule drops is at a snare stroke.
  - The hits it drops on real songs:
    - have no snare or tom hit nearby;
    - are 6-37 dB above the kick stem and 16-43 dB above the snare stem in 4-16 kHz;
    - correlate 0.91-0.95 with the drums stem;
    - were present in the integrator's output.
  - Real ride decay exceeds the synth-tuned 9 dB (MEGAFAUNA's rides that are not at a drum stroke: 88 %, median 17.4 dB).
  - Fix: restrict the rule to snare (or tom) coincidence, or require the snare stem to be at least as loud as the candidate.
- **Minors** (in `docs/review/M3a-r-ml.md`, Round 5):
  - r5-m1: D47 in CONTRACT.md and the M3a-R4-2 decision text are stale.
  - r5-m2: the provenance cannot show that the determinism patch took effect (`deterministic_roformer` is hard-coded True;
    `STATS` is never recorded).
  - r5-m3: `coinc_decay_db`, `input_rise_db` and `input_check_below_db` are not stage params.

## Real-song reruns (current code)
- **newton-vs-nye:** two full module runs, `out/_wip/r-ml-m3a-r5/detA` and `detB`, rc 0. Bit-identical (above).
- **versatile:** `out/_wip/r-ml-m3a-r5/versatile`, rc 0, separate_hq 641 s.
  - Drum counts match the integrator's (kick 124, snare 329, tom 93, cymbal 24); hats 659 -> 658.
  - The stems differ from the fixer's 09:11 rerun at -105..-144 dB (lead -83 dB). That rerun predates the final
    rocBLAS fix (10:23), so the difference is the code change, not nondeterminism.
- **jeremy, megafauna, versatile, newton, synth:** probed with the drum core (`probe/p_coinc.py`, `p_coinc2.py`, `p_grid.py`).

## Commands
- `export MVH_RUN_OFFLINE=1; powershell.exe -NoProfile -File scripts/run.ps1 python <probe>`
- Run scripts: `out/_wip/r-ml-m3a-r5/run_det.sh` (GPU hog: `probe/hog.ps1`), `run_synth.sh`, `run_vers.sh`.
