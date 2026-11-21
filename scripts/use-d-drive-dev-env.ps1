$ErrorActionPreference = 'Stop'

# Apply storage paths only to the current PowerShell process. Dot-source this file
# before development commands; it never changes user/system environment variables.
$projectRoot = Split-Path -Parent $PSScriptRoot
$devData = Join-Path $projectRoot '.dev-data'
$paths = @{
    Temp = Join-Path $devData 'tmp'
    PipCache = Join-Path $devData 'pip-cache'
    NpmCache = Join-Path $devData 'npm-cache'
    PytestCache = Join-Path $devData 'pytest-cache'
    RuffCache = Join-Path $devData 'ruff-cache'
    Coverage = Join-Path $devData 'coverage'
}

$paths.Values | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        New-Item -ItemType Directory -Path $_ | Out-Null
    }
}

$env:TEMP = $paths.Temp
$env:TMP = $paths.Temp
$env:PIP_CACHE_DIR = $paths.PipCache
$env:npm_config_cache = $paths.NpmCache
$env:RUFF_CACHE_DIR = $paths.RuffCache
$env:COVERAGE_FILE = Join-Path $paths.Coverage '.coverage'
$env:PYTEST_ADDOPTS = (($env:PYTEST_ADDOPTS, "-o cache_dir=$($paths.PytestCache)") |
    Where-Object { $_ }) -join ' '

Write-Host "Project-local development data: $devData"
