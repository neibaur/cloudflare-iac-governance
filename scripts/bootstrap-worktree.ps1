<#
.SYNOPSIS
    Provisions an agent worktree so a worker can run the repository quality gate.

.DESCRIPTION
    Git worktrees receive a clean checkout of tracked files only. Everything ignored by
    .gitignore -- the virtualenv and all secret material -- exists solely in the primary clone.
    This script rebuilds that local state inside a worktree.

    By default it provisions the Python environment only. Secret material is copied in ONLY when
    -WithSecrets is passed, so pulling credentials into a worktree is always a deliberate act.

.PARAMETER WithSecrets
    Copy .env, service_account.json, and terraform/terraform.tfvars from the primary clone.
    Use only when the task spec states that real credentials or real Terraform inputs are needed.

.PARAMETER SourceRepo
    Path to the primary clone to copy ignored files from. Defaults to the sibling
    'cloudflare-iac-governance' directory two levels up from a worktree.

.PARAMETER SkipVenv
    Skip virtualenv creation and dependency installation.

.PARAMETER Force
    Recreate the virtualenv even if one already exists, and overwrite existing secret files.

.EXAMPLE
    .\scripts\bootstrap-worktree.ps1
    .\scripts\bootstrap-worktree.ps1 -WithSecrets
#>
[CmdletBinding()]
param(
    [switch]$WithSecrets,
    [string]$SourceRepo,
    [switch]$SkipVenv,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (git rev-parse --show-toplevel)
if (-not $RepoRoot) { throw "Not inside a git repository." }
$RepoRoot = $RepoRoot -replace '/', '\'
Set-Location $RepoRoot

Write-Host "Worktree : $RepoRoot" -ForegroundColor Cyan
Write-Host "Branch   : $(git rev-parse --abbrev-ref HEAD)" -ForegroundColor Cyan

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

# ---------------------------------------------------------------- secrets (opt-in)
if ($WithSecrets) {
    if (-not $SourceRepo -or -not (Test-Path $SourceRepo)) {
        throw "Cannot copy secrets: source clone not found. Pass -SourceRepo <path>."
    }

    Write-Host ""
    Write-Host "Copying secret material from: $SourceRepo" -ForegroundColor Yellow
    Write-Host "These files are gitignored. Consume them; never print or commit their contents." -ForegroundColor Yellow

    $secretFiles = @(
        '.env',
        'service_account.json',
        'terraform\terraform.tfvars',
        'terraform\secrets.auto.tfvars'
    )

    foreach ($rel in $secretFiles) {
        $src = Join-Path $SourceRepo $rel
        $dst = Join-Path $RepoRoot $rel
        if (-not (Test-Path $src)) {
            Write-Host "  skip    $rel (not present in source)" -ForegroundColor DarkGray
            continue
        }
        if ((Test-Path $dst) -and -not $Force) {
            Write-Host "  exists  $rel (use -Force to overwrite)" -ForegroundColor DarkGray
            continue
        }
        $parent = Split-Path $dst -Parent
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item -Path $src -Destination $dst -Force
        Write-Host "  copied  $rel" -ForegroundColor Green
    }

    # Safety net: ask git directly whether each copied file is ignored.
    # git check-ignore exits 0 when the path IS ignored, 1 when it is not.
    $leaks = @()
    foreach ($rel in $secretFiles) {
        $dst = Join-Path $RepoRoot $rel
        if (-not (Test-Path $dst)) { continue }
        git check-ignore --quiet -- $rel
        if ($LASTEXITCODE -ne 0) { $leaks += $rel }
    }
    if ($leaks.Count -gt 0) {
        Write-Host ""
        Write-Host "WARNING: git does NOT ignore these secret files:" -ForegroundColor Red
        $leaks | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        Write-Host "Do not commit. Fix .gitignore before continuing." -ForegroundColor Red
    }
    else {
        Write-Host "Verified: all copied secrets are ignored by git." -ForegroundColor Green
    }
}
else {
    Write-Host ""
    Write-Host "No secrets copied. Re-run with -WithSecrets if the task spec requires them." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host "Quality gate: .venv\Scripts\python scripts/run_all_checks.py" -ForegroundColor Cyan
Write-Host "Protocol    : handoff/README.md" -ForegroundColor Cyan
