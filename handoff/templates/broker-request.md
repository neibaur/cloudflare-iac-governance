# Broker Request

A worker files this when it needs real infrastructure data it cannot get without a credential.
The operator runs the command in the primary clone and returns the sanitized output. The worker
never receives the credential itself.

Write this to `handoff-live/outbox/<slot>-<task-id>-broker-request.md` and set the slot status to
`BLOCKED` with reason `awaiting broker`.

---

- **Task ID:**
- **Slot:** wt-0X
- **Agent:** Codex | Claude | Gemini | Copilot
- **Requested:** YYYY-MM-DD

## What I need

The specific data, in terms of fields and scope. "The current SSL mode and zone ID for every zone
in the account", not "Cloudflare data".

## Why I need it

What in the task spec is unfinishable without it. If the task can be completed against
`terraform/ci.auto.tfvars` mock values or fixtures instead, say so and withdraw the request.

## Command I believe should run

```powershell
.\scripts\export-audit-snapshot.ps1 -Label <task-id>
```

Read-only only. If you are proposing anything that writes, changes state, or runs
`terraform apply`, stop: that is not a broker request, it is an escalation to a human.

## What I will do with the result

How the snapshot gets used, and what lands in the commit. Name the files you expect to change.

## Confirmation

- [ ] I am not asking for a credential, only for output.
- [ ] The command I named is read-only.
- [ ] I will not commit the snapshot or quote its contents into any tracked file, PR, or issue.
- [ ] Findings I write down will be generalized (counts, settings, compliance state) rather than
      copied identifiers, unless the task spec explicitly requires the identifiers.
