$ErrorActionPreference = 'Stop'

$composeFile = Join-Path $PSScriptRoot '..\compose.postgres-test.yml'
$backendDir = Join-Path $PSScriptRoot '..\backend'
$container = 'academy-learningops-postgres-test'

# Python (FastAPI) PostgreSQL integration tests only. The Java legacy app is not part of this
# repository, so its Maven integration step was removed (Phase 11-5 Step 1).
if (-not $env:ACADEMY_TEST_DB_PASSWORD) {
    throw 'ACADEMY_TEST_DB_PASSWORD must be set locally before running integration tests.'
}

# Fail closed: every check below must positively succeed. No --format template is passed, because
# Windows PowerShell 5.1 strips embedded double quotes from native arguments (the old
# '{{index .Config.Labels "academy.environment"}}' became a template error, the output was empty
# and the negative -notmatch checks let it through). A native non-zero exit code does not stop
# the script under $ErrorActionPreference, so it is checked explicitly.
$inspectJson = docker inspect $container
if ($LASTEXITCODE -ne 0 -or -not $inspectJson) {
    throw "Refusing destructive tests: 'docker inspect $container' failed (exit $LASTEXITCODE) or returned nothing."
}
try { $inspected = @(($inspectJson -join "`n") | ConvertFrom-Json) }
catch { throw "Refusing destructive tests: 'docker inspect' output is not valid JSON." }
if ($inspected.Count -ne 1 -or $inspected[0].Name -ne "/$container") {
    throw "Refusing destructive tests: 'docker inspect' did not return exactly the container $container."
}
$labels = $inspected[0].Config.Labels
$bindings = @($inspected[0].HostConfig.PortBindings.'5432/tcp')
$environmentLabel = if ($labels) { $labels.'academy.environment' } else { $null }
$destructiveLabel = if ($labels) { $labels.'academy.destructive-tests' } else { $null }
$bindingText = ($bindings | ForEach-Object { "$($_.HostIp):$($_.HostPort)" }) -join ','
if ($environmentLabel -cne 'isolated-test' -or $destructiveLabel -cne 'allowed' -or $bindingText -ne '127.0.0.1:55432') {
    throw "Refusing destructive tests: unexpected container identity: environment=[$environmentLabel] destructive-tests=[$destructiveLabel] port=[$bindingText]"
}

$databaseIdentity = docker exec $container psql -U academy_test -d academy_learningops_test -Atc 'SELECT current_database() || ''|'' || current_user'
if ($LASTEXITCODE -ne 0 -or -not $databaseIdentity -or ([string]$databaseIdentity).Trim() -ne 'academy_learningops_test|academy_test') {
    throw "Refusing destructive tests: unexpected database identity: $databaseIdentity"
}

$env:ACADEMY_DB_TEST_MODE = '1'
$env:ACADEMY_DB_MODE = 'test'
$env:ACADEMY_RUN_POSTGRES_INTEGRATION = '1'
$encodedPassword = [uri]::EscapeDataString($env:ACADEMY_TEST_DB_PASSWORD)
$env:ACADEMY_DATABASE_URL = "postgresql+psycopg://academy_test:$encodedPassword@127.0.0.1:55432/academy_learningops_test"
$encodedPassword = $null

Push-Location $backendDir
try {
    & '.\.venv\Scripts\pytest.exe' -q -m postgres
    if ($LASTEXITCODE -ne 0) { throw 'Python PostgreSQL integration tests failed.' }
}
finally {
    Remove-Item Env:ACADEMY_DATABASE_URL -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host "Test DB remains running. Stop without deleting its volume:"
Write-Host "docker compose -f $composeFile stop"
