<#
.SYNOPSIS
  mv-harness gate (PLAN §12 "Gates"):  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gate.ps1 <W1b|M1..M6b|stage|all>

.DESCRIPTION
  Steps (each PASS / FAIL / SKIP, summary table at the end, exit 1 on any FAIL):
    1. fixture     regenerate tests/contract/synth/ when its .done.json is missing, using the generator command named in
                   docs/build/reports/fixtures.md ("python -m tests.synth.build ..."), only if that report names one
    2. unit        pytest on the target's unit tests (tests/unit/<stage> for its stages; W1b: runner io cli ingest worker
                   contract fixtures lib; all: tests/unit)
    3. review      pytest on every tests/review/** folder for the target
    4. ruff        ruff check src tests
    5. contract    python -m mvh.contract.gen --check
    6. validate    mvh validate tests/contract/synth
    7. e2e         mvh analyze of the walking skeleton (fixture song) into a temp folder, then mvh validate on it
    8. lib-node    node --test tests/unit/lib (when present)
    9. determinism mvh analyze --force again and diff every file except run.json and .cache/
  Options: -SkipE2E (steps 7 and 9), -KeepTemp (keep the temp song folder), -Threads N (default 3).
  Heavy slots stay ON: once modules replace the stubs the e2e run is real inference.
#>
param(
    [Parameter(Position = 0)][string]$Target = 'W1b',
    [switch]$SkipE2E,
    [switch]$KeepTemp,
    [int]$Threads = 3
)

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'mvh-env.ps1') -Offline -Threads $Threads
Set-Location -LiteralPath $repo

$modules = [ordered]@{
    'W1b' = @('ingest')
    'M1'  = @('spectral', 'loudness', 'dynamics')
    'M2'  = @('allin1', 'rhythm', 'structure', 'choreo', 'cues')
    'M3a' = @('separate_fast', 'separate_hq', 'stem_activity', 'drums')
    'M3b' = @('notes', 'vocals', 'instruments')
    'M4'  = @('harmony', 'mood')
    'M5'  = @('identity', 'lyrics', 'voices', 'lipsync')
    'M6a' = @('viewer')
    'M6b' = @('meaning', 'brief', 'frames')
}

$results = New-Object System.Collections.ArrayList
function Add-Result([string]$Step, [string]$Result, [double]$Seconds, [string]$Detail) {
    [void]$results.Add([pscustomobject]@{ Step = $Step; Result = $Result; Seconds = [math]::Round($Seconds, 1); Detail = $Detail })
    $color = @{ PASS = 'Green'; FAIL = 'Red'; SKIP = 'Yellow' }[$Result]
    Write-Host ("[gate] {0,-12} {1} ({2:N1}s) {3}" -f $Step, $Result, $Seconds, $Detail) -ForegroundColor $color
}

function Invoke-Uv([string[]]$UvArgs) {
    # native command: no 2>&1 in PowerShell 5.1; output goes to the host, the exit code is returned
    & uv run --frozen --no-sync @UvArgs | Out-Host
    return $LASTEXITCODE
}

function Get-Paths([string[]]$Candidates) {
    $out = @()
    foreach ($c in $Candidates) { if (Test-Path -LiteralPath (Join-Path $repo $c)) { $out += $c } }
    return , $out
}

# ---------------------------------------------------------------------------------------- target -> test paths
$t = $Target
$key = $null
foreach ($k in $modules.Keys) { if ($k -ieq $t) { $key = $k } }
$unit = @(); $review = @()
if ($t -ieq 'all') {
    $unit = Get-Paths @('tests/unit')
    $review = Get-Paths @('tests/review')
} elseif ($key -eq 'W1b') {
    $unit = Get-Paths @('tests/unit/runner', 'tests/unit/io', 'tests/unit/cli', 'tests/unit/ingest', 'tests/unit/worker',
                        'tests/unit/contract', 'tests/unit/fixtures', 'tests/unit/lib')
    $review = Get-Paths @('tests/review/W1b', 'tests/review/runtime', 'tests/review/lib', 'tests/review/fixtures',
                          'tests/review/contract', 'tests/review/platform', 'tests/review/R-CONTRACT', 'tests/review/R-PLATFORM')
} elseif ($key) {
    $unit = Get-Paths (@('tests/unit/contract') + ($modules[$key] | ForEach-Object { "tests/unit/$_" }))
    $review = Get-Paths (@("tests/review/$key", "tests/review/$($key.ToLower())") + ($modules[$key] | ForEach-Object { "tests/review/$_" }))
} else {
    # a single stage name
    $unit = Get-Paths @('tests/unit/contract', "tests/unit/$t")
    $review = Get-Paths @("tests/review/$t")
}
# pytest collects python files only; the JS lib tests run under node (step 8)
$unitPy = @($unit | Where-Object { $_ -ne 'tests/unit/lib' -or (Get-ChildItem -LiteralPath (Join-Path $repo $_) -Filter '*.py' -Recurse -ErrorAction SilentlyContinue) })
Write-Host "[gate] target=$Target unit=[$($unitPy -join ', ')] review=[$($review -join ', ')]"

# ---------------------------------------------------------------------------------------- 1. fixture
$fx = Join-Path $repo 'tests/contract/synth'
$t0 = Get-Date
if (Test-Path -LiteralPath (Join-Path $fx '.done.json')) {
    Add-Result 'fixture' 'PASS' 0 'tests/contract/synth/.done.json present'
} else {
    $report = Join-Path $repo 'docs/build/reports/fixtures.md'
    $cmd = $null
    if (Test-Path -LiteralPath $report) {
        $txt = Get-Content -LiteralPath $report -Raw -Encoding UTF8
        $m = [regex]::Match($txt, 'python -m (tests\.synth\.build(?:[ \t]+--?[A-Za-z][\w-]*(?:[ \t]+[\w.,-]+)?)*)')
        if ($m.Success) { $cmd = $m.Groups[1].Value.Trim() }
    }
    if ($cmd) {
        $parts = @('python', '-m') + ($cmd -split '\s+')
        $rc = Invoke-Uv $parts
        $ok = ($rc -eq 0) -and (Test-Path -LiteralPath (Join-Path $fx '.done.json'))
        Add-Result 'fixture' ($(if ($ok) { 'PASS' } else { 'FAIL' })) ((Get-Date) - $t0).TotalSeconds "regenerated: python -m $cmd"
    } else {
        Add-Result 'fixture' 'FAIL' 0 'tests/contract/synth/.done.json missing and docs/build/reports/fixtures.md names no generator'
    }
}

# ---------------------------------------------------------------------------------------- 2./3. pytest
foreach ($pair in @(@('unit', $unitPy), @('review', $review))) {
    $name = $pair[0]; $paths = @($pair[1])
    $t0 = Get-Date
    if ($paths.Count -eq 0) { Add-Result $name 'SKIP' 0 'no test folders for this target'; continue }
    # one pytest per folder: several folders ship their own conftest.py (rootdir import mode clashes otherwise)
    $codes = @()
    foreach ($p in $paths) {
        $c = Invoke-Uv @('python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', $p)
        $codes += "$($p.Split('/')[-1])=$c"
        if ($c -ne 0 -and $c -ne 5) { $rc = $c } elseif (-not $rc) { $rc = $c }
    }
    $bad = @($codes | Where-Object { $_ -notmatch '=(0|5)$' })
    # exit 5 = no tests collected
    $res = $(if ($bad.Count -gt 0) { 'FAIL' } elseif (@($codes | Where-Object { $_ -match '=0$' }).Count -gt 0) { 'PASS' } else { 'SKIP' })
    Add-Result $name $res ((Get-Date) - $t0).TotalSeconds ("pytest exit codes: " + ($codes -join ' '))
    $rc = $null
}

# ---------------------------------------------------------------------------------------- 4. ruff
$t0 = Get-Date
$rc = Invoke-Uv @('ruff', 'check', 'src', 'tests')
Add-Result 'ruff' ($(if ($rc -eq 0) { 'PASS' } else { 'FAIL' })) ((Get-Date) - $t0).TotalSeconds "ruff check src tests (exit $rc)"

# ---------------------------------------------------------------------------------------- 5. contract
$t0 = Get-Date
$rc = Invoke-Uv @('python', '-m', 'mvh.contract.gen', '--check')
Add-Result 'contract' ($(if ($rc -eq 0) { 'PASS' } else { 'FAIL' })) ((Get-Date) - $t0).TotalSeconds 'python -m mvh.contract.gen --check'

# ---------------------------------------------------------------------------------------- 6. validate fixture
$t0 = Get-Date
if (Test-Path -LiteralPath (Join-Path $fx 'manifest.json')) {
    $rc = Invoke-Uv @('python', '-m', 'mvh.cli', 'validate', $fx)
    Add-Result 'validate' ($(if ($rc -eq 0) { 'PASS' } else { 'FAIL' })) ((Get-Date) - $t0).TotalSeconds 'mvh validate tests/contract/synth'
} else {
    Add-Result 'validate' 'FAIL' 0 'tests/contract/synth/manifest.json missing'
}

# ---------------------------------------------------------------------------------------- 7./9. e2e + determinism
$tmp = Join-Path $env:TEMP ('mvh-gate-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$song = Join-Path $tmp 'synth song'
$songIn = Join-Path $fx '_truth/synth-song.flac'
if (-not (Test-Path -LiteralPath $songIn)) { $songIn = Join-Path $fx 'audio/mix.flac' }
if ($SkipE2E) {
    Add-Result 'e2e' 'SKIP' 0 '-SkipE2E'
} elseif (-not (Test-Path -LiteralPath $songIn)) {
    Add-Result 'e2e' 'FAIL' 0 'no fixture song to analyse'
} else {
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $env:MVH_FIXTURE_DIR = $fx
    $t0 = Get-Date
    $rc = Invoke-Uv @('python', '-m', 'mvh.cli', 'analyze', $songIn, '--out', $song, '--slug', 'synth')
    $ok = $rc -eq 0
    if ($ok) { $rc2 = Invoke-Uv @('python', '-m', 'mvh.cli', 'validate', $song); $ok = $rc2 -eq 0 }
    Add-Result 'e2e' ($(if ($ok) { 'PASS' } else { 'FAIL' })) ((Get-Date) - $t0).TotalSeconds "mvh analyze + validate -> $song"
}

# ---------------------------------------------------------------------------------------- 8. node lib tests
$t0 = Get-Date
$libDir = Join-Path $repo 'tests/unit/lib'
$jsTests = @()
if (Test-Path -LiteralPath $libDir) {
    $jsTests = @(Get-ChildItem -LiteralPath $libDir -Recurse -File |
                 Where-Object { $_.Name -match '(\.test\.(m?js|cjs)$)|(^test[-_].*\.(m?js|cjs)$)' })
}
if ($jsTests.Count -eq 0) {
    Add-Result 'lib-node' 'SKIP' 0 'no JS tests under tests/unit/lib'
} elseif (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Add-Result 'lib-node' 'FAIL' 0 'node not on PATH'
} else {
    # relative forward-slash paths: node --test treats its arguments as glob patterns (backslashes are escapes)
    $rel = @($jsTests | ForEach-Object { $_.FullName.Substring($repo.Length + 1).Replace('\', '/') })
    & node --test @rel | Out-Host
    $rc = $LASTEXITCODE
    Add-Result 'lib-node' ($(if ($rc -eq 0) { 'PASS' } else { 'FAIL' })) ((Get-Date) - $t0).TotalSeconds "node --test ($($jsTests.Count) files)"
}

if (-not $SkipE2E -and (Test-Path -LiteralPath (Join-Path $song 'manifest.json'))) {
    $t0 = Get-Date
    $a = Join-Path $tmp 'snap-a.json'; $b = Join-Path $tmp 'snap-b.json'
    $rc = Invoke-Uv @('python', '-m', 'mvh.runner.snapshot', 'hash', $song, $a)
    $rc = Invoke-Uv @('python', '-m', 'mvh.cli', 'analyze', $songIn, '--out', $song, '--slug', 'synth', '--force')
    $ok = $rc -eq 0
    $rc = Invoke-Uv @('python', '-m', 'mvh.runner.snapshot', 'hash', $song, $b)
    $rc = Invoke-Uv @('python', '-m', 'mvh.runner.snapshot', 'diff', $a, $b)
    $ok = $ok -and ($rc -eq 0)
    Add-Result 'determinism' ($(if ($ok) { 'PASS' } else { 'FAIL' })) ((Get-Date) - $t0).TotalSeconds 'analyze --force twice, diff all but run.json/.cache'
} elseif (-not $SkipE2E) {
    Add-Result 'determinism' 'FAIL' 0 'no e2e output to compare'
} else {
    Add-Result 'determinism' 'SKIP' 0 '-SkipE2E'
}
Remove-Item Env:MVH_FIXTURE_DIR -ErrorAction SilentlyContinue
if (-not $KeepTemp -and (Test-Path -LiteralPath $tmp)) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }

# ---------------------------------------------------------------------------------------- summary
Write-Host ''
Write-Host "gate $Target summary"
$results | Format-Table -AutoSize Step, Result, Seconds, Detail | Out-Host
$failed = @($results | Where-Object { $_.Result -eq 'FAIL' })
if ($failed.Count -gt 0) {
    Write-Host ("GATE FAILED: " + (($failed | ForEach-Object { $_.Step }) -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host 'GATE PASSED' -ForegroundColor Green
exit 0
