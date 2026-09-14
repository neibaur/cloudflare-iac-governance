# ADR 0003: Three-Token Cloudflare Credential Model

## Status

Accepted

## Date

2026-09-13

## Context

CI, attended operator work, and agent audits have different authority and lifecycle needs. Reusing
one credential across them would give every context the broadest permissions and couple rotation
or failure in one path to all other paths.

## Decision

Use three separate Cloudflare credentials:

- A read-only CI token stored as a GitHub Secret, used by the read-only `Compliance Audit` workflow.
- An expiring, IP-allowlisted operator token stored in local `.env`, with edit permission for
  attended operations.
- An expiring, read-only agent token stored in `.env.agent` for explicitly provisioned audits.

An edit-capable token for guarded correction is separate from this model's CI token and is defined
by ADR 0001.

The [Cloudflare API Token Runbook](../cloudflare-api-token-runbook.md) is the source of truth for
scopes, setup, storage, verification, rotation, and troubleshooting procedures.

## Consequences

Each execution context receives only its intended authority, and a token can be rotated without
changing the other roles. Operators maintain three credential lifecycles and must provision agent
access explicitly.

## Alternatives considered

- One shared token simplifies setup but expands blast radius and couples unrelated workflows.
- Edit-capable agent credentials allow remediation but exceed the authority needed for audits.
- No agent credential prevents live audits even when an explicitly scoped read-only audit is
  appropriate.
