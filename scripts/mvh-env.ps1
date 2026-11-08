<#
.SYNOPSIS
  mv-harness shell environment. DOT-SOURCE it:   . scripts\mvh-env.ps1   [-Offline] [-Threads N]

.DESCRIPTION
  Puts Python 3.12, uv and ffmpeg on PATH by ABSOLUTE path (none of them is on the machine PATH),
  and sets the variables PLAN 3.3 / 3.4 require:
    MVH_FFMPEG, MVH_THREADS (default 3) + OMP/OPENBLAS/MKL/NUMBA thread vars,
    TORCH_HOME, HF_HOME, AUDIO_SEPARATOR_MODEL_DIR, NUMBA_CACHE_DIR, NLTK_DATA (all under %LOCALAPPDATA%\mvh),
    UV_NO_SYNC=1, UV_PYTHON, UV_CACHE_DIR, PYTHONUTF8=1, PYTHONPATH=<repo>\src.
  -Offline additionally sets HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 and MVH_OFFLINE=1.
  Without -Offline those three are REMOVED again (so a previous -Offline does not stick).

  Run python only as:  uv run --frozen --no-sync <cmd>      (never bare python / pip)
#>
param(
    [switch]$Offline,
    [int]$Threads = 0
)

# NOTE: no 'exit' and no $ErrorActionPreference change here: this file is dot-sourced into the caller's shell.
$mvhRepo = Split-Path -Parent $PSScriptRoot
$mvhHome = Join-Path $env:LOCALAPPDATA 'mvh'

$mvhPyDir      = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312'
$mvhPyExe      = Join-Path $mvhPyDir 'python.exe'
$mvhUvDir      = Join-Path $env:APPDATA 'Python\Python312\Scripts'
$mvhFfBin      = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin'
$mvhCfgPath    = Join-Path $mvhHome 'config.json'

# config.json (written by bootstrap.ps1) may override the ffmpeg location
if (Test-Path -LiteralPath $mvhCfgPath) {
    try {
        $mvhCfg = Get-Content -LiteralPath $mvhCfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($mvhCfg.ffmpeg -and (Test-Path -LiteralPath $mvhCfg.ffmpeg)) { $mvhFfBin = Split-Path -Parent $mvhCfg.ffmpeg }
    } catch { Write-Warning "mvh-env: could not read $mvhCfgPath : $_" }
}

foreach ($p in @($mvhPyExe, (Join-Path $mvhFfBin 'ffmpeg.exe'), (Join-Path $mvhFfBin 'ffprobe.exe'))) {
    if (-not (Test-Path -LiteralPath $p)) { Write-Warning "mvh-env: missing tool: $p" }
}
if (-not (Test-Path -LiteralPath (Join-Path $mvhUvDir 'uv.exe'))) {
    Write-Warning "mvh-env: uv.exe not found in $mvhUvDir (use: $mvhPyExe -m uv ...)"
}

# --- PATH (ours first; remove earlier copies so repeated dot-sourcing does not grow it) ---
$mvhOurs = @($mvhFfBin, $mvhPyDir, (Join-Path $mvhPyDir 'Scripts'), $mvhUvDir)
$mvhRest = ($env:PATH -split ';') | Where-Object { $_ -and ($mvhOurs -notcontains $_) }
$env:PATH = (($mvhOurs + $mvhRest) -join ';')

# --- directories ---
$mvhDirs = @{
    TORCH_HOME                = Join-Path $mvhHome 'torch'
    HF_HOME                   = Join-Path $mvhHome 'hf'
    AUDIO_SEPARATOR_MODEL_DIR = Join-Path $mvhHome 'models\separator'
    NUMBA_CACHE_DIR           = Join-Path $mvhHome 'numba'
    NLTK_DATA                 = Join-Path $mvhHome 'nltk'
    MVH_MODELS_DIR            = Join-Path $mvhHome 'models'
    UV_CACHE_DIR              = Join-Path $mvhHome 'uvcache'
    XDG_CACHE_HOME            = Join-Path $mvhHome 'models\xdg'
}
foreach ($k in $mvhDirs.Keys) {
    New-Item -ItemType Directory -Force -Path $mvhDirs[$k] | Out-Null
    Set-Item -Path "Env:$k" -Value $mvhDirs[$k]
}
New-Item -ItemType Directory -Force -Path (Join-Path $mvhHome 'locks') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $mvhHome 'bin') | Out-Null

# --- tools / paths ---
$env:MVH_HOME   = $mvhHome
$env:MVH_REPO   = $mvhRepo
$env:MVH_FFMPEG = Join-Path $mvhFfBin 'ffmpeg.exe'
$env:MVH_FFPROBE = Join-Path $mvhFfBin 'ffprobe.exe'
$env:MVH_RHUBARB = Join-Path $mvhHome 'bin\rhubarb\Rhubarb-Lip-Sync-1.14.0-Windows\rhubarb.exe'
$env:UV_PYTHON  = $mvhPyExe
$env:UV_NO_SYNC = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path $mvhRepo 'src'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$env:HF_HUB_DISABLE_PROGRESS_BARS = '1'
$env:TOKENIZERS_PARALLELISM = 'false'
Remove-Item Env:KMP_DUPLICATE_LIB_OK -ErrorAction SilentlyContinue   # never mask an OpenMP clash: the smoke test checks for it

# --- threads ---
if ($Threads -gt 0)                  { $env:MVH_THREADS = "$Threads" }
elseif (-not $env:MVH_THREADS)       { $env:MVH_THREADS = '3' }
foreach ($v in 'OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS') {
    Set-Item -Path "Env:$v" -Value $env:MVH_THREADS
}

# --- offline ---
if ($Offline) {
    $env:HF_HUB_OFFLINE = '1'; $env:TRANSFORMERS_OFFLINE = '1'; $env:MVH_OFFLINE = '1'
} else {
    foreach ($v in 'HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','MVH_OFFLINE') { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
}

Write-Host ("mvh-env: repo={0} threads={1} offline={2} ffmpeg={3}" -f $mvhRepo, $env:MVH_THREADS, [bool]$Offline, $env:MVH_FFMPEG)
