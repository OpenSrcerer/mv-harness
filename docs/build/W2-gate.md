# Orchestrator gate after W2 (`scripts\gate.ps1 all`, 2026-11-09 03:44)

Log: out/_wip/orchestrator/gate-all-W2.log (UTF-8 with BOM).

| Step | Result | Note |
|---|---|---|
| fixture, ruff, contract, validate, lib-node | PASS | |
| e2e | PASS | full mvh analyze of the synthetic song in 149 s |
| unit | **FAIL (nothing ran)** | collection error: tests/unit/rhythm/test_real_songs.py and tests/unit/lyrics/test_real_songs.py have the same basename and no package `__init__.py` ("import file mismatch"), so pytest aborted the whole unit run. **No unit test ran.** |
| review | FAIL, 55 failed / 144 passed / 21 skipped | exactly the open W2 findings (M1 kicks, M2 structure jitter, M3a ride, M4 band noise, M5 labels/hallucination/headers, M6a undo, M6b intent parsing) |
| determinism | **FAIL** | 11 of 180 files differ between two `analyze --force` runs: stems/drums/{kick,snare,toms,hihat,ride,crash}.flac → events/drum_hits.json, curves/core.f32, curves/stems.f32, manifest.json, viewer.html. The DrumSep sub-stems (GPU / ROCm) are not bit-reproducible and the differences cascade downstream. |

For the W3 integrator: fix the unit collection error first, then re-run the unit tests; that run is the first real unit-test result since W2.
Then decide and implement the determinism policy for GPU-separated stems: deterministic kernels or seeds, a CPU path, or a documented
tolerance diff for float audio plus exact diffs everywhere else. Record that as a contract decision.
