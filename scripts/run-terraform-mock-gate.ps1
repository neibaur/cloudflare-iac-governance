<#
.SYNOPSIS
    Runs the Terraform mock validation gate: fmt, validate, test, and the ci.auto.tfvars plan.

.DESCRIPTION
    The committed terraform/backend.tf is a partial R2 backend, so the gate first writes an ignored
    terraform/ci_backend_override.tf that selects the local backend. The gate never contacts R2 and
    never needs credentials.

    Steps, each of which stops the gate on failure:

      1. refuse to run if any terraform/terraform.tfstate* file exists
      2. terraform fmt -check -recursive
      3. write the local-backend override
      4. terraform init -backend=false, validate, test
      5. terraform init -reconfigure, then check again for state
      6. terraform plan -refresh=false -input=false -var-file=ci.auto.tfvars

    The override is removed on every exit, including failure. The script exits 1 if any step fails.
    CI runs the same steps in .github/workflows/quality.yml.

.EXAMPLE
    .\scripts\run-terraform-mock-gate.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$terraformDir = Join-Path $RepoRoot 'terraform'
$override = Join-Path $terraformDir 'ci_backend_override.tf'

function Assert-NoState {
    if (Test-Path (Join-Path $terraformDir 'terraform.tfstate*')) {
        throw 'Terraform state found in terraform/. Mock inputs must never be planned against real state.'
    }
}

function Invoke-Terraform([string[]]$Arguments) {
    Write-Host "terraform $($Arguments -join ' ')" -ForegroundColor Cyan
    & terraform "-chdir=$terraformDir" @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "terraform $($Arguments[0]) failed with exit code $LASTEXITCODE."
    }
}

try {
    Assert-NoState
    Invoke-Terraform @('fmt', '-check', '-recursive')

    [System.IO.File]::WriteAllText($override, "terraform {`n  backend `"local`" {}`n}`n", [System.Text.Encoding]::ASCII)
    Invoke-Terraform @('init', '-backend=false', '-input=false')
    Invoke-Terraform @('validate')
    Invoke-Terraform @('test')
    Invoke-Terraform @('init', '-reconfigure', '-input=false')

    Assert-NoState
    Invoke-Terraform @('plan', '-refresh=false', '-input=false', '-var-file=ci.auto.tfvars')
}
catch {
    Write-Host "MOCK GATE FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Remove-Item -LiteralPath $override -ErrorAction SilentlyContinue
}

Write-Host 'Terraform mock gate passed.' -ForegroundColor Green
