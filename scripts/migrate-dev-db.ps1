$ErrorActionPreference = 'Stop'
# Applies pending Alembic migrations to the isolated DEVELOPMENT database only.
# Same container identity checks as start-fastapi.ps1; the password is never printed.
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$container = 'academy-learningops-postgres-dev'

$inspectOutput = docker inspect $container
if ($LASTEXITCODE -ne 0) { throw 'Development PostgreSQL container is unavailable.' }
$inspect = ($inspectOutput | ConvertFrom-Json)[0]
$binding = $inspect.HostConfig.PortBindings.'5432/tcp' | Select-Object -First 1
if ($inspect.Config.Labels.'academy.environment' -ne 'isolated-development' -or
    $inspect.State.Status -ne 'running' -or
    $binding.HostIp -ne '127.0.0.1' -or $binding.HostPort -ne '55431') {
    throw 'Development PostgreSQL container identity does not match the allowlist.'
}
$passwordEntry = $inspect.Config.Env | Where-Object { $_ -like 'POSTGRES_PASSWORD=*' } | Select-Object -First 1
if (-not $passwordEntry) { throw 'Development PostgreSQL credential is unavailable.' }

$env:ACADEMY_DB_MODE = 'development'
$env:ACADEMY_DB_TEST_MODE = '0'
$encodedPassword = [uri]::EscapeDataString($passwordEntry.Substring('POSTGRES_PASSWORD='.Length))
$env:ACADEMY_DATABASE_URL = "postgresql+psycopg://academy_dev:$encodedPassword@127.0.0.1:55431/academy_learningops_dev"

Push-Location $backend
try {
    Write-Host 'Current revision:'
    cmd /c ".venv\Scripts\alembic.exe current 2>&1"
    cmd /c ".venv\Scripts\alembic.exe upgrade head 2>&1"
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed. Nothing after the failing step was applied.' }
    Write-Host 'Now at:'
    cmd /c ".venv\Scripts\alembic.exe current 2>&1"
}
finally {
    $encodedPassword = $null
    $passwordEntry = $null
    $inspect = $null
    $inspectOutput = $null
    Remove-Item Env:ACADEMY_DATABASE_URL -ErrorAction SilentlyContinue
    Pop-Location
}
