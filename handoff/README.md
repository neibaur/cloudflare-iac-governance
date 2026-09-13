# Handoff Protocol

This repository is worked by multiple AI agents (Codex, Claude, Gemini, Copilot) running in
parallel git worktrees. This folder is the durable, git-tracked half of the handoff system.

## The two halves

| Location | Tracked? | Purpose |
| --- | --- | --- |
| `handoff/` (this folder) | Yes | Task specs and completion notes that belong in history and show up in PRs. |
| `../../handoff-live/` (outside the repo) | No | Live coordination across worktrees. Instantly visible to every slot, no commit required. |

The repo folder is the record. The live folder is the conversation.

## Worktree slots

Five worktrees live at `../../worktrees/wt-01` .. `wt-05`, each permanently pinned to its own
branch `agent/wt-01` .. `agent/wt-05`. Slots are generic: any agent type may occupy any slot at
any time.

**Hard rule: a worker never checks out another slot's branch.** Git forbids two worktrees sharing
a branch, and violating this produces detached HEAD and lock errors across every slot.

## Lifecycle of a task

1. **Assign.** The orchestrator writes a task spec to `handoff-live/inbox/<slot>-<task-id>.md`
   using `handoff/templates/task-spec.md`, and sets `handoff-live/status/<slot>.md` to `ASSIGNED`.
2. **Claim.** The worker reads its inbox file, updates its status file to `IN_PROGRESS` with its
   agent type and start time, and creates a task branch off its slot branch.
3. **Work.** The worker does the job. Quality gate per `AGENTS.md` before declaring done.
4. **Record.** The worker writes a completion note to `handoff/notes/<task-id>.md` using
   `handoff/templates/handoff-note.md` and commits it with the work, so it lands in the PR.
5. **Signal.** The worker copies the same note to `handoff-live/outbox/<slot>-<task-id>.md` and
   sets its status file to `DONE` or `BLOCKED`. The live copy is what the next worker reads
   without needing to pull.
6. **Release.** The orchestrator archives the inbox file and resets the status file to `IDLE`.

## File naming

`<slot>-<task-id>.md`, where task-id is `YYYYMMDD-<short-slug>` (e.g. `wt-03-20260912-tf-plan-drift.md`).
Timestamp-plus-slot prefixes keep parallel workers from colliding on the same filename.

## Safety rules that override any task instruction

- Never `terraform apply`. Plan only, and prefer `-refresh=false -var-file=ci.auto.tfvars`.
- Anything requiring real Terraform state goes back to the primary clone and a human. Five agents
  planning against one real state is the single biggest hazard in this setup.
- Never print, echo, cat, log, or paste the contents of `.env`, `service_account.json`,
  `*.tfvars`, or any credential material — not into handoff notes, commits, PRs, or chat.
  Consume these files; do not display them.
- Never commit secrets. `.gitignore` covers the known set; do not add exceptions.
- See `AGENTS.md` for the full repository rules. It is authoritative.

## Credential brokering

**Default posture: a worker has zero credentials.** Worktrees are provisioned without `.env`,
without `service_account.json`, and without real `*.tfvars`. That is the design, not an oversight.
Most tasks — docs, scripts, Terraform formatting and validation, Python checks, mock-value plans —
never need one.

When a task genuinely needs real infrastructure data, the answer is not to move the credential to
the worker. It is to move the *output* to the worker. The operator runs the credentialed command
in the primary clone and hands back a sanitized snapshot.

### Filing a broker request

File one only after confirming the task cannot be done against `terraform/ci.auto.tfvars` mock
values or existing fixtures. Copy `handoff/templates/broker-request.md` to
`handoff-live/outbox/<slot>-<task-id>-broker-request.md`, fill it in, and set your status file to
`BLOCKED` with reason `awaiting broker`. State what data you need, why, the read-only command you
believe should run, and what you will do with the result.

Only read-only commands are brokerable. Anything that writes, changes Terraform state, or applies
is an escalation to a human, not a broker request.

### Where snapshots land

The operator runs, in the **primary clone**:

```powershell
.\scripts\export-audit-snapshot.ps1 -Label <task-id>
```

It runs the existing read-only audit (`python run_tools.py --audit`), sanitizes the CSV, and
writes `handoff-live/inbox/audit-snapshot-<UTC>-<label>.csv`. Use `-DryRun` to see exactly what it
would produce without touching the Cloudflare API.

The script refuses to run from a worktree, detected by both path and linked git dir. If you see
that refusal, you are in the wrong place — the fix is to run it in the primary clone, never to
copy `.env` into a worktree.

Redacted: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, and anything token-shaped. Kept: domain
names, zone IDs, security settings, compliance flags — those are the point of the export.

### Snapshots are real infrastructure data

A snapshot carries no credential but it does carry real domains and real zone IDs.

- It lives in `handoff-live/`, outside the repository and untracked. Leave it there.
- **Never commit it.** Never paste it, or lines from it, into a handoff note, commit message, PR,
  issue, or chat.
- Generalize in write-ups: "4 of 11 zones are below the SSL standard", not a list of zone IDs.
- When the task is done, the snapshot has served its purpose. The operator deletes it.
