$ErrorActionPreference = 'Stop'
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
$containerEnvironment = $inspect.Config.Env
$passwordEntry = $containerEnvironment | Where-Object { $_ -like 'POSTGRES_PASSWORD=*' } | Select-Object -First 1
if (-not $passwordEntry) { throw 'Development PostgreSQL credential is unavailable.' }
$databasePassword = $passwordEntry.Substring('POSTGRES_PASSWORD='.Length)

$env:ACADEMY_ENABLE_DB_APIS = '1'
$env:ACADEMY_API_HOST = '127.0.0.1'
$env:ACADEMY_DB_MODE = 'development'
$env:ACADEMY_DB_TEST_MODE = '0'
$env:ACADEMY_API_DOCS = '1'  # local only: /docs, /openapi.json (off by default, SEC-08)
$encodedPassword = [uri]::EscapeDataString($databasePassword)
$env:ACADEMY_DATABASE_URL = "postgresql+psycopg://academy_dev:$encodedPassword@127.0.0.1:55431/academy_learningops_dev"

Push-Location $backend
try {
    & '.\.venv\Scripts\python.exe' 'scripts\auth_preflight.py'
    if ($LASTEXITCODE -ne 0) { throw 'FastAPI authentication preflight failed.' }
    # --no-proxy-headers: the app decides which X-Forwarded-For to trust (ACADEMY_TRUSTED_PROXIES).
    # --no-access-log: the app's own request log has no query strings (e.g. ?q=<student name>).
    & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
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
