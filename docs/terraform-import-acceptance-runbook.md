# Terraform import acceptance run

Run this acceptance procedure only from the primary clone. It produces a read-only import plan;
phase 3 does not authorize applying it.

1. Create the ignored `terraform/backend.hcl` as described in the
   [Terraform state backend runbook](terraform-state-backend-runbook.md). Use that runbook's
   environment-variable loader for the R2 credentials, then initialize the remote backend:

   ```powershell
   terraform -chdir=terraform init -reconfigure -backend-config=backend.hcl
   ```

2. Put the real inventory in the ignored `terraform/terraform.tfvars`. `domains` is the required
   domain-to-zone-ID inventory, and each entry holds only `zone_id`; `security_overrides` is
   optional. Do not copy either into the repository or command history.

3. Set `CLOUDFLARE_API_TOKEN` in the current shell to a read-only token with `Zone:Read`,
   `Zone Settings:Read`, and `Bot Management:Read`, following
   [the Cloudflare API token runbook](cloudflare-api-token-runbook.md). Load it from a file without
   displaying it, as the backend runbook's loader does for the R2 keys.

4. Create the plan outside the repository. From the repository root:

   ```powershell
   terraform -chdir=terraform plan -var-file=terraform.tfvars -var import_existing_zones=true -out="$env:TEMP\cloudflare-import.tfplan"
   ```

   `-var-file=terraform.tfvars` is required. Terraform loads `ci.auto.tfvars` automatically after
   `terraform.tfvars`, so without it the mock inventory replaces the real one.

5. Accept the plan only when its summary reports exactly one import per zone setting in
   `policy/zone-security-standard.json` plus one bot management import, for every inventory zone
   (6 per zone with the current policy), and `0 to add, 0 to change, 0 to destroy`. Read only the aggregate counts; do not copy domain
   names or zone IDs into tickets, logs, or review material.

6. An update in this plan means the live zone differs from the configuration. It is not an import
   failure, and it is never applied as part of this phase. Resolve it according to its source:
   - A policy control, such as SSL mode or Bot Fight Mode, differs: add a `security_overrides` entry
     for that domain or make a reviewed policy decision.
   - A fixed zone-module value differs, such as `enable_js = true` for bot management:
     `security_overrides` can't change it. It needs a separately reviewed change to
     `terraform/modules/cloudflare_zone_config`.

7. Do not apply the saved plan. Phase 4 performs the first import apply. The plan file contains
   real zone identities and configuration: delete it once the counts are recorded, and clear
   `CLOUDFLARE_API_TOKEN` and the R2 keys from the shell.

8. After the acceptance run, never run a standalone plan with `ci.auto.tfvars`. Run
   `./scripts/run-terraform-mock-gate.ps1`, then run `init -reconfigure -backend-config=backend.hcl`
   again before any later remote Terraform work.
