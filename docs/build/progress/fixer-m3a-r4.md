fixer-m3a-r4: R4-1 crash floor DONE (input-event check in drumsep_hits, drums_mix param; review tests pass). NEXT: R4-2 HQ vocals GPU determinism (hq_worker), decisions doc, regression runs, gate
R4-2: found 2 causes: Mel scatter_add atomics (patched via fixed-order matmul) + SDPA mem-efficient autotune (force MATH); both in src/mvh/sep/determinism.py deterministic_roformer, wired in hq_worker; 8 clip runs: 7/8 identical, 1 hog-0.9 run differs. NEXT: unit tests for determinism+crash-floor, decisions doc, real runs vs integrator, gate
decisions doc written, unit tests added; running real regression out/_wip/fixer-m3a-r4/run_real.sh (log run_real.log); then synth + gate + report
newton real rerun ok (cymbals 14->24, rest same); versatile/megafauna/jeremy running; then determinism rerun of newton, synth, gate, report
R4-2 final: ROCBLAS_USE_HIPBLASLT=0 + rocBLAS pref + math SDPA + fixed scatter -> worker 4/4 identical on clip; running det3/det4 full newton reruns, then gate + report
det3==det4 bit-identical (newton full). gate running -> out/_wip/fixer-m3a-r4/gate.log; then report
added coinc_decay rule (48k synth test fix), unit test; running drums-only reruns on 4 real copies then gate again
report written; final
