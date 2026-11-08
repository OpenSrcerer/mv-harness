# bench-music progress
Started 2026-11-08. Resume from the last checked item. Raw outputs: tests/.cache/real/<slug>/<tool>/ ; each step writes _done.json (timings + load) or _error.json.
- [x] 1 write driver docs/research/spike-scripts/bench-music/bench_music.py (resumable per step)
- [ ] 2 run megafauna / versatile / jeremy / newton-vs-nye under heavy lock (log tests/.cache/real/_logs/bench-music.log)
- [ ] 3 analysis script (cross-tool agreement) + docs/spike/bench-music.md
- [ ] 4 index.music.json + report docs/build/reports/bench-music.md
## Commands
Run one song: powershell -NoProfile -File scripts\run.ps1 python scripts\heavy_lock.py run --owner bench-music --threads 6 -- <python> docs\research\spike-scripts\bench-music\bench_music.py <slug>
## status 13:25
- driver docs/research/spike-scripts/bench-music/bench_music.py + run_all.sh <slug...> + analyze.py written. Launch: nohup docs/research/spike-scripts/bench-music/run_all.sh megafauna &  (log tests/.cache/real/_logs/bench-music.log). Resumable: finished steps skipped; --force <step> via bench_music.py args.
- Gotchas: heavy_lock run needs absolute forward-slash python path (.venv/Scripts/python.exe); beat_this Postprocessor needs torch tensors.
- megafauna: decode+demucs done (demucs 112 s for 217 s audio, both models), beat_this failed (fixed in code, rerun with --force beat_this), allin1 running.
- megafauna all steps done (fixed: CED output is already probability; RMVPE gate conf>=0.3; piano presence rule). Next: versatile newton-vs-nye jeremy via run_all.sh
- all 4 songs finished 13:44 (log _logs/bench-music.log). piano skipped everywhere (no piano). Next: analyze.py -> docs/spike/bench-music.md + report
- DONE 13:55: docs/spike/bench-music.md, report, index.music.json written.
