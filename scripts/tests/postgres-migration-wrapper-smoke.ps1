$ErrorActionPreference = "Stop"
trap {
    $failureMessage = [string]$_.Exception.Message
    $failureMessage = $failureMessage.Replace("%", "%25").Replace("`r", "%0D").Replace("`n", "%0A")
    Write-Output "::error title=PowerShell migration wrapper smoke failure::$failureMessage"
    exit 1
}

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
        throw "PowerShell requested prompt '$Prompt' with secret=$([bool]$Secret), but its queued input expects secret=$([bool]$next.secret)."
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
    Write-Output "synthetic inventory report line one"
    Write-Output "synthetic inventory report line two"
    [Console]::Error.WriteLine("synthetic native stderr diagnostic")
    $global:LASTEXITCODE = 0
}
$originalErrorWriter = [Console]::Error
$successErrorWriter = New-Object System.IO.StringWriter
[Console]::SetError($successErrorWriter)
try {
    $restoreExitCode = Invoke-PostgresMigrationOperation `
        -Operation "restore" `
        -Archive "C:\migration private\source.dump" `
        -Report "C:\migration private\restore report.json" `
        -RepositoryRoot $repositoryRoot `
        -InputProvider $inputProvider `
        -NodeInvoker $successfulNode
}
finally {
    [Console]::SetError($originalErrorWriter)
}
if ($restoreExitCode -isnot [int] -or $restoreExitCode -ne 0) {
    $details = $successErrorWriter.ToString().Trim()
    throw "A successful synthetic Node invocation did not return exactly one integer 0. Details: $details"
}
if ($successErrorWriter.ToString() -notlike "*synthetic native stderr diagnostic*") {
    throw "The successful synthetic Node invocation did not preserve stderr diagnostics."
}
if ($global:MigrationWrapperSmokeSource) {
    throw "The restore operation unexpectedly received a source URL."
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
if ($global:MigrationWrapperSmokeArguments -contains $global:MigrationWrapperSmokeTarget -or
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
    Write-Output "synthetic failed report line one"
    Write-Output "synthetic failed report line two"
    [Console]::Error.WriteLine("synthetic failed native stderr diagnostic")
    $global:LASTEXITCODE = 23
}
$failureErrorWriter = New-Object System.IO.StringWriter
[Console]::SetError($failureErrorWriter)
try {
    $failedExitCode = Invoke-PostgresMigrationOperation `
        -Operation "inventory" `
        -RepositoryRoot $repositoryRoot `
        -InputProvider $failedInputProvider `
        -NodeInvoker $failingNode
}
finally {
    [Console]::SetError($originalErrorWriter)
}
if ($failedExitCode -isnot [int] -or $failedExitCode -ne 23) {
    $details = $failureErrorWriter.ToString().Trim()
    throw "The wrapper did not return exactly one integer child failure exit code 23. Details: $details"
}
if ($failureErrorWriter.ToString() -notlike "*synthetic failed native stderr diagnostic*") {
    throw "The failed synthetic Node invocation did not preserve stderr diagnostics."
}
if ($global:MigrationWrapperSmokeSource -notlike "postgresql+psycopg://source:*") {
    throw "The failure-path child process did not receive its synthetic source URL."
}
foreach ($name in $environmentNames) {
    if ($null -ne [Environment]::GetEnvironmentVariable($name, "Process")) {
        throw "Migration environment variable $name remained after the wrapper returned."
    }
}

$global:LASTEXITCODE = 0
$nativeSmokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) `
    ("postgres-migration-wrapper-smoke-" + [Guid]::NewGuid().ToString("N"))
$nativeSmokeNodeDirectory = Join-Path $nativeSmokeRoot "bin"
$nativeSmokeNodePath = Join-Path $nativeSmokeNodeDirectory "node.cmd"
$nativeSmokeDriverPath = Join-Path $nativeSmokeRoot "invoke-wrapper.ps1"
$wrapperPath = Join-Path $repositoryRoot "scripts/postgres-migration.ps1"
$wrapperLiteral = "'" + $wrapperPath.Replace("'", "''") + "'"
$nodeStub = @'
@echo off
echo synthetic native inventory report line one
echo synthetic native inventory report line two
echo synthetic native stderr diagnostic 1>&2
echo synthetic native exit marker %MIGRATION_WRAPPER_SMOKE_EXIT_CODE% 1>&2
exit /b %MIGRATION_WRAPPER_SMOKE_EXIT_CODE%
'@
$driver = @"
function global:Read-Host {
    param([string]`$Prompt, [switch]`$AsSecureString)
    if (`$Prompt -notlike "Paste the local portfolio_app PostgreSQL 18 URL*") {
        throw "Unexpected wrapper prompt."
    }
    `$value = "postgresql+psycopg://source:synthetic@127.0.0.1/portfolio_app"
    if (`$AsSecureString) {
        return ConvertTo-SecureString -String `$value -AsPlainText -Force
    }
    return `$value
}
try {
    & $wrapperLiteral -Operation inventory
}
catch {
    [Console]::Error.WriteLine("The end-to-end wrapper invocation threw: " + [string]$_.Exception.Message)
    exit 97
}
`$remainingMigrationEnvironment = @(
    "MIGRATION_SOURCE_URL", "MIGRATION_SOURCE_SCHEMA", "MIGRATION_TARGET_URL",
    "MIGRATION_TARGET_SCHEMA", "MIGRATION_EXPECTED_TARGET_HOST",
    "MIGRATION_EXPECTED_TARGET_DATABASE", "MIGRATION_NEON_API_KEY",
    "MIGRATION_NEON_PROJECT_ID", "MIGRATION_NEON_TARGET_BRANCH_ID",
    "MIGRATION_NEON_TARGET_ENDPOINT_ID", "MIGRATION_PRODUCTION_HOST",
    "MIGRATION_ALLOW_TEST_TARGET", "MIGRATION_PG_TOOLS_CONTAINER"
) | Where-Object { `$null -ne [Environment]::GetEnvironmentVariable(`$_, "Process") }
if (`$remainingMigrationEnvironment.Count -gt 0) {
    [Console]::Error.WriteLine("The wrapper left migration environment variables active: " + (`$remainingMigrationEnvironment -join ", "))
    exit 98
}
Write-Output "synthetic wrapper last exit marker `$LASTEXITCODE"
exit [int]$LASTEXITCODE
"@

$originalPath = $env:PATH
$hadOriginalNativeExit = Test-Path Env:MIGRATION_WRAPPER_SMOKE_EXIT_CODE
$originalNativeExit = $env:MIGRATION_WRAPPER_SMOKE_EXIT_CODE
$hadOriginalNativeSource = Test-Path Env:MIGRATION_SOURCE_URL
$originalNativeSource = $env:MIGRATION_SOURCE_URL
try {
    New-Item -ItemType Directory -Path $nativeSmokeNodeDirectory -Force | Out-Null
    Set-Content -LiteralPath $nativeSmokeNodePath -Value $nodeStub -Encoding ASCII
    Set-Content -LiteralPath $nativeSmokeDriverPath -Value $driver -Encoding ASCII
    $env:PATH = "$nativeSmokeNodeDirectory;$originalPath"
    $nativeShell = if ($PSVersionTable.PSEdition -eq "Desktop") {
        Join-Path $PSHOME "powershell.exe"
    }
    else {
        Join-Path $PSHOME "pwsh.exe"
    }
    foreach ($expectedExitCode in @(0)) {
        $env:MIGRATION_WRAPPER_SMOKE_EXIT_CODE = [string]$expectedExitCode
        Remove-Item Env:MIGRATION_SOURCE_URL -ErrorAction SilentlyContinue
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = $nativeShell
        $startInfo.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$nativeSmokeDriverPath`""
        $startInfo.WorkingDirectory = $repositoryRoot
        $startInfo.UseShellExecute = $false
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            throw "Could not start the end-to-end wrapper smoke process."
        }
        $childStdout = $process.StandardOutput.ReadToEnd()
        $childStderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $processExitCode = $process.ExitCode
        $process.Dispose()

        if ($processExitCode -ne $expectedExitCode) {
            throw "The wrapper process returned $processExitCode for the synthetic native exit code $expectedExitCode. stdout: $childStdout stderr: $childStderr"
        }
        if ($childStdout -notlike "*synthetic native inventory report line one*" -or
            $childStdout -notlike "*synthetic native inventory report line two*") {
            throw "The end-to-end wrapper did not preserve multiple native stdout lines. stdout: $childStdout stderr: $childStderr"
        }
        if (($childStdout + $childStderr) -notlike "*synthetic native stderr diagnostic*") {
            throw "The end-to-end wrapper did not preserve the native stderr diagnostic. stdout: $childStdout stderr: $childStderr"
        }
        if (($childStdout + $childStderr) -notlike "*synthetic native exit marker $expectedExitCode*") {
            throw "The end-to-end native shim did not receive its configured exit code. stdout: $childStdout stderr: $childStderr"
        }
        if (($childStdout + $childStderr) -match "postgresql\+psycopg://source:synthetic") {
            throw "The end-to-end wrapper exposed its hidden database URL."
        }
    }
}
finally {
    $env:PATH = $originalPath
    if ($hadOriginalNativeExit) {
        $env:MIGRATION_WRAPPER_SMOKE_EXIT_CODE = $originalNativeExit
    }
    else {
        Remove-Item Env:MIGRATION_WRAPPER_SMOKE_EXIT_CODE -ErrorAction SilentlyContinue
    }
    if ($hadOriginalNativeSource) {
        $env:MIGRATION_SOURCE_URL = $originalNativeSource
    }
    else {
        Remove-Item Env:MIGRATION_SOURCE_URL -ErrorAction SilentlyContinue
    }
    $temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $temporaryPrefix = $temporaryRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + `
        [System.IO.Path]::DirectorySeparatorChar
    $smokeRoot = [System.IO.Path]::GetFullPath($nativeSmokeRoot)
    if (-not $smokeRoot.StartsWith($temporaryPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        [System.IO.Path]::GetFileName($smokeRoot) -notlike "postgres-migration-wrapper-smoke-*") {
        throw "Refusing to remove a path outside this migration smoke test's temporary directory."
    }
    Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Remove-Variable MigrationWrapperSmokeArguments, MigrationWrapperSmokeSource, `
    MigrationWrapperSmokeTarget, MigrationWrapperSmokeApiKey, MigrationWrapperSmokeLegacyHost `
    -Scope Global -ErrorAction SilentlyContinue
Write-Output "PowerShell migration wrapper syntax, argument, environment, stdout/stderr and end-to-end exit-code smoke tests passed."
