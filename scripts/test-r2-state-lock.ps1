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
      7. cleanup confirms no lock remains on the disposable key

    Only PASS or FAIL lines are printed. Credential values, the bucket name, and the account ID are
    redacted from failure details.

    The script reads these values from the repository's .env file and never displays them:

      TF_STATE_ACCESS_KEY_ID      operator R2 access key ID
      TF_STATE_SECRET_ACCESS_KEY  operator R2 secret access key
      TF_STATE_BUCKET             state bucket name
      TF_STATE_ACCOUNT_ID         optional; defaults to CLOUDFLARE_ACCOUNT_ID

    It refuses to run from an agent worktree, because worktrees hold no credentials by design.

.PARAMETER HoldSeconds
    How long each lock holder keeps the lock after acquiring it. Default 40.

.PARAMETER AcquireTimeoutSeconds
    How long to wait for a lock holder to acquire the lock before failing. Increase it on slow
    connections. Default 180.

.EXAMPLE
    powershell -NoProfile -File .\scripts\test-r2-state-lock.ps1

.NOTES
    Windows only. Needs network access to the Terraform registry and the R2 endpoint. A passing
    run leaves no object in the bucket. When the script exits, even on failure or Ctrl+C, it stops
    its Terraform processes and clears any lock left on its disposable key. The script prints its run
    ID when it starts. If the window is closed or the process is killed, delete only
    lock-test/<run ID>/ in the R2 dashboard: another operator's test may be using a different run
    ID under lock-test/ at the same time.
#>
[CmdletBinding()]
param(
    [ValidateRange(20, 600)]
    [int]$HoldSeconds = 40,

    [ValidateRange(30, 1800)]
    [int]$AcquireTimeoutSeconds = 180
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
# Printed first so the operator knows which prefix to clean up if the process is killed.
Write-Output "Run ID: $runId (disposable key lock-test/$runId/terraform.tfstate)"
$work = Join-Path ([System.IO.Path]::GetTempPath()) "r2-lock-test-$runId"
$savedEnv = @{}
# TF_DATA_DIR, TF_WORKSPACE, and TF_CLI_ARGS* are cleared too: inherited values could send init or plan to
# another checkout's .terraform directory or inject arguments.
$terraformEnv = @('TF_DATA_DIR', 'TF_WORKSPACE', 'TF_CLI_ARGS', 'TF_CLI_ARGS_init', 'TF_CLI_ARGS_plan')
foreach ($name in @('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'CLOUDFLARE_API_TOKEN', 'TF_IN_AUTOMATION') + $terraformEnv) {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$results = [ordered]@{}
$started = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$initialized = $false
$pushed = $false

function Invoke-Tf([string]$Name, [string[]]$Arguments, [switch]$NoWait) {
    # Windows PowerShell 5.1 joins ArgumentList with spaces and doesn't quote, so quote any argument
    # that contains whitespace or a double quote, such as a temp path under a profile with a space.
    $quoted = foreach ($argument in $Arguments) {
        if ($argument -match '[\s"]') { '"' + ($argument -replace '"', '\"') + '"' } else { $argument }
    }
    $params = @{
        FilePath               = 'terraform'
        ArgumentList           = $quoted
        NoNewWindow            = $true
        PassThru               = $true
        RedirectStandardOutput = "$work\$Name.out.log"
        RedirectStandardError  = "$work\$Name.err.log"
    }
    $process = Start-Process @params
    $null = $process.Handle  # Windows PowerShell 5.1 loses ExitCode unless the handle is cached.
    $started.Add($process)
    if (-not $NoWait) { $process.WaitForExit() }
    return $process
}
function Stop-TfProcess([System.Diagnostics.Process]$Process) {
    if (-not $Process.HasExited) { & taskkill.exe /T /F /PID $Process.Id 2>$null | Out-Null }
    $Process.WaitForExit()
}
# The data source writes the marker only after Terraform holds the state lock, so waiting for it
# replaces a fixed delay.
function Wait-LockHeld([System.Diagnostics.Process]$Process, [string]$Marker) {
    $deadline = (Get-Date).AddSeconds($AcquireTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $Marker) { return $true }
        if ($Process.HasExited) { return $false }
        Start-Sleep -Milliseconds 250
    }
    return $false
}
function Get-LockId([string]$Name) {
    if ((Get-TfOutput $Name) -match '(?ms)Lock Info:.*?ID:\s+([0-9a-fA-F-]{36})') { return $Matches[1] }
    return $null
}
function Get-TfOutput([string]$Name) {
    return ((Get-Content "$work\$Name.out.log", "$work\$Name.err.log" -Raw -ErrorAction SilentlyContinue) -join "`n")
}
function Get-FailDetail([string]$Name) {
    $allLines = (Get-TfOutput $Name) -split "`n" | Where-Object { $_.Trim() }
    $lines = $allLines | Where-Object { $_ -match 'Error|denied|Forbidden|NoSuch|40[134]' } | Select-Object -First 5
    if (-not $lines) { $lines = $allLines | Select-Object -Last 3 }
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
    # An inherited AWS session token would be sent with the R2 keys and fail authentication.
    Remove-Item Env:AWS_SESSION_TOKEN, Env:CLOUDFLARE_API_TOKEN -ErrorAction SilentlyContinue
    foreach ($name in $terraformEnv) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }

    New-Item -ItemType Directory $work | Out-Null
    Copy-Item (Join-Path $RepoRoot 'terraform\backend.tf') "$work\backend.tf"
    [IO.File]::WriteAllText("$work\hold.tf", @'
terraform {
  required_providers {
    external = {
      source  = "hashicorp/external"
      version = "= 2.4.2"
    }
  }
}

variable "hold_seconds" {
  type    = number
  default = 0
}

variable "marker_path" {
  type    = string
  default = ""
}

# Runs during the plan, after the state lock is acquired: writes an optional marker, then holds the
# lock for hold_seconds without creating any resource. Doubling apostrophes makes the path a valid
# PowerShell single-quoted literal.
data "external" "hold" {
  program = [
    "powershell", "-NoProfile", "-Command",
    "$marker = '${replace(var.marker_path, "'", "''")}'; if ($marker) { New-Item -ItemType File -Force -Path $marker | Out-Null }; Start-Sleep -Seconds ${var.hold_seconds}; '{}'",
  ]
}
'@)
    [IO.File]::WriteAllText("$work\backend.hcl",
        "bucket = `"$($envValues.TF_STATE_BUCKET)`"`nkey    = `"lock-test/$runId/terraform.tfstate`"`n" +
        "endpoints = {`n  s3 = `"https://$accountId.r2.cloudflarestorage.com`"`n}`n")

    Push-Location $work
    $pushed = $true
    $plan = @('plan', '-refresh=false', '-input=false', '-no-color', '-lock-timeout=0s')

    $init = Invoke-Tf 'init' @('init', '-input=false', '-no-color', '-backend-config=backend.hcl')
    if (Set-Result 'init connects to the bucket' ($init.ExitCode -eq 0) 'init') {
        $initialized = $true
        $first = Invoke-Tf 'first' $plan
        $null = Set-Result 'plan acquires and releases the lock' ($first.ExitCode -eq 0) 'first'
    }

    if ($results['plan acquires and releases the lock'] -eq 'PASS') {
        $holderMarker = (Join-Path $work 'holder.marker').Replace('\', '/')
        $holder = Invoke-Tf 'holder' ($plan + "-var=hold_seconds=$HoldSeconds" + "-var=marker_path=$holderMarker") -NoWait
        if (Wait-LockHeld $holder $holderMarker) {
            $contender = Invoke-Tf 'contender' $plan
            $refused = ($contender.ExitCode -ne 0) -and ((Get-TfOutput 'contender') -match 'Error acquiring the state lock')
            $null = Set-Result 'second run refused while lock is held' $refused 'contender'
        }
        else {
            $results['second run refused while lock is held'] = "FAIL: holder did not acquire the lock within $AcquireTimeoutSeconds seconds. $(Get-FailDetail 'holder')"
            Stop-TfProcess $holder
        }
        $holder.WaitForExit()
        $null = Set-Result 'lock holder finishes normally' ($holder.ExitCode -eq 0) 'holder'

        $released = Invoke-Tf 'released' $plan
        $null = Set-Result 'lock is free after normal release' ($released.ExitCode -eq 0) 'released'

        $victimMarker = (Join-Path $work 'victim.marker').Replace('\', '/')
        $victim = Invoke-Tf 'victim' ($plan + "-var=hold_seconds=$HoldSeconds" + "-var=marker_path=$victimMarker") -NoWait
        $victimHeld = Wait-LockHeld $victim $victimMarker
        Stop-TfProcess $victim
        $blocked = Invoke-Tf 'blocked' $plan
        $lockId = Get-LockId 'blocked'
        if (Set-Result 'killed run leaves a stale lock' ($victimHeld -and ($blocked.ExitCode -ne 0) -and $lockId) 'blocked') {
            $unlock = Invoke-Tf 'unlock' @('force-unlock', '-force', '-no-color', $lockId)
            $null = Set-Result 'force-unlock clears the stale lock' ($unlock.ExitCode -eq 0) 'unlock'
            $recovered = Invoke-Tf 'recovered' $plan
            $null = Set-Result 'plan succeeds after recovery' ($recovered.ExitCode -eq 0) 'recovered'
        }
    }
}
finally {
    # Stop any Terraform run still in flight, then clear a lock it may have left on the disposable
    # key, so an interrupted or failed test doesn't leave a .tflock object in the bucket.
    foreach ($process in @($started)) { Stop-TfProcess $process }
    if ($initialized) {
        $probe = Invoke-Tf 'cleanup-probe' $plan
        $lockClear = $probe.ExitCode -eq 0
        if (-not $lockClear) {
            $staleLockId = Get-LockId 'cleanup-probe'
            if ($staleLockId) {
                $unlock = Invoke-Tf 'cleanup-unlock' @('force-unlock', '-force', '-no-color', $staleLockId)
                $lockClear = $unlock.ExitCode -eq 0
            }
        }
        # Cleanup is part of the result: a run that can't confirm the lock is gone doesn't pass.
        $results['disposable lock cleaned up'] = if ($lockClear) { 'PASS' } else { "FAIL: $(Get-FailDetail 'cleanup-probe')" }
        if (-not $lockClear) {
            Write-Host "WARNING: could not confirm the disposable lock is clear. Delete lock-test/$runId/ in the R2 dashboard." -ForegroundColor Yellow
        }
    }
    # Scan after cleanup, so the cleanup commands' logs and .terraform writes are covered too.
    if (Test-Path $work) {
        $latin1 = [System.Text.Encoding]::GetEncoding(28591)
        $leaked = foreach ($file in Get-ChildItem $work -Recurse -File -Force) {
            $text = $latin1.GetString([System.IO.File]::ReadAllBytes($file.FullName))
            $text.Contains($envValues.TF_STATE_ACCESS_KEY_ID) -or $text.Contains($envValues.TF_STATE_SECRET_ACCESS_KEY)
        }
        $null = Set-Result 'no credential in output or .terraform' (-not ($leaked -contains $true)) $null
    }
    if ($pushed) { Pop-Location }
    foreach ($name in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnv[$name], 'Process') }
    if (Test-Path $work) { Remove-Item -Recurse -Force $work }
}

Write-Output "Terraform $((terraform version -json | ConvertFrom-Json).terraform_version)"
$results.GetEnumerator() | ForEach-Object { Write-Output ('{0,-42} {1}' -f $_.Key, $_.Value) }
$failed = @($results.Values | Where-Object { $_ -ne 'PASS' }).Count
# A failed early check skips later checks, so require every check to have run.
$expectedChecks = 10
if ($results.Count -lt $expectedChecks -or $failed -gt 0) {
    Write-Output 'RESULT: FAIL. Do not migrate state; see the runbook.'
    exit 1
}
Write-Output 'RESULT: PASS'
