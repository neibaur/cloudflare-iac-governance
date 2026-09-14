<#
.SYNOPSIS
    Runs the R2 state-lock acceptance test against a disposable state key.

.DESCRIPTION
    Proves that Terraform's native S3 lockfile works against the operator's R2 bucket, without
    touching real state and without running terraform apply.

    The script copies terraform/backend.tf into a temporary directory, so it tests the committed
    backend settings, and adds a throwaway data source that holds the state lock for a set time.
    The state key is always lock-test/<random>/terraform.tfstate. It then checks that:

      1. terraform init connects to the bucket
      2. a second run is refused while the first holds the lock
      3. the lock is released when a run finishes normally
      4. a force-killed run leaves a stale lock
      5. terraform force-unlock clears that lock and a new run succeeds
      6. neither credential value appears in any output or in the .terraform directory

    Only PASS or FAIL lines are printed. Credential values, the bucket name, and the account ID are
    redacted from failure details.

    The script reads these values from the repository's .env file and never displays them:

      TF_STATE_ACCESS_KEY_ID      operator R2 access key ID
      TF_STATE_SECRET_ACCESS_KEY  operator R2 secret access key
      TF_STATE_BUCKET             state bucket name
      TF_STATE_ACCOUNT_ID         optional; defaults to CLOUDFLARE_ACCOUNT_ID

    It refuses to run from an agent worktree, because worktrees hold no credentials by design.

.PARAMETER HoldSeconds
    How long the lock holder keeps the lock. Increase it on slow connections. Default 40.

.EXAMPLE
    powershell -NoProfile -File .\scripts\test-r2-state-lock.ps1

.NOTES
    Windows only. Needs network access to the Terraform registry and the R2 endpoint. A passing
    run leaves no object in the bucket.
#>
[CmdletBinding()]
param(
    [ValidateRange(20, 600)]
    [int]$HoldSeconds = 40
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (git rev-parse --show-toplevel)
if (-not $RepoRoot) { throw "Not inside a git repository." }
$RepoRoot = $RepoRoot -replace '/', '\'

$gitDir = (git rev-parse --absolute-git-dir) -replace '/', '\'
$gitCommonDir = (git rev-parse --git-common-dir) -replace '/', '\'
if (-not [System.IO.Path]::IsPathRooted($gitCommonDir)) { $gitCommonDir = Join-Path $RepoRoot $gitCommonDir }
$gitCommonDir = [System.IO.Path]::GetFullPath($gitCommonDir)
if (($RepoRoot -match '\\worktrees\\') -or ($gitDir.TrimEnd('\') -ne $gitCommonDir.TrimEnd('\'))) {
    Write-Host "REFUSING TO RUN: this is an agent worktree. Run the lock test in the primary clone." -ForegroundColor Red
    exit 1
}

$envFile = Join-Path $RepoRoot '.env'
if (-not (Test-Path $envFile)) { Write-Output "FAIL: $envFile not found."; exit 1 }
$envValues = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
        $envValues[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}
$accountId = if ($envValues.TF_STATE_ACCOUNT_ID) { $envValues.TF_STATE_ACCOUNT_ID } else { $envValues.CLOUDFLARE_ACCOUNT_ID }
$missing = @('TF_STATE_ACCESS_KEY_ID', 'TF_STATE_SECRET_ACCESS_KEY', 'TF_STATE_BUCKET') | Where-Object { -not $envValues[$_] }
if (-not $accountId) { $missing += 'TF_STATE_ACCOUNT_ID or CLOUDFLARE_ACCOUNT_ID' }
if ($missing) { Write-Output "FAIL: missing from .env: $($missing -join ', ')"; exit 1 }

$redactions = [ordered]@{
    'access-key-id' = $envValues.TF_STATE_ACCESS_KEY_ID
    'secret-key'    = $envValues.TF_STATE_SECRET_ACCESS_KEY
    'account-id'    = $accountId
    'state-bucket'  = $envValues.TF_STATE_BUCKET
}
function Hide-Identity([string]$Text) {
    foreach ($name in $redactions.Keys) { $Text = $Text.Replace($redactions[$name], "<$name>") }
    return $Text
}

$runId = [guid]::NewGuid().ToString('N').Substring(0, 12)
$work = Join-Path ([System.IO.Path]::GetTempPath()) "r2-lock-test-$runId"
$savedEnv = @{}
foreach ($name in 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'CLOUDFLARE_API_TOKEN', 'TF_IN_AUTOMATION') {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$results = [ordered]@{}

function Invoke-Tf([string]$Name, [string[]]$Arguments, [switch]$NoWait) {
    $params = @{
        FilePath               = 'terraform'
        ArgumentList           = $Arguments
        NoNewWindow            = $true
        PassThru               = $true
        RedirectStandardOutput = "$work\$Name.out.log"
        RedirectStandardError  = "$work\$Name.err.log"
    }
    $process = Start-Process @params
    $null = $process.Handle  # Windows PowerShell 5.1 loses ExitCode unless the handle is cached.
    if (-not $NoWait) { $process.WaitForExit() }
    return $process
}
function Get-TfOutput([string]$Name) {
    return ((Get-Content "$work\$Name.out.log", "$work\$Name.err.log" -Raw -ErrorAction SilentlyContinue) -join "`n")
}
function Get-FailDetail([string]$Name) {
    $lines = (Get-TfOutput $Name) -split "`n" | Where-Object { $_ -match 'Error|denied|Forbidden|NoSuch|40[134]' } |
        Select-Object -First 5
    return Hide-Identity ($lines -join ' | ')
}
function Set-Result([string]$Check, [bool]$Passed, [string]$Name) {
    $results[$Check] = if ($Passed) { 'PASS' } elseif ($Name) { "FAIL: $(Get-FailDetail $Name)" } else { 'FAIL' }
    return $Passed
}

try {
    $env:AWS_ACCESS_KEY_ID = $envValues.TF_STATE_ACCESS_KEY_ID
    $env:AWS_SECRET_ACCESS_KEY = $envValues.TF_STATE_SECRET_ACCESS_KEY
    $env:TF_IN_AUTOMATION = '1'
    Remove-Item Env:CLOUDFLARE_API_TOKEN -ErrorAction SilentlyContinue

    New-Item -ItemType Directory $work | Out-Null
    Copy-Item (Join-Path $RepoRoot 'terraform\backend.tf') "$work\backend.tf"
    [IO.File]::WriteAllText("$work\hold.tf", @'
terraform {
  required_providers {
    external = {
      source  = "hashicorp/external"
      version = "~> 2.3"
    }
  }
}

variable "hold_seconds" {
  type    = number
  default = 0
}

# Holds the state lock for the plan's duration without creating any resource.
data "external" "hold" {
  program = ["powershell", "-NoProfile", "-Command", "Start-Sleep -Seconds ${var.hold_seconds}; '{}'"]
}
'@)
    [IO.File]::WriteAllText("$work\backend.hcl",
        "bucket = `"$($envValues.TF_STATE_BUCKET)`"`nkey    = `"lock-test/$runId/terraform.tfstate`"`n" +
        "endpoints = {`n  s3 = `"https://$accountId.r2.cloudflarestorage.com`"`n}`n")

    Push-Location $work
    $plan = @('plan', '-refresh=false', '-input=false', '-no-color', '-lock-timeout=0s')
    $settle = [Math]::Min(15, [int]($HoldSeconds / 2))

    $init = Invoke-Tf 'init' @('init', '-input=false', '-no-color', '-backend-config=backend.hcl')
    if (Set-Result 'init connects to the bucket' ($init.ExitCode -eq 0) 'init') {
        $first = Invoke-Tf 'first' $plan
        $null = Set-Result 'plan acquires and releases the lock' ($first.ExitCode -eq 0) 'first'
    }

    if ($results['plan acquires and releases the lock'] -eq 'PASS') {
        $holder = Invoke-Tf 'holder' ($plan + "-var=hold_seconds=$HoldSeconds") -NoWait
        Start-Sleep -Seconds $settle
        $contender = Invoke-Tf 'contender' $plan
        $holder.WaitForExit()
        $refused = ($contender.ExitCode -ne 0) -and ((Get-TfOutput 'contender') -match 'Error acquiring the state lock')
        $null = Set-Result 'second run refused while lock is held' $refused 'contender'
        $null = Set-Result 'lock holder finishes normally' ($holder.ExitCode -eq 0) 'holder'

        $released = Invoke-Tf 'released' $plan
        $null = Set-Result 'lock is free after normal release' ($released.ExitCode -eq 0) 'released'

        $victim = Invoke-Tf 'victim' ($plan + "-var=hold_seconds=$HoldSeconds") -NoWait
        Start-Sleep -Seconds $settle
        & taskkill.exe /T /F /PID $victim.Id | Out-Null
        Start-Sleep -Seconds 3
        $blocked = Invoke-Tf 'blocked' $plan
        $lockId = $null
        if ((Get-TfOutput 'blocked') -match '(?ms)Lock Info:.*?ID:\s+([0-9a-fA-F-]{36})') { $lockId = $Matches[1] }
        if (Set-Result 'killed run leaves a stale lock' (($blocked.ExitCode -ne 0) -and $lockId) 'blocked') {
            $unlock = Invoke-Tf 'unlock' @('force-unlock', '-force', '-no-color', $lockId)
            $null = Set-Result 'force-unlock clears the stale lock' ($unlock.ExitCode -eq 0) 'unlock'
            $recovered = Invoke-Tf 'recovered' $plan
            $null = Set-Result 'plan succeeds after recovery' ($recovered.ExitCode -eq 0) 'recovered'
        }
    }

    $logs = (Get-ChildItem $work -Filter *.log | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
    $dotTerraform = (Get-ChildItem "$work\.terraform" -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -lt 1MB } | ForEach-Object { Get-Content $_.FullName -Raw }) -join "`n"
    $leaked = foreach ($text in $logs, $dotTerraform) {
        $text.Contains($envValues.TF_STATE_ACCESS_KEY_ID) -or $text.Contains($envValues.TF_STATE_SECRET_ACCESS_KEY)
    }
    $null = Set-Result 'no credential in output or .terraform' (-not ($leaked -contains $true)) $null
}
finally {
    Pop-Location -ErrorAction SilentlyContinue
    foreach ($name in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
    if (Test-Path $work) { Remove-Item -Recurse -Force $work }
}

Write-Output "Terraform $((terraform version -json | ConvertFrom-Json).terraform_version)"
$results.GetEnumerator() | ForEach-Object { Write-Output ('{0,-42} {1}' -f $_.Key, $_.Value) }
$failed = @($results.Values | Where-Object { $_ -ne 'PASS' }).Count
# A failed early check skips later checks, so require every check to have run.
$expectedChecks = 9
if ($results.Count -lt $expectedChecks -or $failed -gt 0) {
    Write-Output 'RESULT: FAIL. Do not migrate state; see the runbook.'
    exit 1
}
Write-Output 'RESULT: PASS'
