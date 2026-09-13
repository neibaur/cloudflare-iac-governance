# Architecture Decision Record 0002

## Title

Single-Trunk Branching

## Status

Accepted

## Date

2026-09-13

## Context

Infrastructure changes need a clear production line, review before integration, and checks that
prevent unsafe or unverified commits from becoming the deployed definition. Parallel agent and
human work also needs short-lived isolation without creating competing production branches.

## Decision

`main` is the only long-lived branch. Work uses short-lived branches and enters `main` through
pull requests. The `main protection` ruleset requires pull requests, linear history, resolved
review threads, and the required checks `quality`, `CodeQL`, and `Gitleaks history scan`.

## Consequences

Every production change has a reviewable pull request and a common validation path. Contributors
must keep branches focused and current enough to merge linearly. Temporary branches are deleted
after merge rather than becoming alternate lines of development.

## Alternatives considered

- Long-lived development or release branches add synchronization and drift without a current
  repository need.
- Direct pushes to `main` reduce review and validation guarantees.
