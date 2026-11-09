# fixer-m5-r4 progress (W3 module fix round 2, M5 Words)
- started: read fixer-m5-r3 report + r-words-m5-r4 verify. Open: R4-1 (major, colon lyric lines deleted as markers), minors r4-m1..m5;
  S03 part-2 integration test judged wrong by reviewer (r4-m3); integration tests read integrator folders (pre-fix) -> fail until integrator reruns M5.
- plan: lone 'Name:' markers decided per file (recurrence with different following text, or strict names in a non-title-case file); r4-m1 long-tail headers; r4-m2 joint hints.
- DONE text.py: _scan_labels (lone markers per file, M5-D54), header long tail, lone (x2); voices hint_parts (M5-D55). Unit test tests/unit/lyrics/test_r4_fixes.py; test_r3_fixes updated (lone marker is a candidate). Text tests 52 pass. Decisions D54/D55 written.
- NEXT: voices unit tests, real reruns via out/_wip/fixer-m5-r4/m5drive.py, gate.
- real reruns launched: sh out/_wip/fixer-m5-r4/scripts/drive.sh newton-vs-nye jeremy megafauna versatile synth (log out/_wip/fixer-m5-r4/drive.log; <slug>.DONE markers; rerun to resume)
- voices unit test tests/unit/voices/test_joint_hints.py (pass). ruff clean.
- r4-m4 partial-version control test added to test_r4_fixes.py (15 pass).
- M5-D56 hold cap at next lead line (core.py, r3-m1). Restarted drive (killed first one: it was still waiting for a heavy slot). pytest-all running bg -> out/_wip/fixer-m5-r4/pytest-all.log
- gate bg running (log docs/build/progress/fixer-m5-r4.gate.log): contract unit fails again = vocals deps (+lyrics, M3b) + CONTRACT.md regen; non-M5. compare script out/_wip/fixer-m5-r4/scripts/compare.py (integrator / r3 / r4).
- BUG fixed: D56 cap used variable name 'lead' (shadowed lead audio) -> renamed lead_lines. Killed gate run 1 + drive; restarting drive then gate.
- D56 hold cap REVERTED (newton voices 4->3). Rerunning newton.
- rerun (reverted): newton, jeremy done; megafauna/versatile/synth running.
- all 5 reruns done (reverted code). gate run 2 started bg (log docs/build/progress/fixer-m5-r4.gate.log).
- compare: all 5 songs identical to fixer-m5-r3 (grades jeremy B, newton B 4 voices, megafauna D, versatile instr mouth 0, synth B). leak scan clean (3 songs). Waiting for gate run 2, then report.
- gate run 2 so far: unit M5 dirs 0, review PASS, validate PASS; FAIL contract unit (vocals deps), contract gen --check, ruff src/mvh/sep/determinism.py (foreign). e2e/determinism pending. Report drafted.
- DONE. gate run 2 exit 1 (foreign only: contract unit vocals deps, contract gen --check, ruff sep/determinism.py); e2e/determinism PASS. Report final docs/build/reports/fixer-m5-r4.md
