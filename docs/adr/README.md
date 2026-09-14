# Architecture Decision Records

An architecture decision record (ADR) captures a repository-wide decision, its context, and its
lasting tradeoffs. ADRs use these status values:

- **Proposed:** under consideration and not yet binding.
- **Accepted:** current and binding.
- **Superseded:** replaced by a later decision.

ADR filenames start with a four-digit number assigned in sequence, followed by a concise slug.
Numbers are never reused. An accepted ADR changes only through a new ADR that supersedes it. In
that case, delete the old ADR and carry its lasting context into the replacement, following the
repository's delete-don't-annotate rule.

## Index

- [0001: Terraform state and guarded drift remediation](0001-terraform-state-and-drift-remediation.md) — Accepted
- [0002: Single-trunk branching](0002-single-trunk-branching.md) — Accepted
- [0003: Three-token Cloudflare credential model](0003-three-token-credential-model.md) — Accepted
- [0004: Agent worktree and handoff model](0004-agent-worktree-and-handoff-model.md) — Accepted
- [0005: Agent cost and authority limits](0005-agent-cost-and-authority-limits.md) — Proposed
