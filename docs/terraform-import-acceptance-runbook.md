# Terraform import acceptance run

Run this acceptance procedure only from the primary clone, in one PowerShell window from the
repository root. It produces a read-only import plan; phase 3 does not authorize applying it.

Keep every Terraform argument quoted exactly as shown. Windows PowerShell splits an unquoted
argument such as `-var-file=terraform.tfvars` at the dot, and Terraform then fails with
`Too many command line arguments`.

1. Create the ignored `terraform/backend.hcl`, then load the R2 keys and initialize the remote
   backend, both as described under "Initialize the remote backend" in the
   [Terraform state backend runbook](terraform-state-backend-runbook.md). Its loader ends with:

   ```powershell
   terraform -chdir=terraform init -reconfigure "-backend-config=backend.hcl"
   ```

2. Put the real inventory in the ignored `terraform/terraform.tfvars`. `domains` is the required
   domain-to-zone-ID inventory, and each entry holds only `zone_id`; `security_overrides` is
   optional. Do not copy either into the repository or command history.

3. Load a read-only Cloudflare token with `Zone:Read`, `Zone Settings:Read`, and
   `Bot Management:Read` (see [the Cloudflare API token runbook](cloudflare-api-token-runbook.md))
   into the current shell without displaying it. This reads `CLOUDFLARE_API_TOKEN` from `.env`, so
   confirm first that the token stored there has no edit permission:

   ```powershell
   Remove-Item Env:CLOUDFLARE_API_TOKEN -ErrorAction SilentlyContinue
   foreach ($line in Get-Content .env) {
       if ($line -match '^\s*CLOUDFLARE_API_TOKEN\s*=\s*(.+?)\s*$') {
           $env:CLOUDFLARE_API_TOKEN = $Matches[1].Trim('"').Trim("'")
       }
   }
   if (-not $env:CLOUDFLARE_API_TOKEN) { throw '.env must define CLOUDFLARE_API_TOKEN.' }
   ```

4. Create the plan outside the repository. From the repository root:

   ```powershell
   terraform -chdir=terraform plan "-var-file=terraform.tfvars" "-var=import_existing_zones=true" "-out=$env:TEMP\cloudflare-import.tfplan"
   ```

   `-var-file=terraform.tfvars` is required. Terraform loads `ci.auto.tfvars` automatically after
   `terraform.tfvars`, so without it the mock inventory replaces the real one.

5. Confirm the plan command exited 0 with no `Error:` output. A failed validation or precondition
   still prints a plan summary and writes the plan file, so the exit code, not the summary, decides
   whether the plan succeeded.

6. Verify every import in the saved plan. From the repository root:

   ```powershell
   .venv\Scripts\python -m scripts.check_import_plan "$env:TEMP\cloudflare-import.tfplan"
   ```

   The checker runs `terraform show -json` on the plan and compares every import against the
   plan's own inventory and `policy/zone-security-standard.json`. Each zone must import exactly one
   resource per policy zone setting plus its bot management, at the expected module address and
   with its own zone ID, and the plan must change nothing else. Matching summary counts alone can't
   prove this: an import bound to the wrong address or zone still counts as one import.

   Accept the plan only when the checker prints `RESULT: PASS` and exits 0. It prints counts only,
   so its output is safe to record. Do not copy domain names or zone IDs from the plan into
   tickets, logs, or review material.

7. An update in this plan means the live zone differs from the configuration. It is not an import
   failure, and it is never applied as part of this phase. Resolve it according to its source:
   - A policy control, such as SSL mode or Bot Fight Mode, differs: add a `security_overrides` entry
     for that domain or make a reviewed policy decision.
   - A fixed zone-module value differs, such as `enable_js = true` for bot management:
     `security_overrides` can't change it. It needs a separately reviewed change to
     `terraform/modules/cloudflare_zone_config`.

8. Do not apply the saved plan. Phase 4 performs the first import apply. The plan file contains
   real zone identities and configuration: delete it once the checker result is recorded, and clear
   `CLOUDFLARE_API_TOKEN` and the R2 keys from the shell:

   ```powershell
   Remove-Item "$env:TEMP\cloudflare-import.tfplan"
   Remove-Item Env:CLOUDFLARE_API_TOKEN, Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY
   ```

9. After the acceptance run, never run a standalone plan with `ci.auto.tfvars`. Run
   `.\scripts\run-terraform-mock-gate.ps1`, then repeat step 1's remote initialization before any
   later remote Terraform work.
