<#
.SYNOPSIS
  One-command setup of mv-harness on this machine (safe to re-run; finished steps are skipped or verified).
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 [-NoRocm] [-SkipModels]
  Steps:
    1. check Python 3.12 and ffmpeg; install uv with pip if it is missing
    2. main Python environment, config.json and ALL pinned models (scripts\bootstrap.ps1; models.lock.json, SHA-256 verified)
    3. stem-separation environments: CPU always, ROCm (AMD GPU) unless -NoRocm; a ROCm failure is a warning, not an error
    4. mvh doctor
  Everything downloaded goes to %USERPROFILE%\.mvh (override with MVH_HOME): about 12 GB of models.
#>
param([switch]$NoRocm, [switch]$SkipModels)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
function Step($n, $t) { Write-Host ""; Write-Host "== setup $n/4: $t ==" -ForegroundColor Cyan }

Step 1 'tools'
$py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    throw "Python 3.12 not found at $py. Install it first:  winget install Python.Python.3.12"
}
. "$PSScriptRoot\mvh-env.ps1"
if (-not $env:MVH_FFMPEG -or -not (Test-Path -LiteralPath $env:MVH_FFMPEG)) {
    throw "ffmpeg not found. Install it first:  winget install Gyan.FFmpeg   (then open a new PowerShell window)"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'setup: installing uv with pip'
    & $py -m pip install --user --quiet uv
    if ($LASTEXITCODE -ne 0) { throw "pip install uv failed ($LASTEXITCODE)" }
    . "$PSScriptRoot\mvh-env.ps1"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv is still not on PATH after installing it' }
}
Write-Host "setup: python, ffmpeg and uv are present; data folder: $env:MVH_HOME"

Step 2 'main environment and models (the first run downloads about 12 GB)'
$boot = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'bootstrap.ps1'))
if ($SkipModels) { $boot += '-SkipModels' }
& powershell.exe @boot
if ($LASTEXITCODE -ne 0) { throw "bootstrap failed ($LASTEXITCODE)" }

Step 3 'stem-separation environments'
$variants = @('cpu'); if (-not $NoRocm) { $variants += 'rocm' }
foreach ($v in $variants) {
    Push-Location (Join-Path $repo "envs\sep\$v")
    try {
        $env:UV_PROJECT_ENVIRONMENT = "..\.venv-$v"
        Write-Host "setup: uv sync --frozen (sep $v)"
        & uv sync --frozen
        $rc = $LASTEXITCODE
    } finally {
        Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
        Pop-Location
    }
    if ($rc -ne 0) {
        if ($v -eq 'rocm') { Write-Warning "setup: the ROCm environment did not install ($rc); separation will use the CPU (slower). Re-run with -NoRocm to skip it." }
        else { throw "sep $v environment failed ($rc)" }
    }
}

Step 4 'doctor'
Set-Location $repo
& uv run --frozen --no-sync mvh doctor --quick
if ($LASTEXITCODE -ne 0) { Write-Warning 'setup: mvh doctor reported problems (see the lines that are not OK above)'; exit 1 }
Write-Host ''
Write-Host 'setup: done. Next:  . .\scripts\mvh-env.ps1 ;  uv run --frozen --no-sync mvh analyze "songs\My Song.flac"' -ForegroundColor Green
