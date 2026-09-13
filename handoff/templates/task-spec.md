# Task Spec

- **Task ID:** YYYYMMDD-short-slug
- **Slot:** wt-0X
- **Assigned agent:** Codex | Claude | Gemini | Copilot
- **Base branch:** main
- **Assigned:** YYYY-MM-DD

## Objective

One or two sentences. What should be true when this is finished.

## Scope

In scope:
-

Explicitly out of scope:
-

## Files expected to change

-

## Acceptance criteria

- [ ] Python quality gate passes: `.venv\Scripts\python scripts/run_all_checks.py`
- [ ] `terraform -chdir=terraform fmt -check -recursive` passes (if Terraform touched)
- [ ] `terraform -chdir=terraform validate` passes (if Terraform touched)
- [ ] No protected files, reports, state, real tfvars, .env, or service account material committed
- [ ]

## Context and constraints

Links, prior decisions, gotchas. Note anything the worker must NOT assume.

## Secrets needed

None | CLOUDFLARE_API_TOKEN | GCP_SERVICE_ACCOUNT_KEY | real tfvars

If any are needed, the worker must run `scripts/bootstrap-worktree.ps1 -WithSecrets` and must not
display the values.

## Handoff target

Who or what picks this up next: another slot, a PR review, or the orchestrator.
