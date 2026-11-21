$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'frontend')
if (-not (Test-Path 'node_modules')) { npm ci --no-audit --no-fund }
npm run dev
