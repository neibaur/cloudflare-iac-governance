# ADR 0005: Agent Cost and Authority Limits

## Status

Proposed

## Date

2026-09-13

## Context

Agent dispatch is easier to scale than human review. Unbounded parallel work increases review
queues, spend, and the chance that overlapping changes conflict. Automated launch also needs
explicit limits that cannot be relaxed by a worker.

## Decision

The operator launches workers manually; there is no automatic dispatch. Open agent pull requests
have a work-in-progress limit, while parallel tasks may proceed when their specs touch disjoint
files. The numeric limit remains an open question for the operator.

Agents never merge. They receive no secrets unless a task spec names a bootstrap flag.

The orchestrator integrates finished work as small pull requests grouped by concern, planned when the
batch's task specs are written. This is an encouraged default rather than an enforced limit: tightly
coupled changes may share a pull request, but unrelated concerns go into separate ones.

Any future scripted launch has a hard per-run spend cap and turn cap, deny-by-default permissions,
and no auto-merge. For Claude Code headless mode, the launch sets `--max-budget-usd` and
`--max-turns`. Orchestrators do not coordinate other orchestrators because review capacity, not
dispatch, is the bottleneck.

## Consequences

Concern-grouped pull requests keep each review within one reason for change, so gaps surface in one
review instead of across many rounds, at the cost of more pull requests to track and order.

Human review capacity governs throughput, and each automated run has bounded cost and authority.
The operator must choose and maintain a practical numeric pull-request limit before accepting this
decision.

## Alternatives considered

- Automatic dispatch maximizes concurrency but can outpace review and create overlapping work.
- Unbounded headless runs reduce launch configuration but expose spend and execution risk.
- Orchestrator hierarchies increase dispatch capacity without addressing the review bottleneck.
