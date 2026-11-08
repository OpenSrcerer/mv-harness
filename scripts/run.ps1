<#  Helper: scripts\run.ps1 <args to uv run...>  -> sources the env then 'uv run --frozen --no-sync <args>'.
    Example: powershell -NoProfile -File scripts\run.ps1 python scripts\smoke\imports.py   (add -Offline via $env:MVH_RUN_OFFLINE=1) #>
$repo = Split-Path -Parent $PSScriptRoot
if ($env:MVH_RUN_OFFLINE) { . "$PSScriptRoot\mvh-env.ps1" -Offline } else { . "$PSScriptRoot\mvh-env.ps1" }
Set-Location $repo
uv run --frozen --no-sync @args
exit $LASTEXITCODE
