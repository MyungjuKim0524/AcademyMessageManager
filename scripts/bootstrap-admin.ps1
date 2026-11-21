$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$container = 'academy-learningops-postgres-dev'

if (-not $env:ACADEMY_BOOTSTRAP_EMAIL -or -not $env:ACADEMY_BOOTSTRAP_PASSWORD) {
    throw 'ACADEMY_BOOTSTRAP_EMAIL and ACADEMY_BOOTSTRAP_PASSWORD must be set.'
}

$inspectOutput = docker inspect $container
if ($LASTEXITCODE -ne 0) { throw 'Development PostgreSQL container is unavailable.' }
$inspect = ($inspectOutput | ConvertFrom-Json)[0]
$binding = $inspect.HostConfig.PortBindings.'5432/tcp' | Select-Object -First 1
if ($inspect.Config.Labels.'academy.environment' -ne 'isolated-development' -or
    $inspect.State.Status -ne 'running' -or
    $binding.HostIp -ne '127.0.0.1' -or $binding.HostPort -ne '55431') {
    throw 'Development PostgreSQL container identity does not match the allowlist.'
}
$containerEnvironment = $inspect.Config.Env
$passwordEntry = $containerEnvironment | Where-Object { $_ -like 'POSTGRES_PASSWORD=*' } | Select-Object -First 1
if (-not $passwordEntry) { throw 'Development PostgreSQL credential is unavailable.' }
$databasePassword = $passwordEntry.Substring('POSTGRES_PASSWORD='.Length)

$env:ACADEMY_BOOTSTRAP_ADMIN = '1'
$env:ACADEMY_DB_MODE = 'development'
$env:ACADEMY_DB_TEST_MODE = '0'
$encodedPassword = [uri]::EscapeDataString($databasePassword)
$env:ACADEMY_DATABASE_URL = "postgresql+psycopg://academy_dev:$encodedPassword@127.0.0.1:55431/academy_learningops_dev"

Push-Location $backend
try {
    & '.\.venv\Scripts\python.exe' 'scripts\bootstrap_admin.py'
    if ($LASTEXITCODE -ne 0) { throw 'Administrator bootstrap failed.' }
}
finally {
    $encodedPassword = $null
    $databasePassword = $null
    $passwordEntry = $null
    $containerEnvironment = $null
    $inspect = $null
    $inspectOutput = $null
    Pop-Location
}
