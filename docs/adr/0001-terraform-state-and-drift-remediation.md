# ADR 0001: Terraform State and Guarded Drift Remediation

## Status

Accepted

## Date

2026-09-13

## Context

Terraform in CI initializes with `-backend=false` and has no durable state. An apply from that
position would evaluate the real inventory from empty state and discard whatever state it created,
which is not a safe basis for managing existing infrastructure, so no workflow runs `terraform apply`
until this design is implemented. The configuration declares five
`cloudflare_zone_setting` instances and one `cloudflare_bot_management` instance for each zone. At
roughly 96 zones, the intended state contains about 576 managed resources. The Python audit checks
only four of those six controls, and its standard is separate from the Terraform defaults.

Terraform must first acquire durable, locked state and adopt every existing object. Only after a
stable no-change baseline exists can scheduled plans detect drift. Automatic correction is a later
capability with a deliberately narrow fail-closed policy.

This repository is public. GitHub states that Actions history and logs in a public repository are
visible to everyone, and people with repository read access can download workflow artifacts
([repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility),
[artifact access](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)).
Terraform also warns that saved plan files can contain sensitive data and must not be committed
([saved plans](https://developer.hashicorp.com/terraform/tutorials/cli/plan)). Domain names, zone
identifiers, state, plans, and raw audit reports are therefore confidential operational data even
when they do not contain credentials.

## Decision drivers

- State must be durable, recoverable, encrypted, access-controlled, and locked across operator and
  CI runs.
- Adoption must never propose creating or deleting existing zone controls.
- Drift checks must be scheduled, observable, inexpensive, and bounded by Cloudflare API limits.
- The automatic path must be structurally unable to create, delete, or replace resources.
- An unstable correction must stop after one attempt and alert instead of looping.
- Read credentials and edit credentials must have separate lifetimes and scopes.
- Public logs and artifacts must reveal counts and classifications, not infrastructure identities.
- Terraform and the independent Python audit must interpret one security standard.
- Each implementation step must be independently reviewable and reversible.

## Options considered

### State backend: Cloudflare R2 through Terraform's S3 backend

Pros:

- The S3 backend supports opt-in native lockfile locking with `use_lockfile = true`; lock objects
  need get, put, and delete permissions. HashiCorp also recommends bucket versioning for recovery
  ([S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)).
- Cloudflare documents R2 as a Terraform S3 remote backend. Its example uses `region = "auto"`, an
  account-specific S3 endpoint, `use_path_style = true`, and
  `skip_credentials_validation`, `skip_metadata_api_check`, `skip_region_validation`,
  `skip_requesting_account_id`, and `skip_s3_checksum` set to true
  ([R2 backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/)).
- Terraform's native lock is a `.tflock` object acquired with a conditional write. R2 documents
  support for `If-None-Match` on `PutObject`, plus `GetObject` and `DeleteObject`
  ([R2 S3 compatibility](https://developers.cloudflare.com/r2/api/s3/api/)). These are the S3
  operations and conditional behavior the lock implementation needs.
- It keeps execution in GitHub Actions and avoids a managed-resource subscription threshold.

Cons:

- Terraform introduced S3 native lockfiles in Terraform 1.10. The repository pins Terraform 1.15,
  which satisfies that minimum. The 1.10 release is the first release whose S3 backend exposes
  this behavior ([Terraform 1.10 release](https://github.com/hashicorp/terraform/releases/tag/v1.10.0),
  [S3 lock configuration](https://developer.hashicorp.com/terraform/language/backend/s3)).
- Cloudflare's backend example does not currently demonstrate `use_lockfile`, bucket versioning, or
  a concurrent lock test. Compatibility follows from the documented S3 operations, but the exact
  Terraform/R2 combination still needs an acceptance test before state migration.
- The operator must create and secure the bucket and two narrowly scoped R2 credentials. Backend
  credentials must come from environment variables or a partial backend configuration because
  HashiCorp warns that hard-coded or command-line backend secrets can be copied into `.terraform`
  and plan files ([backend credential warning](https://developer.hashicorp.com/terraform/language/backend/s3)).

### State backend: HCP Terraform

Pros:

- HCP Terraform provides remote execution, VCS integration, and state management. Its Free plan
  includes one concurrent remote run and one concurrent agent run
  ([HCP Terraform plans](https://developer.hashicorp.com/terraform/cloud-docs/overview)).
- Locking and run serialization are managed by the service rather than assembled from object-store
  behavior.

Cons:

- A Free organization is limited to 500 managed resources, while this configuration is expected to
  manage about 576. Resources created with `for_each` count individually, so this repository does
  not fit the Free plan at its current scale
  ([HCP Terraform plans](https://developer.hashicorp.com/terraform/cloud-docs/overview)).
- Paid service cost and an additional control plane are required. The current price for the needed
  paid capacity is intentionally not fixed in this ADR because pricing changes; the operator must
  obtain it when deciding.

### Existing-zone inventory: explicit input versus discovery

Keeping the domain-to-zone map in `REAL_TFVARS` makes the managed inventory explicit and preserves
the current `for_each` keys. It also avoids silently adding every account zone to management. Its
cost is secret rotation and duplication: the inventory can become stale, and domain names and zone
identifiers live in a broad secret alongside configuration values.

Provider-backed discovery could reduce inventory maintenance. The provider v5 `cloudflare_zone`
data source accepts an account/name filter and returns zone identity and name
([zone data source](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/data-sources/zone)).
However, current official documentation does not establish a plural, fully paginated v5 data source
that safely returns all account zones as a stable `for_each` map. Discovery also changes the trust
boundary: a newly created account zone could enter Terraform management automatically. The first
adoption therefore keeps an explicit inventory, separates inventory from the security standard,
and treats automatic full-account discovery as an open design question.

### Plan policy: a small Python checker versus OPA/conftest

A small Python checker can read `resource_changes[*].change.actions`, resource type, and count from
`terraform show -json`. It uses the repository's existing language, test runner, and review skills;
the complete policy is small enough to audit directly.

OPA evaluates policies against Terraform plan JSON and is designed for pre-apply policy checks, but
its documentation notes that unknown plan-time values limit what a policy can know
([OPA Terraform integration](https://www.openpolicyagent.org/docs/terraform)). OPA/conftest adds a
runtime, Rego source, dependency maintenance, and a second test tool. That is worthwhile for a broad
organization-wide policy library, but not for this narrow action/type/count gate.

## Decision

Cloudflare R2 through the S3 backend is the chosen backend, contingent on the phase 2 concurrent-lock
acceptance test; HCP Terraform is the fallback if that test fails. Keep Terraform at 1.10 or later
(the repository pins 1.15). Enable `use_lockfile = true`; configure the documented R2
endpoint and compatibility flags; provide credentials only through environment variables or
ephemeral runner files; restrict object permissions to the state key and its `.tflock` companion;
and enable R2 object versioning if the selected R2 feature supports the required recovery workflow.
The exact R2 version-retention mechanism is unverified and remains an open question.

HCP Terraform is the fallback if the R2 concurrency test fails. Its 500-resource Free limit does
not fit the expected state.

Keep an explicit zone inventory for initial adoption. Split it from the policy standard and retain
it as a protected CI secret named `REAL_TFVARS` until a separately reviewed inventory mechanism is
available. Use root-module `import` blocks with `for_each` to adopt all objects. Cloudflare provider
v5 imports `cloudflare_zone_setting` with `<zone_id>/<setting_id>` and
`cloudflare_bot_management` with `<zone_id>`
([zone-setting import](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zone_setting),
[bot-management import](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/bot_management)).
Cloudflare's migration guide states that generated import blocks require Terraform 1.7 or later and
that import blocks targeting resources inside modules must live in the root module
([provider v5 migration](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/guides/version-5-migration.md)).
The repository's 1.10-or-later backend requirement therefore also satisfies import iteration.

Before the first import apply, generate a saved plan and require it to contain exactly the expected
imports, with zero creates, updates, deletes, or replacements. The operator reviews and performs
that one state-writing apply. A following refresh plan must be empty. Import blocks remain until the
team deliberately removes them after adoption; Terraform must never bind one remote object to more
than one resource address
([import safety](https://developer.hashicorp.com/terraform/cli/commands/import)).

After adoption, run scheduled `terraform plan -detailed-exitcode -out=<ephemeral-path>`. Exit code 0
means no drift, 1 means an error, and 2 means a non-empty diff
([plan exit codes](https://developer.hashicorp.com/terraform/cli/commands/plan)). At roughly 576
resources, a simple upper-bound estimate of one refresh request per resource is below Cloudflare's
documented global 1,200 requests per five minutes per user/account token. A real plan may make more
than one request per resource and other callers share the quota, so this comparison does not prove
that a plan fits. Measure request count/duration and observe rate-limit headers during a read-only
pilot; schedule with margin and fail on HTTP 429 rather than applying
([Cloudflare API limits](https://developers.cloudflare.com/fundamentals/api/reference/limits/)).

Use a tested Python policy checker for guarded correction. OPA/conftest remains an option when the
policy surface grows beyond this repository.

## Safety design

The drift workflow has separate plan, decision, apply, verification, and alert stages.

1. The scheduled plan job uses `CLOUDFLARE_PLAN_API_TOKEN`, which has only the account/zone read
   permissions needed for discovery and refresh. Separate backend credentials named
   `TF_STATE_ACCESS_KEY_ID` and `TF_STATE_SECRET_ACCESS_KEY` provide read/write access to only the
   remote state and lock objects; non-secret endpoint, bucket, region, and key configuration comes
   from reviewed configuration or GitHub variables. The job saves a binary plan in an ephemeral
   directory and converts that exact file with
   `terraform show -json`; Terraform documents that `show -json` emits a plan's JSON representation
   ([show command](https://developer.hashicorp.com/terraform/cli/commands/show)). Neither form is
   printed or uploaded.
2. The checker denies by default. It considers only entries with non-empty actions. Every action
   list must equal `["update"]`; every resource type must be in an explicit allow-list initially
   limited to `cloudflare_zone_setting` and `cloudflare_bot_management`; and the total changed
   resource count must not exceed a conservative ceiling, initially 10. The ceiling is a policy
   constant with unit tests and requires code review to change.
3. Any `create`, `delete`, `["delete","create"]`, `["create","delete"]`, unknown action, unknown
   resource type, malformed/unknown value that prevents classification, or count above 10 denies
   the entire apply. There is no partial apply and no `-target`. The alert reports only commit/run
   identity, aggregate counts, action classes, and resource types. A job with least-privilege
   `GITHUB_TOKEN` permissions can open an issue using `contents: read` and `issues: write`
   ([GitHub token permissions](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)).
4. The apply job references a protected GitHub Environment and receives
   `CLOUDFLARE_APPLY_API_TOKEN` only there. Environment secrets are unavailable until the job's
   protection rules pass, and environments can restrict deployment branches
   ([GitHub environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)).
   The apply token has only the specific zone-setting and bot-management edit permissions required;
   it has no zone-create/delete permission. Backend credentials remain separate from Cloudflare API
   credentials. `CLOUDFLARE_APPLY_API_TOKEN` is an Environment secret;
   `CLOUDFLARE_PLAN_API_TOKEN`, `TF_STATE_ACCESS_KEY_ID`, and `TF_STATE_SECRET_ACCESS_KEY` are
   available only to jobs that need them; and `REAL_TFVARS` remains a separate protected inventory
   secret during the migration phases. Secret values never enter command arguments or output.
5. The apply command consumes the already inspected saved plan file. It never runs a fresh plan.
   Applying a saved plan executes those recorded actions without a new approval prompt
   ([saved plan behavior](https://developer.hashicorp.com/terraform/tutorials/cli/plan)). The plan
   file moves between jobs only through a non-public mechanism; if GitHub Actions cannot transfer it
   without making it downloadable to public readers, plan and apply run in one environment-gated job
   with the read token removed before the edit token is exposed.
6. After apply, remove the edit token from the environment and run one new read-only plan with
   `-detailed-exitcode`. Only exit 0 succeeds. Exit 1 or 2 fails and opens a summarized alert. The
   workflow never retries an apply.
7. Give all state-using workflows the same fixed `concurrency` group with `cancel-in-progress:
   false`. GitHub documents that concurrency limits a group to one running job or workflow
   ([deployment concurrency](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)).
   The backend lock is the second line of defense.
8. Trigger drift remediation only from `schedule` (and retain a separately gated diagnostic manual
   trigger if useful), never from issue, workflow completion, state-object change, or a bot commit.
   The workflow does not modify repository files or dispatch itself. Creating or updating its alert
   issue therefore cannot trigger another remediation run. There is one plan, at most one apply, and
   one verification plan per scheduled run.
9. Keep the Python audit scheduled and independent. It uses the plan/read token, executes even when
   Terraform reports no drift, and alerts on disagreement. It must cover all six Terraform controls
   before automatic correction is enabled.

The automatic path cannot destroy because the JSON gate rejects every delete, replacement, and
create; the apply credential lacks zone lifecycle permissions; and only the approved saved plan is
applied. It cannot loop because no emitted event is a trigger, workflow concurrency serializes runs,
there is no retry, and the single post-apply plan alerts without applying again.

Public output is reduced to status, total refreshed resources, changed-resource count, allow-listed
resource types, and policy decision. Commands redirect normal plan, state, provider debug, and audit
detail to ephemeral files. `TF_LOG` stays off. Workflow annotations, issue bodies, step summaries,
cache keys, filenames, and artifact names contain no domain or zone identifier. Binary/JSON plans,
state, raw audit CSV, `REAL_TFVARS`, and provider logs are never uploaded. If a private evidence
store is later approved, upload only a redacted summary with the shortest useful retention; GitHub
documents 1–90 day retention for public-repository logs and artifacts
([retention limits](https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization)).

Create one versioned, non-secret policy document (for example JSON) containing setting identifiers,
expected values, and whether each resource type is eligible for automatic correction. Terraform
loads it with `jsondecode(file(...))`; Python loads the same file with its JSON library. Schema tests
reject unknown keys/types and both implementations test the same fixtures. Zone inventory and
credentials are not part of this document. Terraform configuration becomes the enforcement engine,
the Python audit remains an independent observation engine, and neither carries a second copy of the
standard.

## Consequences

- CI gains serialized, recoverable state and meaningful drift plans.
- The first safe adoption is operator-assisted and deliberately slower than ordinary delivery.
- R2 adds bucket and credential administration; HCP Terraform remains a paid fallback.
- Automatic correction covers only small, known in-place drift. Larger or structurally different
  plans intentionally require human review.
- A plan that encounters throttling, unknown JSON, a policy-checker failure, or verification drift
  becomes an alert, never an apply.
- Raw troubleshooting data cannot be placed in public Actions output. Operators need a private,
  credentialed workstation for identity-level diagnosis.
- Sharing one declarative standard removes value drift between Terraform and Python, while their
  separate implementations preserve independent detection.

## Implementation plan

Each phase is one reviewable pull request and must pass the repository quality gate.

1. **Canonical standard and parity.** Add the non-secret versioned policy file, schema validation,
   Terraform loading, Python loading, and parity tests for all six controls. Acceptance: Terraform
   and Python tests consume the same fixture and the audit reports every enforced control. No
   operator action is needed.
2. **Backend prerequisites and lock proof.** Confirm the pinned Terraform version still satisfies the
   1.10 lockfile minimum, add partial R2 S3 backend configuration, document recovery, and add a disposable-backend
   lock test procedure. Acceptance: two concurrent holders cannot acquire the same test lock, stale
   lock recovery is demonstrated, and no credential appears in configuration or logs. The operator
   creates the R2 bucket, enables the selected recovery/versioning feature, creates scoped backend
   credentials, and adds the named secrets.
3. **Inventory and generated imports.** Separate inventory from standard values and add root-module
   `for_each` import blocks for all five setting resources and bot management per zone. Acceptance:
   a saved plan against remote state reports exactly the expected imports and zero create, update,
   delete, or replacement actions. The operator supplies/rotates `REAL_TFVARS` and privately checks
   the inventory.
4. **First adoption.** Add a one-time environment-gated workflow/runbook that applies only the
   reviewed import plan. Acceptance: the operator performs the first import apply, state contains
   each intended object exactly once, and the immediate full refresh plan returns exit 0. This is
   the only phase whose acceptance requires the first import apply; rollback uses a reviewed state
   version/recovery procedure, never manual state editing.
5. **Scheduled drift detection.** Replace state-less CI planning with locked remote-state planning,
   detailed exit codes, sanitized summaries, concurrency, and alerts. Acceptance: scheduled no-drift,
   safe-drift, error, and simulated-rate-limit cases produce the expected result without exposing
   identities. The operator adds `CLOUDFLARE_PLAN_API_TOKEN` and backend read/lock secrets.
6. **Policy checker in report-only mode.** Add the Python JSON-plan gate and unit fixtures for every
   allowed and denied action sequence, allow-list violation, malformed input, and the ceiling.
   Acceptance: the checker never invokes Terraform and report-only scheduled runs classify several
   observed cycles correctly. No operator action is needed beyond reviewing classifications.
7. **Environment-gated canary correction.** Add saved-plan apply with
   `CLOUDFLARE_APPLY_API_TOKEN`, initially with a ceiling of one and a narrowly selected setting
   allow-list, followed by the mandatory zero-diff plan. Acceptance: an operator-created benign
   canary drift is corrected once; create/delete/replace fixtures apply nothing; failed verification
   opens one sanitized alert; and no retry or self-trigger occurs. The operator creates/protects the
   GitHub Environment and supplies the edit token.
8. **Bounded automatic correction.** After an agreed observation period and canary evidence, enable
   scheduled apply without manual approval for the reviewed allow-list and raise the ceiling no
   higher than 10. Acceptance: documented evidence shows stable convergence, a forced unsafe plan
   applies nothing, overlapping runs serialize, and the independent audit agrees after correction.
   The operator explicitly approves removing the environment's manual reviewer while retaining its
   branch restrictions and secrets.

## Open questions

- Which R2 object-versioning or retention feature provides tested state recovery, and what retention
  period is appropriate? The official Terraform/R2 backend page does not verify this.
- Does Terraform 1.10's native S3 lock pass concurrent acquisition, unlock, interrupted-run, and
  recovery tests against the operator's R2 bucket with the documented compatibility flags? The API
  primitives are documented, but end-to-end support is not explicitly guaranteed by Cloudflare.
- What is the measured request count and duration of a full refresh of approximately 576 resources,
  including provider retries and other token users? Until measured, one plan fitting inside the
  1,200-per-five-minute limit is unverified.
- Can the pinned provider version expose a complete, paginated, deterministic account-zone
  collection suitable for `for_each`, and should newly discovered zones be opt-in? Until verified,
  `REAL_TFVARS` remains the explicit inventory.
- What private transfer mechanism, if any, is acceptable for a saved plan between GitHub jobs in a
  public repository? Without one, plan, decision, and apply stay in one protected job.
- What observation period and evidence threshold are sufficient before the operator enables
  unattended correction, and which individual settings besides the initial canary are safe enough
  to allow-list?

## References

- [Terraform S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)
- [Cloudflare R2 remote backend](https://developers.cloudflare.com/terraform/advanced-topics/remote-backend/)
- [Cloudflare R2 S3 API compatibility](https://developers.cloudflare.com/r2/api/s3/api/)
- [HCP Terraform plans and limits](https://developer.hashicorp.com/terraform/cloud-docs/overview)
- [Terraform import block](https://developer.hashicorp.com/terraform/language/block/import)
- [Cloudflare provider v5 migration guide](https://github.com/cloudflare/terraform-provider-cloudflare/blob/main/docs/guides/version-5-migration.md)
- [Cloudflare zone-setting import](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zone_setting)
- [Cloudflare bot-management import](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/bot_management)
- [Terraform plan command](https://developer.hashicorp.com/terraform/cli/commands/plan)
- [Terraform show command](https://developer.hashicorp.com/terraform/cli/commands/show)
- [Terraform JSON output format](https://developer.hashicorp.com/terraform/internals/json-format)
- [Cloudflare API rate limits](https://developers.cloudflare.com/fundamentals/api/reference/limits/)
- [OPA policy checks for Terraform](https://www.openpolicyagent.org/docs/terraform)
- [GitHub Actions environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [GitHub Actions deployment concurrency](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
- [GitHub Actions token permissions](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
- [GitHub public-repository visibility](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility)
