# r-ml-m3b-r2 progress (R-ML review round 2 of M3b)
## Done
- started; read round-1 progress (r-ml-m3b.md) and review tests
## Next
- verify fixes for R-ML-M3b-1 (CLAP padding) and R-ML-M3b-2 (piano floor); look for regressions
- fix 1 (clap.py text: batch of 1, no padding) is real; fix 2 (notes floor piano_min_active_s=1.0 s; warning; basic-pitch fallback) real
- tests/review/M3b/r-ml: 3 passed (401 s). ruff M3b clean. tests/unit/{instruments,notes}: 24 passed.
- stem_activity present needs >= 2 s active AND conf >= 0.4, so 1 s floor is redundant but harmless
- copied round-1 synth folder -> out/_wip/r-ml-m3b-r2/synth; reran instruments (synth_rerun.log); rerun spectral,rhythm,notes,vocals (synth_rerun2.log/.err)
- synth rerun (r2): notes degraded piano:basic_pitch (CED piano mean .024 on synthetic piano voice) -> 25 piano notes, 18 correct (P .72); bass F1 .858; vocals G3-A4 present
  piano stem from separate_hq is ~-115 dB 17-37 s (upstream), active only 37.9-42.4 s -> low recall is upstream
- real songs (builder-m3a stem_activity): piano present=false on all 4 -> no regression from the 1 s floor on real songs
- synth_* sub-type one-hot frac .849 after fix (was .774): minor m1 persists
- determinism rerun started (hash1.txt; synth_rerun3.err)
- determinism: all 17 M3b outputs byte-identical on rerun
- versatile instruments (copy of builder-m3a/versatile): sub-type argmax pad7/lead28/arp56/bass67 (was 148/158 bass); one-hot .778
- WROTE docs/review/M3b-r-ml.md Round 2 (r2-m1, r2-m2), docs/build/reports/r-ml-m3b-r2.md. DONE -> StructuredOutput
