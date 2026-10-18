[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "inventory",
        "capacity",
        "schema-check",
        "backup",
        "verify-backup",
        "restore",
        "reconcile",
        "cutover-preflight"
    )]
    [string]$Operation,

    [string]$Archive,
    [string]$Output,
    [string]$Report
)

$ErrorActionPreference = "Stop"

function Read-ConnectionUrl {
    param([Parameter(Mandatory = $true)][string]$Prompt)

    $secureValue = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secureValue.Dispose()
    }
}

function Set-TargetIdentity {
    $script:TargetUrl = Read-ConnectionUrl `
        "Paste the isolated Neon migration database URL (input is hidden)"
    $env:MIGRATION_EXPECTED_TARGET_HOST = Read-Host `
        "Expected direct Neon hostname for this isolated migration database"
    $env:MIGRATION_EXPECTED_TARGET_DATABASE = Read-Host `
        "Expected database name; it must end in _migration"
    $env:MIGRATION_PRODUCTION_HOST = Read-Host `
        "Protected production Neon hostname only (never paste a URL or password)"
    $env:MIGRATION_TARGET_URL = $script:TargetUrl
}

$migrationEnvironmentNames = @(
    "MIGRATION_SOURCE_URL",
    "MIGRATION_SOURCE_SCHEMA",
    "MIGRATION_TARGET_URL",
    "MIGRATION_TARGET_SCHEMA",
    "MIGRATION_EXPECTED_TARGET_HOST",
    "MIGRATION_EXPECTED_TARGET_DATABASE",
    "MIGRATION_PRODUCTION_HOST",
    "MIGRATION_ALLOW_TEST_TARGET",
    "MIGRATION_PG_TOOLS_CONTAINER"
)
foreach ($name in $migrationEnvironmentNames) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

$requiresSource = @("inventory", "capacity", "schema-check", "backup", "reconcile", "cutover-preflight") -contains $Operation
$requiresTarget = @("schema-check", "restore", "reconcile", "cutover-preflight") -contains $Operation

if ($Operation -eq "backup" -and [string]::IsNullOrWhiteSpace($Output)) {
    throw "Backup requires -Output pointing to a new private file outside the repository."
}
if (@("verify-backup", "restore", "cutover-preflight") -contains $Operation -and
    [string]::IsNullOrWhiteSpace($Archive)) {
    throw "$Operation requires -Archive."
}

$exitCode = 1
try {
    if ($requiresSource) {
        $env:MIGRATION_SOURCE_URL = Read-ConnectionUrl `
            "Paste the local portfolio_app PostgreSQL 18 URL (input is hidden)"
    }

    if ($requiresTarget) {
        Set-TargetIdentity
    }
    elseif ($Operation -eq "capacity") {
        $includeTarget = Read-Host "Include an explicitly isolated Neon migration database capacity check? (y/N)"
        if ($includeTarget -match "^(y|yes)$") {
            Set-TargetIdentity
        }
    }

    $arguments = @(
        "scripts/uv.mjs",
        "run",
        "--locked",
        "--project",
        "apps/api",
        "python",
        "-m",
        "portfolio_api.postgres_migration",
        $Operation
    )

    if ($Operation -eq "backup") {
        $arguments += @("--output", $Output)
    }
    if (@("verify-backup", "restore", "cutover-preflight") -contains $Operation) {
        $arguments += @("--archive", $Archive)
    }
    if ($Operation -eq "restore") {
        $confirmation = "RESTORE $($env:MIGRATION_EXPECTED_TARGET_HOST)/$($env:MIGRATION_EXPECTED_TARGET_DATABASE)"
        $typedConfirmation = Read-Host "Type exactly: $confirmation"
        $arguments += @("--confirm-target", $typedConfirmation)
    }
    if ($Report) {
        $arguments += @("--report", $Report)
    }

    Push-Location (Split-Path -Parent $PSScriptRoot)
    try {
        & node @arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    foreach ($name in $migrationEnvironmentNames) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    $script:TargetUrl = $null
}

exit $exitCode
