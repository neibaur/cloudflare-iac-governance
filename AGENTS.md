# AGENTS.md

## Repository Purpose

This repository manages Cloudflare security posture with Terraform and Python automation. Terraform describes zone-level settings, while Python scripts audit compliance, summarize reports, and optionally sync anonymized compliance data for BI reporting.

`main` is the production trunk and the only long-lived branch. Work happens on short-lived branches that are merged into `main` through pull requests and deleted after merge. Changes merged to `main` should already be validated and safe to run against real infrastructure.

## AI Agent Rules

AI and automation agents must:

- Prefer read-only validation, formatting checks, tests, and Terraform plans.
- Never invent infrastructure values such as real domains, zone IDs, account IDs, tokens, project IDs, or sheet IDs.
- Never commit secrets, private keys, credentials, service account material, real `.tfvars`, `.env` files, or raw Cloudflare exports.
- Never modify Terraform state files manually.
- Never run destructive actions, remediation, or `terraform apply` without explicit user approval.
- Keep generated reports and local tool outputs out of commits.
- Treat `terraform/ci.auto.tfvars` as mock CI data only.
- Never run Terraform plans using `ci.auto.tfvars` against a real local or remote state; this can produce destructive plans because mock CI inputs do not match real managed infrastructure.
- For local testing with real state, use a local ignored `terraform/terraform.tfvars` instead of CI mock values.
- Preserve `.secrets.baseline`; detect-secrets is used for local pre-flight checks, while Gitleaks is the CI/CD enforcement gate.

## Safe Files To Edit

These files and folders are generally safe for agents to edit when the change matches the user request:

- `README.md`
- `AGENTS.md`
- `.gitignore`
- `.gitattributes`
- `.editorconfig`
- `.gitleaks.toml`
- `.github/workflows/*.yml`
- `.github/dependabot.yml`
- `pyproject.toml`
- `requirements.txt`
- `requirements-dev.txt`
- `scripts/**/*.py`
- `scripts/tests/**/*.py`
- `terraform/**/*.tf`
- `terraform/tests/**/*.hcl`
- `terraform/ci.auto.tfvars` only when preserving mock, non-secret CI values

## Protected Files And Outputs

Do not edit, create, print, or commit these files manually:

- `terraform.tfstate`
- `*.tfstate*`
- `service_account.json`
- `*.service-account.json`
- `.env`
- `.env.*`
- Real `*.tfvars` files containing domains, zone IDs, credentials, or private configuration
- Cloudflare API exports or raw zone exports
- Generated audit reports in `reports/`
- Generated remediation outputs
- Generated Google Sheets sync outputs
- Any file containing credentials, tokens, passwords, private keys, or service account material

If a protected local file exists, leave it alone unless the user explicitly asks for a safe action such as confirming whether it is ignored.

## Validation Commands

Run the lightweight local quality gate before proposing a change is complete:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python scripts/run_all_checks.py
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
terraform -chdir=terraform plan -refresh=false -input=false -var-file=ci.auto.tfvars
```

The mock-value plan runs only in CI or a worktree checkout that has no Terraform state. Before
running it, check for `terraform/terraform.tfstate*`. If any matching file exists, skip the plan
and report that mock inputs must not be planned against real state. Do not move, edit, or remove
state to make the check pass.

Report every validation outcome honestly. If a check fails, include the relevant output and do
not describe partial work as complete.

Use `detect-secrets` locally when changing files that could contain sensitive values:

```powershell
detect-secrets scan --baseline .secrets.baseline
detect-secrets audit .secrets.baseline
```

## Terraform Safety Rules

- Never run `terraform apply` in pull request workflows.
- Default validation is `terraform fmt -check -recursive`, `terraform init -backend=false`, `terraform validate`, and a safe-input `terraform plan`.
- Use `-refresh=false` for PR/local mock-value plans when local state or credentials may exist.
- Use only mock CI values from `terraform/ci.auto.tfvars` for PR validation.
- Use real values only through GitHub Secrets or a local ignored `terraform/terraform.tfvars`.
- Any state-changing operation requires explicit user intent.
- Never manually edit, normalize, move, or recreate Terraform state files.

## Secret Handling

- Keep `REAL_TFVARS`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `GCP_SERVICE_ACCOUNT_KEY`, and `GOOGLE_SHEET_ID` in GitHub Secrets or local ignored files.
- Do not paste secret values into issues, PRs, docs, logs, tests, examples, or generated reports.
- Use placeholders in documentation and examples.
- Keep `.secrets.baseline` for local detect-secrets checks.
- Treat Gitleaks failures in CI as release-blocking until reviewed and remediated.

## Multi-Agent Worktrees

Codex, Claude, Gemini, and Copilot can work in parallel across five worktrees at
`../../worktrees/wt-01` through `wt-05`. Each slot is pinned to its matching `agent/wt-0X`
branch. A worker never checks out another slot's branch because Git cannot attach one branch to
multiple worktrees safely.

Before starting work in a slot:

- Read `handoff/README.md` and the assigned task spec at
  `../../handoff-live/inbox/<your-slot>-<task-id>.md`.
- Run `scripts/bootstrap-worktree.ps1`. Use no secret flags unless the task spec names one. The
  available flags are `-WithCloudflareToken`, `-WithTfvars`, and `-WithServiceAccount`; the last
  also requires `-IAcceptServiceAccountRisk`.
- Update `../../handoff-live/status/<your-slot>.md` when claiming, completing, or blocking a task.
- Write the completion note from `handoff/templates/handoff-note.md` to
  `../../handoff-live/outbox/<your-slot>-<task-id>.md`. Never commit the note.

The handoff protocol defines branch creation, status values, credential brokering, and the full
worker lifecycle.

## Definition Of Done

A change is complete when:

- Python quality checks pass.
- Terraform formatting, validation, and safe-input planning pass.
- No protected files, generated reports, Terraform state, real `.tfvars`, `.env`, or service account files are committed.
- CI workflows remain purpose-specific: fast quality checks for PRs, state-aware Terraform audit/remediation only with explicit gating.
- Documentation reflects any changed commands, secrets, or operational expectations.
