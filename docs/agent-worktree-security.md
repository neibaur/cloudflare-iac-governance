# Agent Worktree Security

How this repository keeps credentials out of git while multiple AI agents commit in parallel
worktrees, what each control actually covers, and — importantly — what none of them cover.

## The threat

Five agent worktrees (`worktrees/wt-01` .. `wt-05`) share one `.git` directory and one working
copy of this repository's real configuration. Agents run shell commands, read files, and commit.
The realistic failure modes are, in rough order of likelihood:

1. An agent stages a file it should not have — a real `.tfvars`, a report containing zone IDs, a
   pasted token in a doc example — and commits it.
2. An agent is handed a credential to do its job and then echoes it into a log, a handoff note,
   or a commit message.
3. A credential broader than the task needs is exposed, so the blast radius of any leak is the
   whole account rather than one zone.

The controls below are ordered by how much they actually buy you.

## Layer 1 (primary): scoped, short-lived credentials

This is the control that matters most, because it is the only one that limits the *damage* of a
leak rather than the *probability* of one.

- Give agent work a Cloudflare API token scoped to the minimum zones and permissions the task
  needs — read-only wherever the task is an audit or a plan.
- Prefer short expiry. A token that expired yesterday is not a finding, it is a non-event.
- Keep real values in GitHub Secrets or a local git-ignored file (`terraform/terraform.tfvars`,
  `.env`). Never in tracked files, and never in `terraform/ci.auto.tfvars`, which is mock CI data
  only.
- Rotate on any suspicion. Rotation is cheap; a history rewrite is not.

`AGENTS.md` is authoritative on secret handling and is the rule set agents are held to.

## Layer 2: the pre-commit gate (`.githooks/pre-commit`)

A local hook that blocks the commit itself. It is the backstop for "the agent did not follow
instructions", because it does not depend on the agent cooperating.

What it does:

- Scans **only the staged change set** (`gitleaks git --staged`), not the working tree and not
  history, so it stays fast enough to run on every commit.
- Uses the repository's `.gitleaks.toml`, so local results match the CI gitleaks gate.
- Exits non-zero on any finding and prints **file, line, and rule id only**. The matched value is
  never printed, never logged, and never left behind in a report file.
- **Fails closed.** No scanner on `PATH` means the commit is refused, not allowed. A gitleaks
  crash or a broken config is treated as "unscanned", not as "clean".
- Falls back to `detect-secrets` against `.secrets.baseline` when gitleaks is missing, after a
  self-check that proves the fallback scanner actually works.
- Names `git commit --no-verify` in its failure message, together with a warning that using it on
  a real finding writes the credential into history permanently.

What it does **not** do: see [Honest limits](#honest-limits).

## Layer 3: CI

Gitleaks runs in `.github/workflows/` on pull requests. The local hook is a faster, earlier copy
of that check, not a replacement for it — a contributor who never installs the hook, or who uses
`--no-verify`, is still caught at the pull request. Treat a CI gitleaks failure as
release-blocking until reviewed and remediated.

## Honest limits

State these plainly rather than letting the hook create false confidence.

- **Nothing here stops a model from READING a secret it was given.** If an agent is handed a
  Cloudflare token so it can run a plan, it has the token. A commit-path scanner is irrelevant to
  that fact.
- **Nothing here stops a secret from entering a provider transcript.** The moment a credential
  appears in a tool result, a shell output, or a pasted file, it has left this machine and is in
  the model provider's logs. It must be treated as disclosed and rotated. This is precisely why
  Layer 1 — scoping and short expiry — is the primary control and this hook is only a backstop.
- **The hook only sees `git commit`.** It does not cover pushing an already-made commit,
  `git commit --no-verify`, `git stash`, file uploads, chat pastes, or anything never staged.
- **Detection is pattern-based.** Gitleaks finds credential shapes it has rules for. A value with
  no distinctive format — an account id, a zone id, a customer domain — can pass cleanly. The
  `AGENTS.md` rule against committing real infrastructure values is doing that work, and no tool
  enforces it.
- **A worktree whose branch lacks `.githooks/` runs no hook at all, silently.** Git does not treat
  a missing hooks directory as an error. Coverage requires `.githooks/` to be merged into every
  branch that gets committed on.

## Install

> **Scope warning.** `core.hooksPath` is stored in the shared repository config. The primary clone
> and every worktree share one `.git` directory, so this single setting changes commit behaviour
> in **all** slots at once — including slots where another agent is mid-task. Do not install it
> while parallel agent work is in flight. The orchestrator installs it after the agent branches
> have merged.

```powershell
# from the primary clone, after merging
pwsh -File scripts/install-git-hooks.ps1
```

The script sets `core.hooksPath` to the relative path `.githooks`. Git resolves a relative
`core.hooksPath` against the top level of the working tree the hook runs in, so one setting
resolves correctly to each worktree's own `.githooks` copy. The script then verifies the setting
took effect and lists every working tree it now governs, flagging any worktree whose branch does
not contain `.githooks/`.

### Verify

```powershell
git config --get core.hooksPath     # -> .githooks   (no output means NOT installed)
```

### Uninstall

```powershell
pwsh -File scripts/install-git-hooks.ps1 -Uninstall
```

Both directions are idempotent. Installing over a `core.hooksPath` that points somewhere else
refuses unless you pass `-Force`.

## Test that it actually blocks

Use an obviously fake credential. Never test with a real one — a test commit that lands anyway is
a real leak.

```bash
printf 'aws_access_key_id = "AKIAQYLPMN5HZ3TX4RWD"\n' > scratch-leak.txt   # gitleaks:allow
git add scratch-leak.txt
git commit -m "should be blocked"     # expect: COMMIT BLOCKED, exit 1
git reset scratch-leak.txt && rm scratch-leak.txt
```

Gitleaks' default config allowlists AWS's published documentation key `AKIAIOSFODNN7EXAMPLE`, so
that particular string will **not** trigger a finding. Use some other fake `AKIA` plus 16
characters, as above.

You can also exercise the hook without installing it, which is the right move while other agents
are working:

```bash
sh .githooks/pre-commit ; echo "exit=$?"
```

## False positives

In order of preference:

1. **Fix the content.** Use an obvious placeholder (`your-scoped-token`, `your-account-id`) rather
   than a realistic-looking fake. `.gitleaks.toml` already allowlists that placeholder vocabulary
   in `.env.example`, `README.md`, `AGENTS.md`, and the quality workflow.
2. **Scope an allowlist entry** in `.gitleaks.toml` — pin it to a path *and* a regex, so it cannot
   silently exempt a future real secret in the same file.
3. **Inline `gitleaks:allow`** as a comment on the offending line. Narrowest scope, but invisible
   in review unless someone reads that line.
4. **`git commit --no-verify`** — last resort, and only after reading the staged diff yourself.
   This leaves no record that the gate was bypassed, so prefer options 1-3.

On the `detect-secrets` fallback path, update the baseline instead:

```powershell
detect-secrets scan --baseline .secrets.baseline
detect-secrets audit .secrets.baseline
```

Preserve `.secrets.baseline`; it is the local pre-flight input, while gitleaks is the enforcement
gate.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Commit succeeds with no scan output | `core.hooksPath` unset, or the branch has no `.githooks/` | `git config --get core.hooksPath`; merge `.githooks/` into the branch |
| "No secret scanner is available on PATH" | Neither gitleaks nor detect-secrets found | `winget install gitleaks` |
| "detect-secrets ... failed its self-check" | Broken console script: moved venv, missing interpreter | Install gitleaks, or `pip install --force-reinstall detect-secrets` |
| "gitleaks exited with an unexpected status" | Malformed `.gitleaks.toml` | Run `gitleaks git --staged --config .gitleaks.toml --no-banner` to see the real error |
| Hook fails with `bad interpreter` or `^M` | Hook checked out with CRLF line endings | `.gitattributes` pins `eol=lf` repo-wide; re-checkout the file |
| Hook feels slow | Cold start of the gitleaks binary, often antivirus scanning it | Expect roughly 1-3 s per commit on Windows; add an AV exclusion if intolerable |
