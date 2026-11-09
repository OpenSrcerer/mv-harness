# r-platform-w4: W4 final R-PLATFORM review

Verdict: **pass-with-fixes**. Full review: `docs/review/W4-platform.md`. No lyric text appears here.

## Findings for the fixers (failing tests)
| ID | Owner | Sev | Claim | Test |
|---|---|---|---|---|
| W4P-1 | RUNTIME | major | A moved/renamed input breaks `mvh analyze <folder>` (ingest fails, all pending); a rename re-runs all 25 stages (ingest key hashes the file name) | tests/review/W4/platform/test_w4p_input_relocation.py (2 fail) |
| W4P-2 | RUNTIME | major | A held `curves/core.f32` crashes analyze in finalize (fixed `.tmp` name, bare os.replace, litter left); no per-song lock, so concurrent runs (viewer Re-run + terminal) fail | tests/review/W4/platform/test_w4p_finalize_held_and_concurrent.py (2 fail) |

Seam items still real (existing failing tests, other modules): S16 (M5) Newton mouths 2.3 s; S17 (M2) groove ids
MEGAFAUNA 48/62, Versatile 32/80; S18 (M2) Newton feel normal; S19 (M3a) Jeremy hats 0.37 on grid. S06 is resolved by
UD2. Minors: Newton lyrics grade C (G2 0.7479), 5 licences unclear, plus 11 platform minors in the review file.

## Verified OK
- Determinism: two fresh Newton max runs in two folders, under contention: 188/188 files identical.
- Unicode/spaces input and output paths, full max synthetic run (Rhubarb, sep worker, whisper): analyze 0 / validate 0.
- Sep CPU variant forced once (`MVH_SEP_VARIANTS=cpu`): works, recorded as `cpu`, stems within -84..-106 dB of ROCm
  (karaoke split -43/-47 dB).
- Cache invalidation: cues and harmony param edits re-ran exactly their descendants; a folder copy is all hits.
- R19 loop end to end in the browser (boundary, pin, voice mapping, Re-run from the viewer, reload): correct, 0 lane errors.
- Server security probes all pass except the 8.3 short-name bypass (minor). doctor full OK; uv lock in sync; models.lock
  81 files sha256-pinned.

## Files
- Tests: tests/review/W4/platform/test_w4p_input_relocation.py, test_w4p_finalize_held_and_concurrent.py (ruff clean).
- Review: docs/review/W4-platform.md. Progress: docs/build/progress/r-platform-w4.md.
- Evidence/probes: out/_wip/r-platform-w4/ (run_det.ps1, run_uni.ps1, run_sepcpu.ps1, probes/detdiff.py, cmp_sep.py,
  probe_server.py, critic_on.py, hold_curve.py; run folders det-a, det-b, cachetest, r19, sepcpu, uni*-max).
