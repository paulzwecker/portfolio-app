$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$powerShellFiles = @(
    (Join-Path $repositoryRoot "scripts/postgres-migration.ps1"),
    (Join-Path $repositoryRoot "scripts/PostgresMigration.psm1"),
    $PSCommandPath
)
foreach ($path in $powerShellFiles) {
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $path, [ref]$tokens, [ref]$parseErrors
    ) | Out-Null
    if ($parseErrors.Count -gt 0) {
        throw "PowerShell syntax validation failed for $([System.IO.Path]::GetFileName($path))."
    }
}

Import-Module (Join-Path $repositoryRoot "scripts/PostgresMigration.psm1") -Force

$restoreArguments = New-MigrationArgumentList `
    -Operation "restore" `
    -Archive "C:\migration private\source.dump" `
    -Report "C:\migration private\restore report.json" `
    -Confirmation "RESTORE synthetic.neon.tech/portfolio_migration"
$expectedRestoreArguments = @(
    "scripts/uv.mjs", "run", "--locked", "--project", "apps/api", "python", "-m",
    "portfolio_api.postgres_migration", "restore", "--archive", "C:\migration private\source.dump",
    "--confirm-target", "RESTORE synthetic.neon.tech/portfolio_migration", "--report",
    "C:\migration private\restore report.json"
)
if (($restoreArguments -join "`n") -cne ($expectedRestoreArguments -join "`n")) {
    throw "PowerShell did not preserve restore arguments as separate, exact tokens."
}
$backupArguments = New-MigrationArgumentList `
    -Operation "backup" `
    -Output "C:\migration private\source backup.dump" `
    -Report "C:\migration private\backup report.json"
$expectedBackupArguments = @(
    "scripts/uv.mjs", "run", "--locked", "--project", "apps/api", "python", "-m",
    "portfolio_api.postgres_migration", "backup", "--output",
    "C:\migration private\source backup.dump", "--report", "C:\migration private\backup report.json"
)
if (($backupArguments -join "`n") -cne ($expectedBackupArguments -join "`n")) {
    throw "PowerShell did not preserve backup output and report paths as exact tokens."
}

$environmentNames = @(
    "MIGRATION_SOURCE_URL", "MIGRATION_SOURCE_SCHEMA", "MIGRATION_TARGET_URL",
    "MIGRATION_TARGET_SCHEMA", "MIGRATION_EXPECTED_TARGET_HOST",
    "MIGRATION_EXPECTED_TARGET_DATABASE", "MIGRATION_NEON_API_KEY",
    "MIGRATION_NEON_PROJECT_ID", "MIGRATION_NEON_TARGET_BRANCH_ID",
    "MIGRATION_NEON_TARGET_ENDPOINT_ID", "MIGRATION_PRODUCTION_HOST",
    "MIGRATION_ALLOW_TEST_TARGET", "MIGRATION_PG_TOOLS_CONTAINER"
)
foreach ($name in $environmentNames) {
    Set-Item "Env:$name" "inherited-sentinel"
}

$queuedInputs = New-Object System.Collections.Queue
$inputValues = @(
    @{ value = "postgresql+psycopg://source:synthetic@127.0.0.1/portfolio_app"; secret = $true },
    @{ value = "postgresql+psycopg://target:synthetic@synthetic.neon.tech/portfolio_migration?sslmode=require"; secret = $true },
    @{ value = "synthetic.neon.tech"; secret = $false },
    @{ value = "portfolio_migration"; secret = $false },
    @{ value = "synthetic-neon-api-key"; secret = $true },
    @{ value = "synthetic-project-id"; secret = $false },
    @{ value = "br-synthetic-migration"; secret = $false },
    @{ value = "ep-synthetic-migration"; secret = $false },
    @{ value = "RESTORE synthetic.neon.tech/portfolio_migration"; secret = $false }
)
foreach ($value in $inputValues) {
    $queuedInputs.Enqueue($value)
}
$inputProvider = {
    param($Prompt, $Secret)
    $next = $queuedInputs.Dequeue()
    if ([bool]$next.secret -ne [bool]$Secret) {
        throw "PowerShell requested an input using the wrong secrecy mode."
    }
    return [string]$next.value
}.GetNewClosure()
$successfulNode = {
    param($Arguments)
    $global:MigrationWrapperSmokeArguments = @($Arguments)
    $global:MigrationWrapperSmokeSource = $env:MIGRATION_SOURCE_URL
    $global:MigrationWrapperSmokeTarget = $env:MIGRATION_TARGET_URL
    $global:MigrationWrapperSmokeApiKey = $env:MIGRATION_NEON_API_KEY
    $global:MigrationWrapperSmokeLegacyHost = $env:MIGRATION_PRODUCTION_HOST
    $global:LASTEXITCODE = 0
}
$restoreExitCode = Invoke-PostgresMigrationOperation `
    -Operation "restore" `
    -Archive "C:\migration private\source.dump" `
    -Report "C:\migration private\restore report.json" `
    -RepositoryRoot $repositoryRoot `
    -InputProvider $inputProvider `
    -NodeInvoker $successfulNode
if ($restoreExitCode -ne 0) {
    throw "A successful synthetic Node invocation did not propagate exit code 0."
}
if ($global:MigrationWrapperSmokeSource -notlike "postgresql+psycopg://source:*") {
    throw "The child process did not receive the source URL in its environment."
}
if ($global:MigrationWrapperSmokeTarget -notlike "postgresql+psycopg://target:*") {
    throw "The child process did not receive the target URL in its environment."
}
if ($global:MigrationWrapperSmokeApiKey -ne "synthetic-neon-api-key") {
    throw "The child process did not receive the synthetic Neon API key."
}
if (($global:MigrationWrapperSmokeArguments -join "`n") -cne ($expectedRestoreArguments -join "`n")) {
    throw "The wrapper did not pass each restore argument as a distinct token."
}
if ($global:MigrationWrapperSmokeLegacyHost) {
    throw "A legacy user-entered production hostname remained active."
}
if ($global:MigrationWrapperSmokeArguments -contains $global:MigrationWrapperSmokeSource -or
    $global:MigrationWrapperSmokeArguments -contains $global:MigrationWrapperSmokeTarget -or
    $global:MigrationWrapperSmokeArguments -contains $global:MigrationWrapperSmokeApiKey) {
    throw "A database URL or Neon API key was exposed in command-line arguments."
}
if ($queuedInputs.Count -ne 0) {
    throw "The restore smoke test did not consume each expected prompt exactly once."
}
foreach ($name in $environmentNames) {
    if ($null -ne [Environment]::GetEnvironmentVariable($name, "Process")) {
        throw "Migration environment variable $name remained after successful execution."
    }
}

$failedInputQueue = New-Object System.Collections.Queue
$failedInputQueue.Enqueue("postgresql+psycopg://source:synthetic@127.0.0.1/portfolio_app")
$failedInputProvider = {
    param($Prompt, $Secret)
    return [string]$failedInputQueue.Dequeue()
}.GetNewClosure()
$failingNode = {
    param($Arguments)
    $global:MigrationWrapperSmokeSource = $env:MIGRATION_SOURCE_URL
    $global:LASTEXITCODE = 23
}
$failedExitCode = Invoke-PostgresMigrationOperation `
    -Operation "inventory" `
    -RepositoryRoot $repositoryRoot `
    -InputProvider $failedInputProvider `
    -NodeInvoker $failingNode
if ($failedExitCode -ne 23) {
    throw "The wrapper did not propagate the child process failure exit code."
}
if ($global:MigrationWrapperSmokeSource -notlike "postgresql+psycopg://source:*") {
    throw "The failure-path child process did not receive its synthetic source URL."
}
foreach ($name in $environmentNames) {
    if ($null -ne [Environment]::GetEnvironmentVariable($name, "Process")) {
        throw "Migration environment variable $name remained after the wrapper returned."
    }
}

Remove-Variable MigrationWrapperSmokeArguments, MigrationWrapperSmokeSource, `
    MigrationWrapperSmokeTarget, MigrationWrapperSmokeApiKey, MigrationWrapperSmokeLegacyHost `
    -Scope Global -ErrorAction SilentlyContinue
Write-Output "PowerShell migration wrapper syntax, argument, environment and exit-code smoke tests passed."
