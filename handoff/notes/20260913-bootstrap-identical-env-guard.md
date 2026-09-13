# Handoff Note

- **Task ID:** 20260913-bootstrap-identical-env-guard
- **Slot:** wt-02
- **Agent:** Claude
- **Branch:** agent/wt-02
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

`scripts/bootstrap-worktree.ps1` now warns when `.env.agent` and `.env` in the source clone carry
the same `CLOUDFLARE_API_TOKEN` value. Previously the only token warning fired when `.env.agent`
was absent, so an agent file created by copying `.env` produced a silent, clean-looking bootstrap
while the credential separation was nominal.

Two pieces landed:

- `Get-EnvValueHash -Path <file> -Key <name>` returns the SHA-256 hex digest of one key's value in
  a dotenv-style file, or `$null` when the key is absent or its value empty. It returns a digest
  and nothing else; the value never leaves the function. Parsing handles comment lines, an
  `export ` prefix, whitespace around `=`, matched surrounding single or double quotes, trailing
  whitespace/CR, and a repeated key (last assignment wins, matching dotenv loaders).
- In the `-WithCloudflareToken` branch, when `.env.agent` exists both files are hashed and compared.
  On a match the script prints a warning naming the consequence: the worktree carries exactly the
  operator's Cloudflare rights, and the day an edit-capable token is written to `.env`, every
  worktree bootstrapped this way silently inherits edit capability. It then continues; the copy
  still happens.

Only the token value is compared, not whole files — the two files legitimately differ in other
keys (in the real clone they do not, but the fixture case proves the distinction) and that is
exactly the case worth catching.

Output carries a 12-character hash prefix only. No token value is printed, logged, or written.

The help block gained a paragraph under `.PARAMETER WithCloudflareToken` describing the new
warning. No line in the help block begins with a dot.

## What was NOT done

Nothing in scope was skipped.

Not attempted, and out of scope: the script still does not verify that the `.env.agent` token is
actually read-only (that needs a live API call), and it does not compare `CLOUDFLARE_ACCOUNT_ID`
or any other key.

## Verification

All runs used Windows PowerShell 5.1 (`5.1.26100.9444`). No `terraform apply`, no live API calls.

Help block intact (this was the stated regression risk — verified, not assumed):

```
ParseErrors: 0
Synopsis: Provisions an agent worktree so a worker can run the repository quality gate.
ParamHelpCount: 8
ExampleCount: 4
DescLines: 1
```

`Get-Help .\scripts\bootstrap-worktree.ps1 -Full` renders the authored SYNOPSIS, DESCRIPTION, all
8 parameter descriptions and all 4 examples, including the new paragraph.

Four bootstrap runs, all with `-SkipVenv -Force`:

| Source clone | Condition | Result |
| --- | --- | --- |
| real primary clone | `.env` and `.env.agent` token identical | identical-token WARNING fired |
| throwaway fixture | different token values | no warning; copied `.env.agent -> .env` |
| throwaway fixture | no `.env.agent` | existing fallback WARNING fired unchanged |
| throwaway fixture | same token, other keys differ, `export`/quotes/spaces | identical-token WARNING fired |

Real primary clone (token value absent from output, as required):

```
WARNING: .env.agent and .env hold the SAME Cloudflare API token.
  Both resolve to token sha256 89ec68f6adaa (value not shown, never logged).
  The separation is nominal: this worktree gets exactly the Cloudflare
  rights the operator holds, not a narrowed subset. Today's token is
  read-only, so nothing is over-exposed yet -- but the day an
  edit-capable token is written to .env, every worktree bootstrapped
  this way silently inherits edit capability with no further signal.
  Fix: mint a separate read-only, narrowly scoped agent token and put
  it in .env.agent so the two files stop sharing a credential.
  Continuing with the bootstrap.
  copied  .env.agent -> .env
```

The normalization was cross-checked against an independent hasher. The fixture pair
`CLOUDFLARE_API_TOKEN=<v>` versus `export CLOUDFLARE_API_TOKEN = "<v>"  ` both produced prefix
`766d61449c14`, matching `sha256sum` of the bare value — so `export`, padding, quotes and trailing
whitespace are normalized away and the two files are correctly judged identical.

Repository quality gate, run in this worktree:

```
Ruff lint / Ruff format / mypy / Bandit: pass
71 passed; coverage 92.71% (required 75%)
All quality checks passed.
```

Secret hygiene. Every test run copied a `.env` into the worktree and it was deleted immediately
after each run. Final state:

```
$ Test-Path .env
False
$ git status --porcelain --untracked-files=all
(clean)
```

The throwaway fixtures lived outside the repository, in the session scratchpad, and were deleted.
They contained obvious placeholder strings, never a real token.

Gitleaks pre-commit hook ran on the commit and passed. `--no-verify` was not used. (Confirmed the
hook is wired in this worktree: `core.hooksPath=.githooks`, and it fails closed when no scanner is
on PATH, so a silent pass means it scanned and found nothing.)

## Files changed

- `scripts/bootstrap-worktree.ps1`

## Decisions and assumptions

- **Warn before copying, then copy anyway.** The spec calls this a warning, not a refusal, and the
  current token is read-only. Ordering the warning ahead of the `copied` line keeps the cause above
  the effect in the transcript.
- **Compare one key, not the file.** Whole-file hashing would miss the case where the files share a
  token but differ elsewhere, and would false-positive on a differing `GOOGLE_SHEET_ID`.
- **Digest, not value, crosses the function boundary.** `Get-EnvValueHash` returns a hex string; no
  caller can reach the value even accidentally. The value variable is nulled in a `finally`.
- **Literal string parsing only** — `Trim`, `StartsWith`, `IndexOf`, `Substring`, `-eq`. No
  `-match`, no `-replace`, no `-like`. A token is arbitrary text and may contain regex or wildcard
  metacharacters; this script has shipped that class of bug before.
- **No warning when either side lacks the key.** If `.env` is absent, or the key is missing or
  empty in either file, the comparison returns `$null` and stays silent. An absent operator `.env`
  is not a separation failure, and a missing key is a different problem than a shared credential.
- **12 hex characters of the digest** are printed. Enough to correlate two runs, useless as a
  credential, and it is a hash of a high-entropy secret rather than the secret.

## Risks / follow-ups

- The real clone's `.env` and `.env.agent` do currently share a token — the warning is firing for a
  real condition, not a test artifact. Fixing it means minting a separate scoped agent token; that
  is an operator action, outside this task.
- The guard only fires on the `-WithCloudflareToken` path when `.env.agent` exists. If the operator
  deletes `.env.agent`, behavior falls back to the older unrestricted-token warning, as intended.
- Detecting whether the agent token is genuinely read-only would need a live
  `/user/tokens/verify` call and token-permission inspection. Deliberately not done here; no live
  API calls were in scope.

## For the next worker

The help block is the fragile part of this file. In PowerShell 5.1 a single line whose first
non-whitespace character is a dot is read as an unknown help keyword and voids the *entire*
comment-based help block silently — `Get-Help` then falls back to auto-generated output that still
looks plausible. After any edit to the block, re-check that `Get-Help -Full` returns a non-empty
SYNOPSIS and all 4 examples. Referring to `.env` at the start of a help line is the trap.

`Get-EnvValueHash` is generic over key name. If a future task needs to compare
`CLOUDFLARE_ACCOUNT_ID` or a GCP field across the same two files, it takes a `-Key` argument
already — no new parsing code needed.
