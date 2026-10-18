$script:MigrationEnvironmentNames = @(
    "MIGRATION_SOURCE_URL",
    "MIGRATION_SOURCE_SCHEMA",
    "MIGRATION_TARGET_URL",
    "MIGRATION_TARGET_SCHEMA",
    "MIGRATION_EXPECTED_TARGET_HOST",
    "MIGRATION_EXPECTED_TARGET_DATABASE",
    "MIGRATION_NEON_API_KEY",
    "MIGRATION_NEON_PROJECT_ID",
    "MIGRATION_NEON_TARGET_BRANCH_ID",
    "MIGRATION_NEON_TARGET_ENDPOINT_ID",
    "MIGRATION_PRODUCTION_HOST",
    "MIGRATION_ALLOW_TEST_TARGET",
    "MIGRATION_PG_TOOLS_CONTAINER"
)

function Clear-MigrationEnvironment {
    foreach ($name in $script:MigrationEnvironmentNames) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
}

function Read-MigrationInput {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][bool]$Secret,
        [scriptblock]$InputProvider
    )

    if ($InputProvider) {
        $value = & $InputProvider $Prompt $Secret
        if ($Secret) {
            return ConvertTo-SecureString -String ([string]$value) -AsPlainText -Force
        }
        return [string]$value
    }
    if ($Secret) {
        return Read-Host -Prompt $Prompt -AsSecureString
    }
    return Read-Host -Prompt $Prompt
}

function Read-MigrationConnectionUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [scriptblock]$InputProvider
    )

    $secureValue = Read-MigrationInput -Prompt $Prompt -Secret $true -InputProvider $InputProvider
    $pointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $secureValue.Dispose()
    }
}

function New-MigrationArgumentList {
    param(
        [Parameter(Mandatory = $true)][string]$Operation,
        [string]$Archive,
        [string]$Output,
        [string]$Report,
        [string]$Confirmation
    )

    if ($Operation -eq "backup" -and [string]::IsNullOrWhiteSpace($Output)) {
        throw "Backup requires -Output pointing to a new private file outside the repository."
    }
    if (@("verify-backup", "restore", "cutover-preflight") -contains $Operation -and
        [string]::IsNullOrWhiteSpace($Archive)) {
        throw "$Operation requires -Archive."
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
        if ([string]::IsNullOrWhiteSpace($Confirmation)) {
            throw "Restore requires an exact live-target confirmation."
        }
        $arguments += @("--confirm-target", $Confirmation)
    }
    if (-not [string]::IsNullOrWhiteSpace($Report)) {
        $arguments += @("--report", $Report)
    }
    return ,$arguments
}

function Invoke-PostgresMigrationOperation {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet(
            "inventory", "capacity", "schema-check", "backup", "verify-backup",
            "restore", "reconcile", "cutover-preflight"
        )]
        [string]$Operation,
        [string]$Archive,
        [string]$Output,
        [string]$Report,
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [scriptblock]$InputProvider,
        [scriptblock]$NodeInvoker
    )

    $ErrorActionPreference = "Stop"
    Clear-MigrationEnvironment
    $script:TargetUrl = $null
    $exitCode = 1
    try {
        if ($Operation -eq "backup" -and [string]::IsNullOrWhiteSpace($Output)) {
            throw "Backup requires -Output pointing to a new private file outside the repository."
        }
        if (@("verify-backup", "restore", "cutover-preflight") -contains $Operation -and
            [string]::IsNullOrWhiteSpace($Archive)) {
            throw "$Operation requires -Archive."
        }

        $requiresSource = @("inventory", "capacity", "schema-check", "backup", "reconcile", "cutover-preflight") -contains $Operation
        $requiresTarget = @("schema-check", "restore", "reconcile", "cutover-preflight") -contains $Operation
        if ($requiresSource) {
            $env:MIGRATION_SOURCE_URL = Read-MigrationConnectionUrl `
                -Prompt "Paste the local portfolio_app PostgreSQL 18 URL (input is hidden)" `
                -InputProvider $InputProvider
        }

        $includeTarget = $requiresTarget
        if ($Operation -eq "capacity") {
            $includeTargetAnswer = Read-MigrationInput `
                -Prompt "Include an explicitly isolated Neon migration database capacity check? (y/N)" `
                -Secret $false -InputProvider $InputProvider
            $includeTarget = ([string]$includeTargetAnswer -match "^(y|yes)$")
        }
        if ($includeTarget) {
            $script:TargetUrl = Read-MigrationConnectionUrl `
                -Prompt "Paste the isolated Neon migration database URL (input is hidden)" `
                -InputProvider $InputProvider
            $env:MIGRATION_EXPECTED_TARGET_HOST = [string](Read-MigrationInput `
                -Prompt "Expected direct Neon hostname for this isolated migration database" `
                -Secret $false -InputProvider $InputProvider)
            $env:MIGRATION_EXPECTED_TARGET_DATABASE = [string](Read-MigrationInput `
                -Prompt "Expected database name; it must end in _migration" `
                -Secret $false -InputProvider $InputProvider)
            $env:MIGRATION_NEON_API_KEY = Read-MigrationConnectionUrl `
                -Prompt "Paste a Neon API key permitted to read project branch and endpoint metadata (input is hidden)" `
                -InputProvider $InputProvider
            $env:MIGRATION_NEON_PROJECT_ID = [string](Read-MigrationInput `
                -Prompt "Neon project ID" -Secret $false -InputProvider $InputProvider)
            $env:MIGRATION_NEON_TARGET_BRANCH_ID = [string](Read-MigrationInput `
                -Prompt "Neon isolated migration branch ID" -Secret $false -InputProvider $InputProvider)
            $env:MIGRATION_NEON_TARGET_ENDPOINT_ID = [string](Read-MigrationInput `
                -Prompt "Neon direct read-write endpoint ID on that branch" -Secret $false -InputProvider $InputProvider)
            $env:MIGRATION_TARGET_URL = $script:TargetUrl
        }

        $confirmation = $null
        if ($Operation -eq "restore") {
            $confirmationText = "RESTORE $($env:MIGRATION_EXPECTED_TARGET_HOST)/$($env:MIGRATION_EXPECTED_TARGET_DATABASE)"
            $confirmation = [string](Read-MigrationInput `
                -Prompt "Type exactly: $confirmationText" -Secret $false -InputProvider $InputProvider)
        }
        $arguments = New-MigrationArgumentList `
            -Operation $Operation -Archive $Archive -Output $Output -Report $Report `
            -Confirmation $confirmation

        Push-Location $RepositoryRoot
        try {
            if ($NodeInvoker) {
                & $NodeInvoker -Arguments $arguments | Out-Host
            }
            else {
                & node @arguments | Out-Host
            }
            if ($null -eq $LASTEXITCODE) {
                $exitCode = 1
            }
            else {
                $exitCode = [int]$LASTEXITCODE
            }
        }
        finally {
            Pop-Location
        }
    }
    catch {
        [Console]::Error.WriteLine([string]$_.Exception.Message)
        $exitCode = 1
    }
    finally {
        Clear-MigrationEnvironment
        $script:TargetUrl = $null
    }
    return $exitCode
}

Export-ModuleMember -Function @(
    "Clear-MigrationEnvironment",
    "New-MigrationArgumentList",
    "Invoke-PostgresMigrationOperation"
)
