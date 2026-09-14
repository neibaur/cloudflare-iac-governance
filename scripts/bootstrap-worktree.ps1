<#
.SYNOPSIS
    Provisions an agent worktree so a worker can run the repository quality gate.

.DESCRIPTION
    Git worktrees receive a clean checkout of tracked files only. Everything the ignore rules
    exclude -- the virtualenv and all secret material -- exists solely in the primary clone.
    This script rebuilds that local state inside a worktree.

    (Note: no line of this help block may start with a dot, or PowerShell 5.1 treats it as an
    unknown help keyword and silently discards the entire block.)

    By default it provisions the Python environment only. Secret material is never copied
    implicitly: each category of credential is opted into with its own switch, so pulling a
    given class of secret into a worktree is always a deliberate, narrow act.

    Secret categories:
      -WithCloudflareToken  the worktree .env (prefers the restricted agent token)
      -WithTfvars           real Terraform inputs
      -WithServiceAccount   the unscoped GCP private key (requires a second acknowledgement)

    Every file the script places is checked against 'git check-ignore' afterwards, so a
    misconfigured .gitignore is reported loudly instead of silently exposing a credential.

.PARAMETER WithCloudflareToken
    Provision the worktree '.env' containing the Cloudflare API token and account ID.

    Prefers '.env.agent' from the source clone, which should hold a read-only, narrowly scoped
    agent token. Falls back to the source clone's '.env' -- the operator's unrestricted token --
    only with a loud warning. The destination is always written as '.env' so existing code paths
    (python-dotenv, scripts, terraform wrappers) work unchanged.

    Only CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are copied from either file. Everything else
    in the operator's '.env', such as R2 state backend keys or the Google Sheet ID, stays in the
    primary clone.

    A second warning fires when '.env.agent' exists but carries the same CLOUDFLARE_API_TOKEN
    value as '.env', which happens when the agent file was created by copying the operator file.
    The separation then looks real but is not. Only the token value is compared, and only as a
    SHA-256 hash: the two files may differ in other keys and still share the credential, and the
    token value itself is never read into any output. Neither warning blocks the bootstrap.

.PARAMETER WithTfvars
    Copy 'terraform/terraform.tfvars' and 'terraform/secrets.auto.tfvars' from the source clone.
    Real Terraform inputs: needed only for tasks that plan against real managed infrastructure.

.PARAMETER WithServiceAccount
    Copy 'service_account.json' from the source clone.

    This is an unscoped GCP private key and the most dangerous item in the set. Because agent
    sessions are non-interactive, the script cannot prompt for confirmation; instead this switch
    does nothing on its own. You must ALSO pass -IAcceptServiceAccountRisk. Without it the copy
    is refused with an explanation and the rest of the bootstrap continues normally.

.PARAMETER IAcceptServiceAccountRisk
    Explicit acknowledgement that unlocks -WithServiceAccount. Has no effect on its own.

.PARAMETER WithSecrets
    DEPRECATED alias for '-WithCloudflareToken -WithTfvars'. Deliberately does NOT include the
    service account. Still works, but prints a deprecation notice naming the granular switches.

.PARAMETER SourceRepo
    Path to the primary clone to copy ignored files from. Defaults to the sibling
    'cloudflare-iac-governance' directory two levels up from a worktree.

.PARAMETER SkipVenv
    Skip virtualenv creation and dependency installation.

.PARAMETER Force
    Recreate the virtualenv even if one already exists, and overwrite existing secret files.

.EXAMPLE
    .\scripts\bootstrap-worktree.ps1

    Python environment and terraform init only. No credentials enter the worktree.

.EXAMPLE
    .\scripts\bootstrap-worktree.ps1 -WithCloudflareToken

    Adds the Cloudflare token .env, preferring the restricted agent token from '.env.agent'.

.EXAMPLE
    .\scripts\bootstrap-worktree.ps1 -WithCloudflareToken -WithTfvars

    The modern equivalent of the deprecated -WithSecrets bundle.

.EXAMPLE
    .\scripts\bootstrap-worktree.ps1 -WithServiceAccount -IAcceptServiceAccountRisk

    Copies the unscoped GCP private key. Only for tasks that genuinely need it.
#>
[CmdletBinding()]
param(
    [switch]$WithCloudflareToken,
    [switch]$WithTfvars,
    [switch]$WithServiceAccount,
    [switch]$IAcceptServiceAccountRisk,
    [switch]$WithSecrets,
    [string]$SourceRepo,
    [switch]$SkipVenv,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (git rev-parse --show-toplevel)
if (-not $RepoRoot) { throw "Not inside a git repository." }
# String.Replace, not the -replace operator: -replace treats its arguments as regex and
# regex replacement text, where a lone backslash is an escape character. A previous version
# of this script shipped that bug.
$RepoRoot = $RepoRoot.Replace('/', '\')
Set-Location $RepoRoot

Write-Host "Worktree : $RepoRoot" -ForegroundColor Cyan
Write-Host "Branch   : $(git rev-parse --abbrev-ref HEAD)" -ForegroundColor Cyan

# ---------------------------------------------------------------- resolve requested categories
$wantToken = [bool]$WithCloudflareToken
$wantTfvars = [bool]$WithTfvars
$wantServiceAccount = [bool]$WithServiceAccount

if ($WithSecrets) {
    Write-Host ""
    Write-Host "DEPRECATED: -WithSecrets is an all-or-nothing bundle." -ForegroundColor Yellow
    Write-Host "  Treating it as: -WithCloudflareToken -WithTfvars" -ForegroundColor Yellow
    Write-Host "  The service account is NOT included. Use -WithServiceAccount" -ForegroundColor Yellow
    Write-Host "  -IAcceptServiceAccountRisk if a task genuinely requires it." -ForegroundColor Yellow
    $wantToken = $true
    $wantTfvars = $true
}

if ($wantServiceAccount -and -not $IAcceptServiceAccountRisk) {
    Write-Host ""
    Write-Host "REFUSED: -WithServiceAccount requires -IAcceptServiceAccountRisk." -ForegroundColor Red
    Write-Host "  service_account.json is an unscoped GCP private key. It is not a read-only" -ForegroundColor Red
    Write-Host "  token and it cannot be narrowed per worktree, so any agent holding it holds" -ForegroundColor Red
    Write-Host "  the full rights of that service account." -ForegroundColor Red
    Write-Host "  This session is non-interactive, so the script cannot prompt. Re-run with" -ForegroundColor Red
    Write-Host "  -WithServiceAccount -IAcceptServiceAccountRisk if you accept that." -ForegroundColor Red
    Write-Host "  Continuing with the rest of the bootstrap." -ForegroundColor Red
    $wantServiceAccount = $false
}

$wantAnySecret = $wantToken -or $wantTfvars -or $wantServiceAccount

# ---------------------------------------------------------------- resolve source clone
if (-not $SourceRepo) {
    $candidate = Join-Path (Split-Path (Split-Path $RepoRoot -Parent) -Parent) 'cloudflare-iac-governance'
    if (Test-Path (Join-Path $candidate '.git')) { $SourceRepo = $candidate }
}

# ---------------------------------------------------------------- python environment
if (-not $SkipVenv) {
    $venv = Join-Path $RepoRoot '.venv'
    if ((Test-Path $venv) -and $Force) {
        Write-Host "Removing existing virtualenv..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $venv
    }
    if (Test-Path $venv) {
        Write-Host "Virtualenv already present. Use -Force to recreate." -ForegroundColor Yellow
    }
    else {
        Write-Host "Creating virtualenv..." -ForegroundColor Cyan
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create virtualenv." }
    }

    $py = Join-Path $venv 'Scripts\python.exe'
    Write-Host "Installing dev dependencies..." -ForegroundColor Cyan
    & $py -m pip install --upgrade pip --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $py -m pip install -r requirements-dev.txt --quiet
    if ($LASTEXITCODE -ne 0) { throw "Dependency install failed." }
    Write-Host "Python environment ready." -ForegroundColor Green
}

# ---------------------------------------------------------------- terraform init
if (Test-Path (Join-Path $RepoRoot 'terraform')) {
    Write-Host "Initializing Terraform (backend disabled)..." -ForegroundColor Cyan
    terraform -chdir=terraform init -backend=false -input=false | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Terraform init failed. Run it manually to see why." -ForegroundColor Yellow
    }
    else {
        Write-Host "Terraform initialized." -ForegroundColor Green
    }
}

# ---------------------------------------------------------------- secrets (granular opt-in)
# Destination-relative paths of everything this run placed in, or found already present in,
# the worktree. Consumed by the git check-ignore safety net below.
$script:TouchedPaths = @()

function Copy-SecretFile {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRelative,
        [Parameter(Mandatory = $true)][string]$DestinationRelative
    )

    $src = Join-Path $SourceRepo $SourceRelative
    $dst = Join-Path $RepoRoot $DestinationRelative

    if (-not (Test-Path $src)) {
        Write-Host "  skip    $SourceRelative (not present in source)" -ForegroundColor DarkGray
        return
    }
    if ((Test-Path $dst) -and -not $Force) {
        Write-Host "  exists  $DestinationRelative (use -Force to overwrite)" -ForegroundColor DarkGray
        $script:TouchedPaths += $DestinationRelative
        return
    }

    $parent = Split-Path $dst -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item -Path $src -Destination $dst -Force
    if ($SourceRelative -eq $DestinationRelative) {
        Write-Host "  copied  $DestinationRelative" -ForegroundColor Green
    }
    else {
        Write-Host "  copied  $SourceRelative -> $DestinationRelative" -ForegroundColor Green
    }
    $script:TouchedPaths += $DestinationRelative
}

# Returns the SHA-256 hex digest of one key's value in a dotenv-style file, or $null when the
# key is absent or empty. The value is never returned, printed, or logged -- only its digest,
# so callers can compare two files without either token entering the transcript.
#
# Parsing is deliberately literal: Trim, IndexOf, StartsWith and Substring only. The -match and
# -replace operators take regex, and a token is arbitrary text that may contain metacharacters.
# The only variables a worktree '.env' may receive. The operator '.env' also holds credentials that
# must never reach an agent, such as the R2 state backend keys.
$WorktreeEnvAllowlist = @('CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID')

# Splits an env file into allowlisted assignment lines and the names of every other variable.
function Split-EnvByAllowlist {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    $kept = New-Object System.Collections.Generic.List[string]
    $keptNames = New-Object System.Collections.Generic.List[string]
    $removedNames = New-Object System.Collections.Generic.List[string]
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith('export ')) { $trimmed = $trimmed.Substring(7).Trim() }
        $sep = $trimmed.IndexOf('=')
        if ($sep -lt 1 -or $trimmed.StartsWith('#')) { continue }
        $name = $trimmed.Substring(0, $sep).Trim()
        if ($WorktreeEnvAllowlist -contains $name) {
            $kept.Add($trimmed)
            $keptNames.Add($name)
        }
        else {
            $removedNames.Add($name)
        }
    }
    return [pscustomobject]@{ Kept = $kept; KeptNames = $keptNames; RemovedNames = $removedNames }
}

function Write-EnvLines([string]$Path, $Lines) {
    $content = if ($Lines.Count) { ($Lines -join "`n") + "`n" } else { '' }
    [System.IO.File]::WriteAllText($Path, $content, (New-Object System.Text.UTF8Encoding($false)))
}

function Copy-EnvAllowlist {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRelative
    )

    $src = Join-Path $SourceRepo $SourceRelative
    $dst = Join-Path $RepoRoot '.env'

    if (-not (Test-Path -LiteralPath $src)) {
        Write-Host "  skip    $SourceRelative (not present in source)" -ForegroundColor DarkGray
        return
    }
    if ((Test-Path -LiteralPath $dst) -and -not $Force) {
        # An existing .env is kept, but never with variables outside the allowlist. A worktree
        # bootstrapped before the allowlist existed may hold a full copy of the operator .env.
        $existing = Split-EnvByAllowlist -Path $dst
        if ($existing.RemovedNames.Count) {
            Write-EnvLines -Path $dst -Lines $existing.Kept
            Write-Host "  cleaned .env: removed $($existing.RemovedNames -join ', ') (not allowlisted)" -ForegroundColor Yellow
        }
        else {
            Write-Host "  exists  .env (use -Force to overwrite)" -ForegroundColor DarkGray
        }
        $script:TouchedPaths += '.env'
        return
    }

    $source = Split-EnvByAllowlist -Path $src
    Write-EnvLines -Path $dst -Lines $source.Kept
    $names = if ($source.KeptNames.Count) { $source.KeptNames -join ', ' } else { 'no allowlisted variables' }
    Write-Host "  copied  $SourceRelative -> .env ($names only)" -ForegroundColor Green
    $script:TouchedPaths += '.env'
}

function Get-EnvValueHash {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key
    )

    if (-not (Test-Path -LiteralPath $Path)) { return $null }

    $value = $null
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0) { continue }
        if ($trimmed.StartsWith('#')) { continue }
        if ($trimmed.StartsWith('export ')) { $trimmed = $trimmed.Substring(7).Trim() }

        $sep = $trimmed.IndexOf('=')
        if ($sep -lt 1) { continue }
        if (-not ($trimmed.Substring(0, $sep).Trim() -eq $Key)) { continue }

        $candidate = $trimmed.Substring($sep + 1).Trim()
        if ($candidate.Length -ge 2) {
            $first = $candidate.Substring(0, 1)
            $last = $candidate.Substring($candidate.Length - 1, 1)
            if (($first -eq $last) -and (($first -eq '"') -or ($first -eq "'"))) {
                $candidate = $candidate.Substring(1, $candidate.Length - 2)
            }
        }
        # Last assignment wins, matching how dotenv loaders resolve a repeated key.
        $value = $candidate
    }

    if (-not $value) { return $null }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($value))
    }
    finally {
        $sha.Dispose()
        $value = $null
    }

    $builder = New-Object System.Text.StringBuilder
    foreach ($b in $bytes) { [void]$builder.Append($b.ToString('x2')) }
    return $builder.ToString()
}

if ($wantAnySecret) {
    if (-not $SourceRepo -or -not (Test-Path $SourceRepo)) {
        throw "Cannot copy secrets: source clone not found. Pass -SourceRepo <path>."
    }

    Write-Host ""
    Write-Host "Copying secret material from: $SourceRepo" -ForegroundColor Yellow
    Write-Host "These files are gitignored. Consume them; never print or commit their contents." -ForegroundColor Yellow

    if ($wantToken) {
        $sourceAgentEnv = Join-Path $SourceRepo '.env.agent'
        $sourceOperatorEnv = Join-Path $SourceRepo '.env'

        if (Test-Path $sourceAgentEnv) {
            $agentTokenHash = Get-EnvValueHash -Path $sourceAgentEnv -Key 'CLOUDFLARE_API_TOKEN'
            $operatorTokenHash = Get-EnvValueHash -Path $sourceOperatorEnv -Key 'CLOUDFLARE_API_TOKEN'

            if ($agentTokenHash -and $operatorTokenHash -and ($agentTokenHash -eq $operatorTokenHash)) {
                $fingerprint = $agentTokenHash.Substring(0, 12)
                Write-Host ""
                Write-Host "WARNING: .env.agent and .env hold the SAME Cloudflare API token." -ForegroundColor Yellow
                Write-Host "  Both resolve to token sha256 $fingerprint (value not shown, never logged)." -ForegroundColor Yellow
                Write-Host "  The separation is nominal: this worktree gets exactly the Cloudflare" -ForegroundColor Yellow
                Write-Host "  rights the operator holds, not a narrowed subset. Today's token is" -ForegroundColor Yellow
                Write-Host "  read-only, so nothing is over-exposed yet -- but the day an" -ForegroundColor Yellow
                Write-Host "  edit-capable token is written to .env, every worktree bootstrapped" -ForegroundColor Yellow
                Write-Host "  this way silently inherits edit capability with no further signal." -ForegroundColor Yellow
                Write-Host "  Fix: mint a separate read-only, narrowly scoped agent token and put" -ForegroundColor Yellow
                Write-Host "  it in .env.agent so the two files stop sharing a credential." -ForegroundColor Yellow
                Write-Host "  Continuing with the bootstrap." -ForegroundColor Yellow
            }

            Copy-EnvAllowlist -SourceRelative '.env.agent'
        }
        elseif (Test-Path $sourceOperatorEnv) {
            Write-Host ""
            Write-Host "WARNING: no .env.agent in the source clone." -ForegroundColor Yellow
            Write-Host "  Falling back to .env, the operator's UNRESTRICTED Cloudflare token." -ForegroundColor Yellow
            Write-Host "  A read-only agent token in .env.agent is strongly preferred: it limits" -ForegroundColor Yellow
            Write-Host "  the blast radius of anything an agent does in this worktree." -ForegroundColor Yellow
            Copy-EnvAllowlist -SourceRelative '.env'
        }
        else {
            Write-Host "  skip    .env (neither .env.agent nor .env present in source)" -ForegroundColor DarkGray
        }
    }

    if ($wantTfvars) {
        Copy-SecretFile -SourceRelative 'terraform\terraform.tfvars' -DestinationRelative 'terraform\terraform.tfvars'
        Copy-SecretFile -SourceRelative 'terraform\secrets.auto.tfvars' -DestinationRelative 'terraform\secrets.auto.tfvars'
    }

    if ($wantServiceAccount) {
        Write-Host "  NOTE: placing an unscoped GCP private key in this worktree." -ForegroundColor Yellow
        Copy-SecretFile -SourceRelative 'service_account.json' -DestinationRelative 'service_account.json'
    }

    # Safety net: ask git directly whether each file we placed is ignored.
    # git check-ignore exits 0 when the path IS ignored, 1 when it is not.
    $placed = @($script:TouchedPaths | Select-Object -Unique)
    $leaks = @()
    foreach ($rel in $placed) {
        $dst = Join-Path $RepoRoot $rel
        if (-not (Test-Path $dst)) { continue }
        git check-ignore --quiet -- $rel
        if ($LASTEXITCODE -ne 0) { $leaks += $rel }
    }

    Write-Host ""
    if ($leaks.Count -gt 0) {
        Write-Host "WARNING: git does NOT ignore these secret files:" -ForegroundColor Red
        $leaks | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        Write-Host "Do not commit. Fix .gitignore before continuing." -ForegroundColor Red
    }
    elseif ($placed.Count -gt 0) {
        Write-Host "Verified: all copied secrets are ignored by git." -ForegroundColor Green
    }
    else {
        Write-Host "Nothing copied: no requested secret files exist in the source clone." -ForegroundColor DarkGray
    }
}
else {
    Write-Host ""
    Write-Host "No secrets copied. Opt in per category if the task spec requires it:" -ForegroundColor DarkGray
    Write-Host "  -WithCloudflareToken   .env (prefers the restricted .env.agent token)" -ForegroundColor DarkGray
    Write-Host "  -WithTfvars            terraform.tfvars / secrets.auto.tfvars" -ForegroundColor DarkGray
    Write-Host "  -WithServiceAccount    service_account.json (also needs -IAcceptServiceAccountRisk)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host "Quality gate: .venv\Scripts\python scripts/run_all_checks.py" -ForegroundColor Cyan
Write-Host "Protocol    : handoff/README.md" -ForegroundColor Cyan
