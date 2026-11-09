# r-platform-w4 progress (W4 final R-PLATFORM review)

## Milestones
- [16:25] started. No earlier progress. Determinism: two fresh max runs of Newton launched in the background
  (out/_wip/r-platform-w4/run_det.ps1 -Name det-a / det-b; logs out/_wip/r-platform-w4/det-?.log, done marker det-?.done.json).
  Resumable: relaunch the same command (stage cache).

- [16:45] launched (background, resumable): run_uni.ps1 (synth max from Unicode in/out paths, folder
  "out/_wip/r-platform-w4/uni üñ ♪ 曲-max", logs uni-max.*), run_sepcpu.ps1 (MVH_SEP_VARIANTS=cpu, synth, --only ingest,separate_hq
  -> sepcpu/). Checked: doctor --quick OK (ROCm line missing in --quick: W1b m6 still), models.lock 28 entries all sha256+size,
  5 sep/demucs licences unclear (m5), vendored wheels not hash-pinned (uv path sources; SHA only in spike doc), slug collision fixed.
  Code notes: viewer idle-timeout kills a running re-run (job object), no per-song lock (W1b m8), prune() keeps only newest key
  (RUNS §3 says old entries kept), device_class first-available (W1b m3), threads clamp (m4), ingest key has file name (m5).

- [17:00] FINDING W4P-1 (RUNTIME major) test written + failing (2/2): tests/review/W4/platform/test_w4p_input_relocation.py
  (moved input -> folder re-run fails ingest, all pending; renamed input -> loudness re-runs = full cascade).
  Server probe (out/_wip/r-platform-w4/probes/probe_server.py): Host/Origin/token/traversal/ADS/413/NaN/1e999 all OK;
  8.3 short name /CACHE~1/ingest/latest.json -> 200 (dot filter bypass, minor). Viewer lanes on ud2 newton copy (tab-3, port
  47321; DO NOT use tab-2 = r-dogfood's): 11 lanes, 0 lane errors at 5 windows, edit pane OK. uv lock --check OK.
  intent block CRLF OK. No abs paths in public outputs.

- [17:20] Unicode run PASS: synth max from "in dïr ♪/曲 tëst ♪.flac" into "uni üñ ♪ 曲-max": analyze 0, validate 0 (119 files),
  lipsync visemes (Rhubarb) OK, scratch empty, 2208 s wall (contention). Earlier review tests w1b + M6a: 39 pass, 1 skip.
  Seam re-check on ud2 folders: S17 grooves megafauna 48/62, versatile 32/80 (still); S18 newton feel normal (still);
  S19 jeremy hats 0.37 on grid (still); Newton lyrics grade C (G2 0.7479); m5 licences unclear (5 entries).

- [17:35] det-a done (analyze 0 validate 0, 124 files, 2666 s). sepcpu done: run.json variant cpu, stems vs ROCm -84..-106 dB
  (karaoke lead/backing -47/-43, guitar -61). Cache: copy of det-a in another folder = 25/25 hits; --param cues.top_moments
  re-ran exactly cues+descendants, kept on next run; harmony.key_override test running (ct-harm.log, background).
  R19 loop: r19/ copy served on port 47322 (tab-3), edits via UI: boundary add 48 s, pin 100 s, V2->C2 "Narrator ☃";
  re-run started from the viewer. Minor: edit bar 'will re-run' shows only the LAST save's affected stages.

- [18:05] DETERMINISM PASS: det-a vs det-b (two folders, contended, ROCm): 188 files identical (only my .seeded marker differs).
  harmony.key_override re-ran exactly its 12 descendants; old cache keys pruned (RUNS §3 says kept: doc minor).
  R19 PASS end to end in browser: re-run from viewer exit 0, only structure..viewer re-ran, after reload boundary S05 48.78,
  pin tier-1 at 100 s, C2 "Narrator ☃", 0 lane errors, validate 126/0. Fresh Newton: S16 mouths 2.3 s (still), S18 feel
  normal (still), lyrics grade C (G2 0.7479).
  FINDING W4P-2 (RUNTIME major): held curves/core.f32 -> analyze rc1 traceback + core.f32.tmp litter (curvefile fixed tmp
  name, bare os.replace); 2-3 concurrent runs on one folder fail (no song lock). Test test_w4p_finalize_held_and_concurrent.py
  (2 failing).

- [18:20] doctor full OK; ruff clean; servers stopped, tab-3 closed. Review doc + report written. DONE (only StructuredOutput left).

## Next
- nothing (if resumed: return the structured summary from docs/build/reports/r-platform-w4.md).
- read PLAN §11, prior platform reviews, integrator-r2; check paths/unicode, subprocess/ffmpeg, env/lock, sep CPU variant,
  cache invalidation, disk, supply chain, doctor, viewer.

## Commands that worked
- powershell.exe -NoProfile -ExecutionPolicy Bypass -File out/_wip/r-platform-w4/run_det.ps1 -Name det-a

## Gotchas
