# Terraform R2 State Backend Runbook

This runbook covers four things for Terraform state in Cloudflare R2: setting up the bucket and
credentials, initializing the backend, proving that locking works, and recovery. It does not migrate
state or authorize `terraform apply`.

## How the backend fits together

Terraform stores its state as one object in an R2 bucket and uses the S3 backend, because R2 is
S3-compatible. With `use_lockfile = true`, Terraform writes a `.tflock` object next to the state
before any operation and deletes it afterwards. A second run that finds the lock is refused. Native
lockfiles need Terraform 1.10 or later, and this repository pins 1.15.
([HashiCorp S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3))

`terraform/backend.tf` commits only the R2 compatibility settings.
([Cloudflare R2 Terraform backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/))
The bucket, the state key, and the account-specific endpoint come from an ignored `backend.hcl`.
Credentials come only from environment variables.

## Create the bucket and credentials

1. In the Cloudflare dashboard, open **R2 object storage** and create one dedicated bucket for
   state:
   - Location: **Automatic**. Don't select a jurisdiction, because that changes the endpoint.
   - Storage class: **Standard**.
   - Public access: off.
2. Next to **API Tokens**, select **Manage**. Create two account API tokens with **Object Read &
   Write** permission, each applied to that bucket only:
   - `terraform-state-ci`, for GitHub Actions
   - `terraform-state-operator`, for local work

   R2 tokens can't be narrowed to an object prefix, so each key reaches the whole state bucket.
   The bucket lock rule described under recovery is what protects backups from a leaked key.
   Leave client IP filtering empty, because GitHub runner addresses change. Cloudflare shows the
   secret access key only once, so store each key in a password manager immediately.
3. Add the operator key and the bucket name to the ignored `.env` in the primary clone.
   `scripts/bootstrap-worktree.ps1 -WithCloudflareToken` copies only `CLOUDFLARE_API_TOKEN` and
   `CLOUDFLARE_ACCOUNT_ID` into a worktree, so these values never reach an agent:

   ```
   TF_STATE_ACCESS_KEY_ID=<operator access key ID>
   TF_STATE_SECRET_ACCESS_KEY=<operator secret access key>
   TF_STATE_BUCKET=<state-bucket>
   ```

   Also set `TF_STATE_ACCOUNT_ID` if the bucket belongs to a different account than
   `CLOUDFLARE_ACCOUNT_ID`.
4. The CI key becomes the GitHub secrets `TF_STATE_ACCESS_KEY_ID` and `TF_STATE_SECRET_ACCESS_KEY`.
   Add them together with the workflow that first uses them, in a GitHub Environment restricted to
   `main`.

Never put either key in `backend.hcl`, command arguments, or any tracked file. The ignored `.env` is
the only file that holds them. HashiCorp
warns that backend credentials supplied through configuration or `-backend-config` can be written to
`.terraform` and to plan files.

## Prove locking works

Run the acceptance test from the primary clone before the first state migration, and again after
any change to `terraform/backend.tf` or the Terraform version:

```powershell
powershell -NoProfile -File .\scripts\test-r2-state-lock.ps1
```

The script reads the `.env` values without displaying them. It copies `terraform/backend.tf` into a
temporary directory, uses a disposable key `lock-test/<random>/terraform.tfstate`, and never plans
the repository's configuration or `ci.auto.tfvars`. A throwaway data source holds the lock for a
fixed time. The script then checks that:
- a second run is refused
- the lock is released normally
- a force-killed run leaves a stale lock, which `terraform force-unlock` clears
- neither credential appears in any output or in `.terraform`
- cleanup confirms no lock remains on the disposable key

Each lock holder writes a marker file once Terraform holds the lock, and the script waits for that
marker instead of a fixed delay. On slow connections, raise `-AcquireTimeoutSeconds` (default 180).

A passing run prints `RESULT: PASS` and leaves no object in the bucket. The script cleans up on any
exit, including failure and Ctrl+C: it stops its Terraform processes and force-unlocks any lock left
on its disposable key. The script prints its run ID when it starts. If the window is closed or the
process is killed before cleanup runs, a `.tflock` object can remain. On the bucket's **Objects**
tab, delete only `lock-test/<run ID>/` for that run. Another operator's test can be using a
different run ID at the same time. Never delete objects under `state/`.

If it fails, don't migrate state. Fix the reported problem, or evaluate ADR 0001's HCP Terraform
fallback. When recording the result, give only the date, the Terraform version, and pass or fail.
Terraform's lock errors include the bucket name, so don't paste raw output.

The test passed with Terraform 1.15.0 on 2026-09-13.

## Initialize the remote backend

Create the ignored `terraform/backend.hcl`. It holds only non-secret, account-specific values:

```hcl
bucket = "<state-bucket>"
key    = "state/terraform.tfstate"
endpoints = {
  s3 = "https://<account-id>.r2.cloudflarestorage.com"
}
```

Load the operator key from `.env` into the current shell only, then initialize from the repository
root. Never type or paste a key into a command: PowerShell's PSReadLine saves command history to
disk. This loop copies the values without displaying them.

```powershell
# Clear any keys already in the shell, so a missing or mistyped .env entry can't leave a stale key.
# A leftover AWS session token would also be sent with the R2 keys and fail authentication.
Remove-Item Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY, Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
$keys = @{}
foreach ($line in Get-Content .env) {
    if ($line -match '^\s*TF_STATE_(ACCESS_KEY_ID|SECRET_ACCESS_KEY)\s*=\s*(.+?)\s*$') {
        $keys[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}
if (-not $keys['ACCESS_KEY_ID'] -or -not $keys['SECRET_ACCESS_KEY']) {
    throw '.env must define both TF_STATE_ACCESS_KEY_ID and TF_STATE_SECRET_ACCESS_KEY.'
}
$env:AWS_ACCESS_KEY_ID = $keys['ACCESS_KEY_ID']
$env:AWS_SECRET_ACCESS_KEY = $keys['SECRET_ACCESS_KEY']
Remove-Item terraform/ci_backend_override.tf -ErrorAction SilentlyContinue
terraform -chdir=terraform init -reconfigure -backend-config=backend.hcl
```

When you're finished, clear the keys from the shell:
`Remove-Item Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY`.

Removing `ci_backend_override.tf` first matters. If a mock gate run was killed before its cleanup
ran, the leftover file keeps Terraform on the local backend.

Don't run a migration or an apply until ADR 0001 phases 3 and 4 authorize one.

## Run the local mock gate safely

The mock gate must never use `backend.hcl` or R2 credentials. From the repository root, run:

```powershell
.\scripts\run-terraform-mock-gate.ps1
```

The script writes an ignored local-backend override, so it can use `ci.auto.tfvars` without
contacting R2, and removes it on every exit. It refuses to run when `terraform/terraform.tfstate*`
exists and stops at the first failing step. The plan is expected to report
`12 to add, 0 to destroy`.

After a remote initialization, never run a standalone `terraform plan` with `ci.auto.tfvars`: it
would run against the real remote state. The gate script re-initializes to the local backend first.

## State recovery

Never edit a Terraform state file manually.

R2 does not document S3 object versioning, so recovery relies on locked backup copies:
- **Backups:** before any state-writing operation, copy the live state object to
  `backups/<UTC timestamp>-<random suffix>.tfstate`. The random suffix guarantees a new key even
  for two copies in the same second, because the bucket lock rejects overwriting an existing backup.
- **Bucket lock rule:** on the bucket's **Settings** tab, a rule on the `backups/` prefix with a
  30-day retention stops any backup being deleted or overwritten for 30 days. That includes deletion
  with a leaked key.
- **Lifecycle rule:** a rule on `backups/` deletes copies after 90 days. The lifecycle expiry must
  be longer than the lock retention.

Never apply a bucket lock rule to `state/` or to the whole bucket. Terraform overwrites the live
state and deletes its `.tflock` during normal operation, and a lock would block both.

Configure the two rules when the first state-writing workflow adds the backup step.

A restore copies an object directly over the live key, which bypasses Terraform's lock. Use a
reviewed procedure that follows these steps:
1. Disable every workflow that uses the state, and confirm no operator is running Terraform against
   it.
2. Confirm that no `state/terraform.tfstate.tflock` object exists. If one does, find out which run
   holds it before going further.
3. Copy the chosen backup over `state/terraform.tfstate`.
4. Run a refresh plan to confirm the result, then re-enable the workflows.

## Sources

- [HashiCorp: S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Cloudflare: Remote R2 backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/)
- [Cloudflare: R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare: R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
