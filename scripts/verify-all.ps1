$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'use-d-drive-dev-env.ps1')
function Invoke-Step([string]$Name,[scriptblock]$Action){Write-Host "[START] $Name";& $Action;if($LASTEXITCODE -ne 0){throw "$Name failed with exit code $LASTEXITCODE"};Write-Host "[PASS] $Name"}

# No database needed: the PostgreSQL integration tests run separately with
# scripts\run-postgres-integration.ps1 against the isolated test DB only.
# (The Java legacy Maven step was removed in Phase 11-5 Step 1: Java is not in this repository.)
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'backend\.venv not found. Create it first (see backend\README.md).' }
Set-Location $backend
Remove-Item Env:ACADEMY_DATABASE_URL -ErrorAction SilentlyContinue
Invoke-Step 'Backend lint (Ruff)' { & $python -m ruff check . }
Invoke-Step 'Backend unit tests (pytest, no DB)' { & $python -m pytest -m 'not postgres' -q }

Set-Location (Join-Path $root 'frontend')
Invoke-Step 'Frontend lint' { npm run lint }
Invoke-Step 'Frontend test' { npm test }
Invoke-Step 'Frontend build' { npm run build }
