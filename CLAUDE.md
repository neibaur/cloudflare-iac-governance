# CLAUDE.md

Read `AGENTS.md` in the repository root and follow it in full. It is the single source of truth;
nothing in this file overrides it.

## Non-negotiables

- Never run `terraform apply`; plan only under the safety conditions in `AGENTS.md`.
- Never modify Terraform state files.
- Never commit secrets, real `.tfvars`, `.env`, or service account material.
- Never print, echo, cat, log, or paste credential contents into handoff notes, commits, pull
  requests, or chat. Credential files may be consumed but not displayed.
- Never invent infrastructure values such as domains, zone IDs, account IDs, tokens, or project
  IDs.
- Keep generated reports out of commits.

For slot rules, bootstrap flags, task specs, status files, and completion notes, follow
`AGENTS.md`'s **Multi-Agent Worktrees** section and `handoff/README.md`.
