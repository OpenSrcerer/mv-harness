#!/usr/bin/env bash
# usage: run_all.sh <variant> [overlap]   (run from the mv-harness root; sequential, resumable, logs to tests/.cache/real/_logs)
V=${1:-rocm}; OV=${2:-4}
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export MVH_FFMPEG="C:/Users/OpenSrcerer/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe"
mkdir -p tests/.cache/real/_logs
run() { slug="$1"; src="$2"
  mkdir -p "tests/.cache/real/$slug/sep"
  echo "== $slug $V $(date +%T)" >> "tests/.cache/real/_logs/sep-$V.log"
  envs/sep/.venv-$V/Scripts/python.exe -X utf8 envs/sep/tools/separate_song.py --variant $V --slug $slug --src "$src" --out "tests/.cache/real/$slug/sep" --overlap $OV >> "tests/.cache/real/_logs/sep-$V-$slug.log" 2>&1
  echo "== $slug done rc=$? $(date +%T)" >> "tests/.cache/real/_logs/sep-$V.log"
}
run newton-vs-nye "songs/Sir Isaac Newton vs Bill Nye.flac"
run jeremy "songs/Jeremy (Redux Version).flac"
run megafauna "../viz/MEGAFAUNA.flac"
run versatile "../viz/Versatile.flac"
