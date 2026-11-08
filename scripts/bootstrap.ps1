<#
.SYNOPSIS
  One-shot setup of the mv-harness MAIN environment (idempotent).
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 [-SkipModels] [-SkipPrewarm] [-VerifyOnly]
  Steps: 1) uv sync --frozen (main env, dev group, 'anthropic' extra)   2) write %LOCALAPPDATA%\mvh\config.json
         3) fetch + SHA-verify models (scripts\fetch_models.py, uses models.lock.json)   4) pre-warm the numba cache
  The sep worker envs (envs\sep, rocm/cpu locks) are synced by their own owner (env-sep): add them below when they exist.
  Only the orchestrator runs this; build agents never sync (UV_NO_SYNC=1).
#>
param([switch]$SkipModels, [switch]$SkipPrewarm, [switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot\mvh-env.ps1"
Set-Location $repo

# 1) sync main env.  src/mvh may not exist yet (contract architect writes it): then skip installing the project itself.
if (-not $VerifyOnly) {
    $syncArgs = @('sync', '--frozen', '--extra', 'anthropic')
    if (-not (Test-Path (Join-Path $repo 'src\mvh\__init__.py'))) { $syncArgs += '--no-install-project' }
    Write-Host "bootstrap: uv $($syncArgs -join ' ')"
    & uv @syncArgs
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed ($LASTEXITCODE)" }
}

# 2) config.json (consumed by io/ffmpeg.py: MVH_FFMPEG, then this file, then PATH)
$cfg = [ordered]@{
    ffmpeg   = $env:MVH_FFMPEG
    ffprobe  = $env:MVH_FFPROBE
    python   = $env:UV_PYTHON
    models   = $env:MVH_MODELS_DIR
    rhubarb  = (Join-Path $env:MVH_HOME 'bin\rhubarb\Rhubarb-Lip-Sync-1.14.0-Windows\rhubarb.exe')
    written  = (Get-Date).ToString('o')
}
# UTF-8 WITHOUT BOM (PowerShell 5.1 'Set-Content -Encoding UTF8' writes a BOM that breaks plain json.load)
[System.IO.File]::WriteAllText((Join-Path $env:MVH_HOME 'config.json'), ($cfg | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
Write-Host "bootstrap: wrote $env:MVH_HOME\config.json"

# 3) models
if (-not $SkipModels) {
    $fa = @('run', '--frozen', '--no-sync', 'python', 'scripts\fetch_models.py')
    if ($VerifyOnly) { $fa += '--verify' }
    & uv @fa
    if ($LASTEXITCODE -ne 0) { throw "fetch_models failed ($LASTEXITCODE)" }
}

# 4) numba cache pre-warm (librosa JIT; ~8 s first run)
if (-not $SkipPrewarm) {
    & uv run --frozen --no-sync python scripts\smoke\prewarm_numba.py
    if ($LASTEXITCODE -ne 0) { throw "prewarm failed ($LASTEXITCODE)" }
}
Write-Host 'bootstrap: done'
