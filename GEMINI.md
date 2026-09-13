# GEMINI.md

## Authoritative rules

Read **`AGENTS.md`** in the repository root and follow it in full. It is the single source of
truth for this repository: safe files, protected files, Terraform safety, secret handling, the
validation commands, and the definition of done. Nothing in this file overrides it.

## Non-negotiables (summary — `AGENTS.md` has the detail)

- Never run `terraform apply`. Plan only, with `-refresh=false -var-file=ci.auto.tfvars`.
- Never modify Terraform state files.
- Never commit secrets, real `.tfvars`, `.env`, or service account material.
- Never print, echo, cat, log, or paste credential contents anywhere — including handoff notes,
  commit messages, PR bodies, and chat. You may *consume* these files; you may not *display* them.
- Never invent infrastructure values (domains, zone IDs, account IDs, tokens, project IDs).
- Keep generated reports out of commits.

## Multi-agent worktree setup

This repository is worked in parallel by Codex, Claude, Gemini, and Copilot agents across five
git worktrees at `../../worktrees/wt-01` .. `wt-05`, each pinned to branch `agent/wt-01` .. `agent/wt-05`.

If you are running inside a worktree:

- **Never check out another slot's branch.** Git forbids two worktrees sharing a branch; doing so
  breaks every other slot.
- Your environment is not provisioned until you run `scripts/bootstrap-worktree.ps1`. Run it with
  no secret flags unless the task spec names one: `-WithCloudflareToken` (read-only agent token),
  `-WithTfvars`, or `-WithServiceAccount` (also requires `-IAcceptServiceAccountRisk`).
- Read **`handoff/README.md`** for the task handoff protocol before starting work.
- Your task spec is at `../../handoff-live/inbox/<your-slot>-<task-id>.md`.
- Update `../../handoff-live/status/<your-slot>.md` when you claim, finish, or block on a task.
- Write a completion note using `handoff/templates/handoff-note.md` to
  `../../handoff-live/outbox/<your-slot>-<task-id>.md`. Never commit it to the repository.

## Validation gate

```powershell
.venv\Scripts\python scripts/run_all_checks.py
terraform -chdir=terraform fmt -check -recursive
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
terraform -chdir=terraform plan -refresh=false -input=false -var-file=ci.auto.tfvars
```

Report outcomes honestly. If a check fails, say so and include the output. Do not claim completion
for work that is partial.
