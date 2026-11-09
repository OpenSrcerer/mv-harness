# r-ml-m3b-r4 progress (R-ML review round 4 of M3b, W3)
## Done
- started 
## Next
- verify S04 fix (vocal presence uses lyric coverage); look for regressions; real-song reruns

- 07:55 integrator outputs have NOT re-run vocals since the S04 fix (vocal_range present false, 05:10). Copied integrator megafauna/versatile/jeremy
  to out/_wip/r-ml-m3b-r4/<slug>; --only vocals refused (rhythm, lyrics stale). Background: run_all.ps1 (--only spectral..lyrics,vocals) logs <slug>.up.log, status run_all.status
- code read: vocals now deps lyrics; gate = active & loud & (voice | lyric mask); lyric_present when >=4 s pitched inside >=20 s of lines; ignores line conf/grade; lyric_min_* not in STAGE.params
- 08:10 NEW major F1 confirmed: tests/review/M3b/r-ml/test_vocals_lyric_gate_hallucination.py FAILS (synth sawtooth inside interpolated conf-0 lines -> present, voiced 24.96 s, p2 57 p98 69, 52 notes). 146 s.
- ideas to check on real runs: lyr_sung flips dominant style on rap (newton); style labels come from CED on lead_vocals while pitch tracks vocals stem (megafauna); fraction of lyric-gated frames inside words
- 08:30 megafauna rerun done (out/_wip/r-ml-m3b-r4/megafauna): present true, 6.96 s, E3-E4 alto, 10 phrases, 33 notes, style speech (instrument CED), basis sung frames. 6.83/6.89 s in-line voiced frames lie inside word spans. 5.29 s have no tagger voice. S04 fix is real (not test hack). probe: out/_wip/r-ml-m3b-r4/probe.py
- 08:45 megafauna notes/instruments identical to integrator (counts + notes.mid byte-identical). Wrote test_vocals_lyric_frames_flip_rap.py (not yet run). running: versatile/jeremy (run_all), newton (separate), unit tests (bg)
- 09:15 newton rerun: identical to integrator (72.12 s, rap, 259 notes; tagger voice 1.0 in every line -> no lyric-only frames). versatile: present false, voiced 5.59 s, 27 notes, 10 phrases (no lines). unit: 53 pass, 1 fail = test_catalog_dag::test_deps_match_plan (vocals gained lyrics; CR known)
- rap-flip test running in bg (b2y3cvf26); jeremy running in run_all
- 09:30 NEW major F2 confirmed synthetically: test_vocals_lyric_frames_flip_rap.py FAILS (style=singing basis=voiced frames; tagger said rap 10 s, 16 s untagged lyric frames counted as singing). Not triggered on newton (tagger voice 1.0 in all lines). old review tests rerun in bg -> old.log
- 09:45 old review tests (clap x2, piano) 3 passed; ruff fixed on my flip test. waiting jeremy lyrics->vocals
- 08:35 jeremy rerun: 196.26 s, E3-C#5 tenor, 589 notes, 41 phrases (integrator 194.01/588/42) -> no regression. NOTE: a refused --only vocals run (upstream stale again) dropped vocal.* curves from my megafauna copy's curves/index.json (runtime behaviour). Determinism re-run not possible (upstream stale); r2 verified.
- next: write docs/review/M3b-r-ml.md Round 4, report, StructuredOutput
- DONE: review doc Round 4 + report written
