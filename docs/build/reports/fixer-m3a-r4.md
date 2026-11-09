# fixer-m3a-r4 report (M3a Separation, W3 round 2)

## Findings
- **R3-1 (ride in 8th notes)**: already fixed in round 3 (`cymbal_rise_db` 4); review test passes.
- **R4-1 (low-rise crash / ride hits are DrumSep artefacts)** `drums.core.drumsep_hits`: a ride / crash candidate rising < 8 dB in its own
  sub-stem must be a >= 3 dB 6-16 kHz event in the DrumSep input (`drums_mix` = the drums stem, else the sub-stem sum).
  `tests/review/M3a/r-ml/test_r4_drums_crash_floor.py` passes (jeremy, megafauna). jeremy cymbals: integrator 169, round 3 275, now 189.
- **R4-2 (vocals / karaoke not bit-reproducible on ROCm)** `src/mvh/sep/determinism.py` + `hq_worker`. Causes found by hashing per-chunk
  model outputs across processes (the model had exactly two possible outputs per input):
  1. Mel mask sum = atomic float `scatter_add_` -> same sum as a 0/1 matrix product (fixed order);
  2. SDPA memory-efficient kernel (float32 on ROCm) varies by process -> `math` backend (patch of audio-separator `_sdpa_backends`);
  3. hipBLASLt picks the GEMM algorithm from free GPU workspace -> `ROCBLAS_USE_HIPBLASLT=0` (set before torch loads) + `preferred_blas_library("cublas")`.
  Evidence: worker (`run_job`) on a 40 s clip, 4 of 4 runs identical (mel vocals, karaoke lead, SW drums, DrumSep kick);
  full newton-vs-nye separate_hq twice (out/_wip/fixer-m3a-r4/det3 and det4): all 14 stems / sub-stems / drum_hits.json byte-identical.
  Micro-benchmark (same chunk, fresh process, 90 % of free GPU memory held): hipBLASLt 2 of 6 differ, `ROCBLAS_USE_HIPBLASLT=0` 6 of 6 identical.
  Settings recorded in `meta/separation.json.worker.settings.deterministic_roformer`.
- **48 kHz synthetic song cymbal F1** (round-2 test, thin margin): the new GEMMs moved the SW drums stem in the last bits, and DrumSep's
  ride / crash stems with it: cymbal F1 0.651. Added M3a-R4-3: a ride / crash hit at a kick / snare / tom stroke must decay like a cymbal
  (<= 9 dB) unless the classifier confirms it (drops snare leakage). Now passes (0.7+). Real songs lose 0-5 of 24-190 cymbals.

## Real-song regression (stages re-run on copies of the integrator folders, out/_wip/fixer-m3a-r4/real/<slug>)
| song | integrator cymbal / hat / tom / kick / snare | now |
|---|---|---|
| newton-vs-nye | 14 / 796 / 34 / 200 / 371 | 24 / 795 / 34 / 200 / 371 |
| versatile | 24 / 659 / 93 / 124 / 329 | 24 / 658 / 93 / 124 / 329 |
| megafauna | 151 / 1007 / 63 / 647 / 546 | 147 / 1005 / 63 / 647 / 546 |
| jeremy | 169 / 988 / 29 / 644 / 355 | 189 / 975 / 29 / 644 / 355 |
Kick / snare / tom unchanged; cymbals up from the round-3 floor (ride 8ths), crash-stem artefacts filtered. separate_hq took 490-620 s per
song (newton, shared GPU), the math attention backend is slower than the memory-efficient one.

## Gate (scripts\gate.ps1 M3a, last run out/_wip/fixer-m3a-r4/gate2.log)
unit: separate_fast / separate_hq / stem_activity / drums pass (3, 16, 11, 27 passed); `tests/unit/contract` 2 fail (not mine, below).
review: 14 passed, 1 failed (determinism, below). ruff PASS, validate PASS. contract `gen --check` FAIL (not mine).
