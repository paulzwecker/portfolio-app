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
Import-Module (Join-Path $PSScriptRoot "PostgresMigration.psm1") -Force -ErrorAction Stop
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$exitCode = Invoke-PostgresMigrationOperation `
    -Operation $Operation -Archive $Archive -Output $Output -Report $Report `
    -RepositoryRoot $repositoryRoot
exit [int]$exitCode
