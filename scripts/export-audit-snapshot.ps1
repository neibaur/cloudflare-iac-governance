<#
.SYNOPSIS
    Exports a sanitized Cloudflare audit snapshot for an agent to analyze without credentials.

.DESCRIPTION
    Agents work with zero credentials by default. When a worker needs real audit data, the
    operator runs this script in the PRIMARY clone -- where the credentials already live -- and
    hands the worker the OUTPUT instead of the token.

    The script runs the existing read-only audit path (python run_tools.py --audit), sanitizes
    the resulting CSV, and writes it to ../handoff-live/inbox/ with a timestamped name.

    Sanitizing removes CLOUDFLARE_ACCOUNT_ID and anything token-shaped. Zone IDs and domain names
    are deliberately KEPT -- they are the point of the export. That makes a snapshot real
    infrastructure data: it belongs in handoff-live only and must never be committed.

    The script refuses to run from an agent worktree. Worktrees have no credentials by design and
    acquiring them there defeats the whole arrangement.

.PARAMETER DryRun
    Show what would be produced without calling the Cloudflare API and without writing a snapshot.

.PARAMETER OutputDir
    Directory to write the snapshot into. Defaults to ../handoff-live/inbox relative to the
    repository root.

.PARAMETER Label
    Optional short slug appended to the snapshot filename, e.g. the task ID it was brokered for.

.EXAMPLE
    .\scripts\export-audit-snapshot.ps1 -DryRun

    Show the resolved paths and the command that would run. Makes no API call.

.EXAMPLE
    .\scripts\export-audit-snapshot.ps1 -Label 20260912-ssl-drift

    Run the audit and write ../handoff-live/inbox/audit-snapshot-<UTC>-20260912-ssl-drift.csv

.NOTES
    Never paste a snapshot into a commit, a PR, an issue, or chat. It is real infrastructure data.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$OutputDir,
    [string]$Label
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- locate repo
$RepoRoot = (git rev-parse --show-toplevel)
if (-not $RepoRoot) { throw "Not inside a git repository." }
$RepoRoot = $RepoRoot -replace '/', '\'

# ---------------------------------------------------------------- guard: primary clone only
$isWorktreePath = $RepoRoot -match '\\worktrees\\'

$gitDir = (git rev-parse --absolute-git-dir) -replace '/', '\'
$gitCommonDir = (git rev-parse --git-common-dir) -replace '/', '\'
$isLinkedWorktree = $false
if ($gitDir -and $gitCommonDir) {
    $resolvedCommon = $gitCommonDir
    if (-not [System.IO.Path]::IsPathRooted($resolvedCommon)) {
        $resolvedCommon = Join-Path $RepoRoot $resolvedCommon
    }
    $resolvedCommon = [System.IO.Path]::GetFullPath($resolvedCommon)
    $isLinkedWorktree = ($gitDir.TrimEnd('\') -ne $resolvedCommon.TrimEnd('\'))
}

if ($isWorktreePath -or $isLinkedWorktree) {
    Write-Host ""
    Write-Host "REFUSING TO RUN: this is an agent worktree, not the primary clone." -ForegroundColor Red
    Write-Host "  Path          : $RepoRoot"
    Write-Host "  Worktree by   : path=$isWorktreePath gitdir=$isLinkedWorktree"
    Write-Host ""
    Write-Host "Agent worktrees hold no credentials on purpose. This script is the operator half" -ForegroundColor Yellow
    Write-Host "of the credential-brokering workflow: run it in the primary clone, then hand the" -ForegroundColor Yellow
    Write-Host "sanitized snapshot to the worker. Do not copy .env into a worktree to make this" -ForegroundColor Yellow
    Write-Host "run -- that is the exact thing the workflow exists to avoid." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "See handoff/README.md, section 'Credential brokering'."
    throw "export-audit-snapshot.ps1 must run in the primary clone."
}

$envFile = Join-Path $RepoRoot '.env'
if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "REFUSING TO RUN: no .env found at the repository root." -ForegroundColor Red
    Write-Host "  Expected      : $envFile"
    Write-Host ""
    Write-Host "The audit path needs CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID. If this IS" -ForegroundColor Yellow
    Write-Host "the primary clone, populate .env from the documented variables first. If it is" -ForegroundColor Yellow
    Write-Host "not, you are in the wrong directory -- do not create credentials here." -ForegroundColor Yellow
    Write-Host ""
    throw "export-audit-snapshot.ps1 requires a credentialed primary clone."
}

# ---------------------------------------------------------------- resolve paths
if (-not $OutputDir) {
    $OutputDir = Join-Path (Split-Path $RepoRoot -Parent) 'handoff-live\inbox'
}

$timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$snapshotName = "audit-snapshot-$timestamp"
if ($Label) {
    $safeLabel = ($Label -replace '[^A-Za-z0-9._-]', '-')
    $snapshotName = "$snapshotName-$safeLabel"
}
$snapshotPath = Join-Path $OutputDir "$snapshotName.csv"

$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

$sourceCsv = Join-Path $RepoRoot 'reports\security_compliance_report.csv'

Write-Host ""
Write-Host "Cloudflare audit snapshot export" -ForegroundColor Cyan
Write-Host "  Repo root     : $RepoRoot"
Write-Host "  Command       : $python run_tools.py --audit"
Write-Host "  Source CSV    : $sourceCsv"
Write-Host "  Snapshot      : $snapshotPath"
Write-Host "  Redacts       : CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, token-shaped strings"
Write-Host "  Keeps         : domain names, zone IDs, security settings, compliance flag"
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN: no Cloudflare API call made, no snapshot written." -ForegroundColor Yellow
    Write-Host "Re-run without -DryRun to produce the snapshot above." -ForegroundColor Yellow
    Write-Host ""
    return
}

# ---------------------------------------------------------------- collect redaction needles
# Secret values are read from .env only so they can be matched and removed. They are never
# printed, logged, or written anywhere.
$needles = @{}
foreach ($line in (Get-Content $envFile)) {
    $trimmed = $line.Trim()
    if ($trimmed -eq '') { continue }
    if ($trimmed.StartsWith('#')) { continue }
    $split = $trimmed.IndexOf('=')
    if ($split -lt 1) { continue }
    $key = $trimmed.Substring(0, $split).Trim()
    $value = $trimmed.Substring($split + 1).Trim().Trim('"').Trim("'")
    if ($value.Length -lt 8) { continue }
    if ($key -match 'TOKEN|SECRET|KEY|PASSWORD|ACCOUNT_ID') {
        $needles[$value] = "[REDACTED:$key]"
    }
}

# ---------------------------------------------------------------- run the read-only audit
Write-Host "Running read-only audit..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & $python run_tools.py --audit
    $auditExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($auditExit -ne 0) { throw "run_tools.py --audit failed with exit code $auditExit." }
if (-not (Test-Path $sourceCsv)) { throw "Audit reported success but $sourceCsv was not written." }

# ---------------------------------------------------------------- sanitize
$content = Get-Content $sourceCsv
$redactionHits = 0
$sanitized = foreach ($line in $content) {
    $out = $line
    foreach ($needle in $needles.Keys) {
        if ($out.Contains($needle)) {
            $out = $out.Replace($needle, $needles[$needle])
            $redactionHits = $redactionHits + 1
        }
    }
    # Catch-all for token-shaped strings. A 32-hex zone ID is shorter than this and survives.
    if ($out -match '[A-Za-z0-9_-]{40,}') {
        $out = $out -replace '[A-Za-z0-9_-]{40,}', '[REDACTED:TOKEN-SHAPED]'
        $redactionHits = $redactionHits + 1
    }
    $out
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
Set-Content -Path $snapshotPath -Value $sanitized -Encoding UTF8

# ---------------------------------------------------------------- report
$rowCount = 0
if ($sanitized.Count -gt 1) { $rowCount = $sanitized.Count - 1 }

Write-Host ""
Write-Host "Snapshot written: $snapshotPath" -ForegroundColor Green
Write-Host "  Data rows     : $rowCount"
Write-Host "  Redactions    : $redactionHits"
Write-Host ""
Write-Host "THIS FILE CONTAINS REAL INFRASTRUCTURE IDENTIFIERS." -ForegroundColor Yellow
Write-Host "Real domain names and real zone IDs are present by design -- they are what the worker" -ForegroundColor Yellow
Write-Host "needs. Credentials are not. Keep it in handoff-live/, which sits outside the" -ForegroundColor Yellow
Write-Host "repository and is untracked. Never commit it, never paste it into a PR, an issue," -ForegroundColor Yellow
Write-Host "or chat." -ForegroundColor Yellow
Write-Host ""
