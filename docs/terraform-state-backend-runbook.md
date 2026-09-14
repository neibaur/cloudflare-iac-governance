# Terraform R2 State Backend Runbook

Use this runbook only after the phase 2 acceptance test has been authorized. It prepares and tests
a remote state backend; it does not migrate state or authorize `terraform apply`.

Terraform 1.15.9 meets the S3 backend's Terraform 1.10 minimum for native lockfiles. The S3
backend stores state at a bucket/key path, and `use_lockfile = true` enables its opt-in lockfile
locking. It needs read, write, and delete access to the companion `.tflock` object.
([HashiCorp S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3))

Cloudflare's R2 backend guidance requires `region = "auto"`, a path-style S3 endpoint, and the
R2 compatibility flags committed in `terraform/backend.tf`. It also specifies a bucket-scoped R2
API token with **Object Read & Write** permission.
([Cloudflare R2 Terraform backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/))

## Create the dedicated backend access

Create one dedicated R2 bucket for Terraform state. Do not share it with application data. Create
two separate scoped R2 API credentials with **Object Read & Write** permission limited to that
bucket: one for CI and one for the local operator. Cloudflare shows the secret access key only
once, so store it immediately in the intended secret store; never place either credential in this
repository.

Store the CI credential as GitHub Actions secrets named:

- `TF_STATE_ACCESS_KEY_ID`
- `TF_STATE_SECRET_ACCESS_KEY`

For local operator work, set the separate operator credential only in the current shell:

```powershell
$env:AWS_ACCESS_KEY_ID = "<operator-r2-access-key-id>"
$env:AWS_SECRET_ACCESS_KEY = "<operator-r2-secret-access-key>"
```

Do not put credentials in `backend.hcl`, command arguments, configuration, plan output, or logs.
HashiCorp notes that backend credentials supplied in configuration or `-backend-config` can be
written to `.terraform` and plan files. ([HashiCorp S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3))

## Initialize the remote backend

Create the ignored `terraform/backend.hcl` locally. It contains only non-secret, account-specific
backend values:

```hcl
bucket = "<state-bucket>"
key    = "state/terraform.tfstate"
endpoints = {
  s3 = "https://<account-id>.r2.cloudflarestorage.com"
}
```

From the repository root, initialize the partial backend explicitly:

```powershell
terraform -chdir=terraform init -reconfigure -backend-config=backend.hcl
```

Do not run a migration or an apply during phase 2. The bucket name, state key, and endpoint are
intentionally absent from committed Terraform configuration. They are supplied only by this
ignored local file (or equivalent protected CI inputs).

## Run the local mock gate safely

The mock gate must never use `backend.hcl` or R2 credentials. It writes an ignored local-backend
override, so it can use `ci.auto.tfvars` without contacting the remote backend. Run these commands
from the repository root, after confirming no `terraform/terraform.tfstate*` file exists:

```powershell
@'
terraform {
  backend "local" {}
}
'@ | Set-Content terraform/ci_backend_override.tf -NoNewline
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
terraform -chdir=terraform test
terraform -chdir=terraform init -reconfigure
terraform -chdir=terraform plan -refresh=false -input=false "-var-file=ci.auto.tfvars"
Remove-Item terraform/ci_backend_override.tf -ErrorAction SilentlyContinue
```

The final plan is expected to report `12 to add, 0 to destroy`. Removing the override restores
the partial R2 backend configuration. Do not use `ci.auto.tfvars` after remote initialization, and
do not run a mock plan against real state.

## Lock acceptance test

Perform this test in a separate disposable bucket or with a disposable key such as
`lock-test/<random-run>/terraform.tfstate`. Never use the production state key or its lock object.
Use the same partial backend configuration and a separate ignored `backend.hcl` with the disposable
bucket/key. Export only the dedicated test credential as the two `AWS_*` environment variables.

Initialize the disposable backend:

```powershell
terraform -chdir=terraform init -reconfigure -backend-config=backend.hcl
```

In two separate terminals, start the following command at the same time. The command is read-only;
it neither applies infrastructure nor writes a state snapshot. Use `-lock-timeout=0s` so a failed
second acquisition is immediately visible rather than waiting.

```powershell
terraform -chdir=terraform plan -refresh=false -input=false -lock-timeout=0s "-var-file=ci.auto.tfvars"
```

Repeat the simultaneous start until one terminal reports that it could not acquire the state lock.
The other must finish normally. Record only the test date, Terraform version, disposable test
identifier, success/failure result, and whether credentials were absent from visible output; do not
retain bucket names, account identifiers, lock contents, or credential values in shared evidence.

For a normal-unlock check, run the command once more after the successful holder exits. It must
acquire and release the lock normally.

For stale-lock recovery, begin the same disposable-key plan and interrupt its process only after it
has announced that it acquired the lock. Do not interrupt a production command. Start another
disposable-key plan with `-lock-timeout=0s`; Terraform reports the stale lock information including
its lock ID. Privately copy only that lock ID into this command:

```powershell
terraform -chdir=terraform force-unlock <lock-id>
```

Confirm the next disposable-key plan acquires the lock and completes. `force-unlock` operates on
remote state locking, so use it only after verifying the named lock belongs to the interrupted
disposable test. Do not run it against the production key. Record that recovery succeeded without
recording the lock ID or other identities.

If the concurrent or stale-lock checks fail, stop before state migration and evaluate the ADR's HCP
Terraform fallback. Cloudflare documents the R2 S3 compatibility needed by the backend, but the
end-to-end lock behavior remains an operator acceptance test.

## State recovery

Do not edit a Terraform state file manually. R2's current Terraform-backend documentation does not
establish object versioning as a recovery feature, so treat it as unavailable unless the operator
verifies current official documentation for the chosen bucket.

The recommended recovery design is a scheduled copy of the live state object to a `backups/`
prefix, using a new object key for every copy. Protect that backup prefix with an R2 bucket lock
rule and configure lifecycle expiry for the retention period the operator selects. This protects
backup copies from accidental deletion or overwrite until their retention expires. It does not
protect the live state key from corruption between copies, and it must not cover the live state key
or its `.tflock`, because Terraform overwrites those objects during normal operation.

If future R2 object versioning becomes available and is verified for this use, it can protect prior
versions of the same live object. Bucket lock/retention protects the locked backup objects from
deletion and overwrite. Scheduled copies create independently named recovery points. The operator
chooses the final recovery control and retention period after the lock test. Restore only through a
reviewed Terraform/R2 recovery procedure, never by manually editing state.

## Sources

- [HashiCorp: S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Cloudflare: Remote R2 backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/)
