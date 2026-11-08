#!/bin/bash
# usage: run_all.sh "slug[:force1,force2]" ...   (each song holds one heavy slot for its own run; resumable)
cd /c/Users/OpenSrcerer/Desktop/playground/mv-harness
for spec in "$@"; do
  s="${spec%%:*}"; f=""; [[ "$spec" == *:* ]] && f="${spec#*:}"
  MVH_RUN_OFFLINE=1 powershell.exe -NoProfile -File scripts/run.ps1 python scripts/heavy_lock.py run --owner "bench-music:$s" --threads 6 -- C:/Users/OpenSrcerer/Desktop/playground/mv-harness/.venv/Scripts/python.exe -X utf8 docs/research/spike-scripts/bench-music/bench_music.py "$s" --force="$f" >> tests/.cache/real/_logs/bench-music.log 2>&1
done
echo ALLDONE >> tests/.cache/real/_logs/bench-music.log
