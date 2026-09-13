# Architecture Decision Record 0004

## Title

Agent Worktree and Handoff Model

## Status

Accepted

## Date

2026-09-13

## Context

Multiple agents need isolated branches and working directories while sharing one repository.
Coordination artifacts must be immediately visible across worktrees without becoming persistent,
potentially stale instructions. Credentials and real infrastructure data require stronger
boundaries than prompt guidance alone provides.

## Decision

Use five pinned worktrees and the lifecycle defined in [the handoff protocol](../../handoff/README.md).
Live task coordination stays in `handoff-live/` outside the repository, and completion notes are
never committed. Workers have zero credentials by default; when real infrastructure data is
necessary, the operator brokers sanitized output rather than copying credentials into a worktree.
Stale or superseded documentation is deleted, not annotated.

## Consequences

Agents can work concurrently on disjoint files with durable Git isolation. Ephemeral coordination
does not accumulate as misleading repository guidance, and credentials remain centralized. The
operator owns task assignment, brokered data, integration, and cleanup of live handoff artifacts.

## Alternatives considered

- A shared working directory makes concurrent edits and branch ownership unsafe.
- Committed completion notes create a growing body of instruction-like historical text.
- Copying operator credentials into worktrees gives agents unnecessary authority and disclosure
  risk.
