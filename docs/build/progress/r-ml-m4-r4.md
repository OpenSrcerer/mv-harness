# r-ml-m4-r4 progress

## Done
- started; read r3 progress

## Next
- verify R3-M1 fix (keys.py/core.py), run review tests, real songs, new findings
- fast M4 suite 61 pass; real review tests 5 pass (R3-M1 band-noise test passes)
- fix is real: keys.global_confidence caps conf 0.3 + no_tonal_evidence when lv N share >= 0.9 (not test-specific)
- jeremy harmony rerun via mvh analyze (out/_wip/r-ml-m4-r4/jeremy): key unchanged vs integrator
- probe out/_wip/r-ml-m4-r4/probe.log: REGRESSION candidate: synth_stem_vocals (a cappella A minor) now conf 0.3 + no_tonal_evidence
  while skey(.566)+ks+temperley+albrecht all say A minor (r3: 0.913). Noise/riser/brown/band all capped OK.
- running probe_real.py (real vocal stems + mixes) -> probe_real.log
- NEW major R4-M1 (regression from R3-M1 fix): a cappella synth lead_vocals capped 0.3 + no_tonal_evidence.
  test tests/review/M4/r-ml/test_key_gating_a_cappella.py FAILS (stub); with NO_TONAL_SHARE=1.01 conf .97 (prefix_check.py)
  chroma peakiness separates: noise median norm entropy >=0.9, vocals 0.71 (peaky.py)
- real probe (probe_real.log): mixes unchanged vs integrator (newton .888, megafauna .5 3 regions, versatile .5); real lead-vocal
  stems: S-KEY mostly does not vote (p .17-.34), profiles split -> gate cost on real stems small (jeremy A minor region .831 -> .3)
- harmony deterministic across processes (jeremy rerun == integrator byte-identical)
- harmony stage_version not bumped (1.0.1) after behaviour change -> stale caches (minor)
- next: gate M4 in background (out/_wip/r-ml-m4-r4/gate.log), write review doc Round 4 + report
- real-model variant of a cappella test also FAILS (0.3 + no_tonal_evidence); ruff clean
- mood re-run jeremy/newton reproduces integrator (5e-5); minors m14-m18 + m9 written to docs/review/M4-r-ml.md Round 4
- next: wait gate log, write report docs/build/reports/r-ml-m4-r4.md, return
- report written; finished (gate fails on shared contract tests, not M4)
