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
   domain-to-zone-ID inventory; `security_overrides` is optional. Do not copy either into the
   repository or command history.

3. Load a read-only Cloudflare API token with `Zone:Read`, `Zone Settings:Read`, and `Bot
   Management:Read`, following [the Cloudflare API token runbook](cloudflare-api-token-runbook.md).

4. Create the plan outside the repository. For example, from the repository root:

   ```powershell
   terraform -chdir=terraform plan -var import_existing_zones=true -out="$env:TEMP\cloudflare-import.tfplan"
   ```

5. Accept the plan only when its summary reports exactly `6 x <number of inventory zones>` imports
   and `0 to add, 0 to change, 0 to destroy`. Read only the aggregate counts; do not copy domain
   names or zone IDs into tickets, logs, or review material.

6. An update in this plan means the live zone differs from the policy or a fixed zone-module value,
   such as `enable_js = true` for bot management. It is not an import failure. Resolve it with a
   `security_overrides` entry or a reviewed policy decision; never apply it as part of this phase.

7. Do not apply the saved plan. Phase 4 performs the first import apply.

8. After the acceptance run, never run a standalone plan with `ci.auto.tfvars`. Run
   `./scripts/run-terraform-mock-gate.ps1`, then run `init -reconfigure -backend-config=backend.hcl`
   again before any later remote Terraform work.
