#!/usr/bin/env bash
# Findings: the ggml Silero VAD step in this ffmpeg build costs ~1 s per second of audio (CPU, independent of use_gpu); without it turbo-q8 on Vulkan is >20x realtime.
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"; cd "$ROOT"
export MVH_FFMPEG="C:/Users/OpenSrcerer/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe"
P=envs/sep/.venv-cpu/Scripts/python.exe; W=envs/sep/tools/whisper_vulkan.py; L=tests/.cache/real/_logs/whisper.log
for slug in newton-vs-nye jeremy; do
  $P -X utf8 $W --slug $slug --model ggml-large-v3-turbo-q8_0.bin --no-vad >> $L 2>&1
  $P -X utf8 $W --slug $slug --model ggml-large-v3.bin --no-vad >> $L 2>&1
done
$P -X utf8 $W --slug newton-vs-nye --model ggml-large-v3-turbo-q8_0.bin --no-vad --no-gpu >> $L 2>&1
$P -X utf8 $W --slug jeremy --model ggml-large-v3-turbo-q8_0.bin >> $L 2>&1   # with VAD (slow)
echo ALLDONE >> $L
