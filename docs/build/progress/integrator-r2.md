# integrator-r2 (W3 steps 4-6) progress

## Status
- 2026-11-09: started fresh (no prior progress file). Phase-1 work: docs/build/progress/integrator.md, reports/integrator.md.
- UD1 (meaning intent grammar) and UD2 (kick source) are W4 phase-0 work: do not start them, avoid conflicting changes.

## Plan
1. gate blockers: tests/unit/contract deps (vocals<-lyrics), CONTRACT gen, ruff
2. small/cross-module fixes from phase-2 open items + critic
3. tests/integration/test_override_roundtrip.py (R19)
4. max re-runs x5 + validate
5. gate all + determinism
6. docs/RUNS.md, SEAMS, CONTRACT, report

## Done

## Commands that worked

## Gotchas
- [x] PLAN_DEPS vocals += lyrics (tests/unit/contract/test_catalog_dag.py) -> D67 (to write)
- [x] structure 1.2.0: W3C-6 boundary edits applied locally after all auto steps (no DP re-run); overrides_applied one entry per key (list);
      F8-r5 phrase_layout local (lead=snapped sections, or evidence[a+r] beats evidence[a] and [b-r] by margin); param phrase_pickup_margin.
      unit structure/choreo pass, review M2 pass (24/6 skip), W3 critic locality pass. tests/unit/structure/test_phrase_grid.py rewritten to local rule.
- baseline review run: out/_wip/integrator-r2/review-base.log (started before edits)
- [x] viewer data.js appliedOverrides collects repeated keys; edit.js pendingBoundaries normalises (M6a F-R5-APPLIED-BOUNDARY)
- [x] voices: n_voices_min floor from viewer block (block stripped before regex count); hints from ALL items (R5-2 crash). unit voices, M5 r5 short-hint, M6a r4 platform pass. integration seam test now asserts n_voices_min.
Gotcha: bash heredoc python writes "\n" as a real newline -> use Edit for backslashes.
- [x] drums 1.1.0: coincidence-decay rule only at snare/tom strokes (M3a R5-1)
- [x] vocals 1.1.0: lyric lines are voice evidence only with grade A-C or G1 >= lyric_min_match 0.3 (R5-1); untagged lyric frames inherit only 'rap' else sung (R5-2)
- [x] instruments 1.1.0: vocal style tagged on pick_lead_stem (r4-m4)
- [x] harmony 1.1.0: chroma peak/mean gate (CHROMA_PEAK_MIN 2.2), S-KEY confirm p>=0.35, carve-out cap 0.8, neighbour/abstaining S-KEY on peaked unanimous chroma -> cap 0.5 + chroma_only/low_confidence (R5-M1/M2). tests pending
- [x] lyrics 1.1.0: _cap_line_tails (W3C-5); lib singer_at/singerAt dedupe (character, voice). node lib 30/30
- [x] tests/unit/vocals/test_lyric_presence.py updated (grade B fixtures) + new acoustic-support test
- [x] choreo 1.1.0: LHL syncopation (W3C-2; truth.py formula re-baselined -> FIXTURE REBUILD NEEDED), tolerant-F1 groove clustering vs majority pattern (W3C-1; thr 0.8, hat w 0.25, hat min vel 0.3; probe out/_wip/integrator-r2/probes/groove_probe2.py: synth agree .982, jeremy .26, newton .26, megafauna .54, versatile .50 -> W4)
- [x] structure: edm_role for every section in a role span (m6); brief 1.0.1 key:key fix (m1); SKILL frames name (m7); voices 1.1.0 single-voice grade-D no review (m2)
- [x] tests/integration/test_override_roundtrip.py written (R19; real+slow; copies integrator folders to out/_wip/integrator-r2/roundtrip). NOT RUN YET (needs fresh max folders)
- [x] tests/integration/M5/test_real_lyrics_grade.py outro test -> flag-for-review assertion (verifier r4-m3 agreed)
- [x] lyrics text: lone 'Name:' markers must pass _strict_name (+ no multiword in Title Case) even when recurring (M5 R5-1); M5 unit+review pass
- [x] harmony unit 75 pass, review M4 15 pass; M3a review 16 pass/1 skip; M3b review 7 pass; choreo near-credit param (groove_near_credit .5, thr .75): synth .988
- [x] sepworker: ROCBLAS_USE_HIPBLASLT=0 for rocm variant
- [x] fixtures rebuilt (python -m tests.synth.build) after truth syncopation change
- [~] 05:xx? launched 5 fresh max runs: out/_wip/integrator-r2/launch_max.ps1 (detached; RESUME = relaunch same script; phase-1 folders moved to out/_wip/integrator/_phase1/<slug>; logs out/_wip/integrator-r2/runs/<slug>.log/.done.json)
NEXT: CONTRACT D67-D78 + gen; wait runs; run tests/integration (incl. roundtrip), W3 critic tests; gate all; determinism; RUNS.md; SEAMS; report
- [x] CONTRACT D67-D77 appended, gen + --check OK, skill copy synced; unit contract 90 pass
- [x] M6a r5 test precondition accepts both stamps (one per key list / one per edit) + new repeated-key file-mode test; 3 pass
- review M6b r-words: 23 fail = R5-1..R5-4 (UD1, W4); M6b r-contract 26 pass
- docs/RUNS.md drafted (placeholders RUN_TABLES_PLACEHOLDER, WEAK_PLACEHOLDER); out/_wip/integrator-r2/timings.py
- [x] 13:24 synth (2737 s) and newton (2715 s) max: analyze 0 validate 0; launched R19 roundtrip test (out/_wip/integrator-r2/roundtrip.log)
- critic on newton/synth: handoffs 3/4 pass (mouth overlap 6.7->2.3 s; 2.1 s is a detected BACKING span V1 on L021 48.5 s, not a handoff), grooves/syncopation newton pass, locality pass, feel fails (W4)
- [x] megafauna 2815 s, versatile 2826 s: analyze 0 validate 0. S04 (M3b presence) + S07 (versatile mouth) PASS now; S06 fails (UD2); grooves megafauna 0.71 / versatile 0.45 (W4); newton lyrics B->C (G2 0.748 vs 0.75, separation bits changed; borderline)
- [x] jeremy 2949 s analyze 0 validate 0. integration: S03 S04 S05 S07 S09 pass; S06 fail (UD2). critic: 28 pass, 5 fail (feel W3C-3, grooves mega/vers, mouth overlap backing 2.1 s, jeremy hats W3C-4)
- [x] R19 roundtrip: 2 passed (synth step1+downbeat, newton) in 481 s; no-op re-run 25/25 hits x5
- [x] SEAMS.md updated (S03-S09 statuses, S13-S20, round-2 section)
- [x] jeremy draft alone 1070 s analyze 0 validate 0 (out/_wip/integrator/jeremy-draft); unit-all: all pass except harmony pytest-timeout waiting for heavy slot during 5 runs (env contention)
- [~] gate all launched detached (14:0x): writes out/_wip/integrator/gate-all.log/.done.json (first launch); run_gate.ps1 now fixed to integrator-r2 paths (relaunch run_gate.ps1 after outage)
- [x] docs/RUNS.md filled
- [x] report drafted (GATE_PLACEHOLDER to fill). NEXT: wait gate (out/_wip/integrator/gate-all.done.json), fill report sec 5, BUILD-STATUS line, StructuredOutput
- [x] gate all: rc 1; unit PASS 992/0 fail; review 39 fail (M1 r5 kicks 11 UD2, M6b r-words 23 UD1, critic 5 W4) / 262 pass; ruff, contract, validate, e2e, lib-node, determinism PASS. Report sec 5 filled.
