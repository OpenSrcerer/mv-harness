<# Builds the 5 s smoke clips (and TTS) under %LOCALAPPDATA%\mvh\smoke.  Usage: powershell -NoProfile -File scripts\smoke\make_clips.ps1 #>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\mvh-env.ps1"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $env:MVH_HOME 'smoke'; New-Item -ItemType Directory -Force $out | Out-Null
$ff = $env:MVH_FFMPEG
function Clip($src, $ss, $dur, $name) {
    & $ff -y -v error -ss $ss -t $dur -i $src -map 0:a:0 -vn -c:a pcm_f32le (Join-Path $out $name)
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed for $name" }
}
Clip (Join-Path $repo 'songs\Jeremy (Redux Version).flac') 100 5 'jeremy_5s.wav'
Clip (Join-Path $repo '..\viz\MEGAFAUNA.flac') 60 5 'megafauna_5s.wav'
Clip (Join-Path $repo '..\viz\Versatile.flac') 120 5 'versatile_5s.wav'
Clip (Join-Path $repo 'songs\Sir Isaac Newton vs Bill Nye.flac') 30 25 'nye_25s.wav'
# TTS (SAPI): known text, two voices, for alignment / ASR / speaker smoke tests
Add-Type -AssemblyName System.Speech
$txt1 = 'The quick brown fox jumps over the lazy dog'
$txt2 = 'She sells sea shells by the sea shore'
foreach ($v in @(@('Microsoft David Desktop','tts_david.wav',$txt1), @('Microsoft Zira Desktop','tts_zira.wav',$txt2), @('Microsoft David Desktop','tts_david2.wav',$txt2))) {
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice($v[0]); $s.SetOutputToWaveFile((Join-Path $out ($v[1] -replace '\.wav$','_raw.wav'))); $s.Speak($v[2]); $s.Dispose()
    & $ff -y -v error -i (Join-Path $out ($v[1] -replace '\.wav$','_raw.wav')) -ar 44100 -ac 1 -c:a pcm_f32le (Join-Path $out $v[1])
}
Set-Content -LiteralPath (Join-Path $out 'tts_david.txt') -Value $txt1 -Encoding UTF8
Set-Content -LiteralPath (Join-Path $out 'tts_zira.txt') -Value $txt2 -Encoding UTF8
Get-ChildItem $out | Select-Object Name, Length | Format-Table -AutoSize
