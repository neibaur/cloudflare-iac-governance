# Handoff Note

- **Task ID:** 20260912-bootstrap-secret-scoping
- **Slot:** wt-02
- **Agent:** Claude
- **Branch:** agent/wt-02
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

`scripts/bootstrap-worktree.ps1` no longer has a single all-or-nothing secret switch. Secret
material is now opted into per category:

- `-WithCloudflareToken` provisions the worktree `.env`. It prefers `.env.agent` from the source
  clone (the restricted, read-only agent token) and falls back to the source clone's `.env` only
  after printing a loud multi-line warning that the operator's unrestricted token is being used.
  The destination is always written as `.env`, so python-dotenv and every existing code path work
  unchanged.
- `-WithTfvars` copies `terraform/terraform.tfvars` and `terraform/secrets.auto.tfvars`.
- `-WithServiceAccount` copies `service_account.json`, but only when `-IAcceptServiceAccountRisk`
  is also passed. Alone it prints a refusal explaining that the file is an unscoped GCP private
  key that cannot be narrowed per worktree, notes that the non-interactive session makes prompting
  impossible, and then continues with the rest of the bootstrap rather than aborting.
- `-WithSecrets` still works as a deprecated alias for `-WithCloudflareToken -WithTfvars`. It
  deliberately does NOT pull the service account, and it prints a deprecation notice naming the
  granular flags.

The `git check-ignore` safety net was kept and now iterates over the set of files the run actually
placed in the worktree (tracked in `$script:TouchedPaths`) instead of a hardcoded list, so it
stays correct as categories are added. `-SkipVenv`, `-Force`, `-SourceRepo`, the default
source-clone resolution, and the terraform init step all behave as before.

Two latent bugs in the existing file were fixed along the way:

1. `$RepoRoot = $RepoRoot -replace '/', '\'` is now `$RepoRoot.Replace('/', '\')`. The `-replace`
   operator treats its second argument as regex replacement text where a lone backslash is an
   escape character. This is presumably the escaping bug the spec warned about.
2. The comment-based help block contained a line starting with `.gitignore`. PowerShell 5.1's help
   parser reads any line beginning with a dot as a help keyword, hit an unknown one, and silently
   discarded the ENTIRE help block — `Get-Help -Full` was returning auto-generated syntax, not the
   authored help. The line was reworded and a comment in the block warns future editors.

## What was NOT done

- Nothing in the spec was skipped.
- `-WithServiceAccount` copying a *real* `service_account.json` could not be exercised, because the
  primary clone does not contain that file. The copy path was verified against a throwaway fixture
  source directory holding placeholder files. Same for `.env.agent` and
  `terraform/secrets.auto.tfvars`, neither of which exists in the primary clone yet.
- The repo-wide quality gate (`run_all_checks.py`, terraform fmt/validate/plan) was not run. This
  change touches one PowerShell script; no Python or Terraform source was modified, and running a
  plan was out of scope and carries the shared-state hazard the protocol warns about. `terraform
  init -backend=false` did run, as part of every bootstrap invocation under test, and succeeded.

## Verification

All runs on Windows PowerShell 5.1.26100.9444 (`powershell.exe`), in the wt-02 worktree.

```
# Parse + help
[Parser]::ParseFile(...)                -> PARSE OK
Get-Help .\scripts\bootstrap-worktree.ps1 -Full
  Synopsis: Provisions an agent worktree so a worker can run the repository quality gate.
  Params:   WithCloudflareToken, WithTfvars, WithServiceAccount,
            IAcceptServiceAccountRisk, WithSecrets, SourceRepo, SkipVenv, Force
  Examples: 4

# No flags (-SkipVenv)
  Terraform initialized.
  "No secrets copied. Opt in per category..." + the three flag names.  EXIT=0

# -WithServiceAccount alone (fixture source)
  REFUSED: -WithServiceAccount requires -IAcceptServiceAccountRisk. ...
  Continuing with the rest of the bootstrap.
  sa-file-present: False

# -WithServiceAccount -IAcceptServiceAccountRisk (fixture source)
  NOTE: placing an unscoped GCP private key in this worktree.
  copied  service_account.json
  Verified: all copied secrets are ignored by git.
  sa-file-present: True

# -WithSecrets (fixture source, which has .env.agent)
  DEPRECATED: -WithSecrets is an all-or-nothing bundle.
    Treating it as: -WithCloudflareToken -WithTfvars
  copied  .env.agent -> .env
  copied  terraform\terraform.tfvars
  copied  terraform\secrets.auto.tfvars
  env/tfvars/secrets-auto present: True/True/True    sa present: False

# -WithCloudflareToken, .env.agent absent (fixture, then again vs the real primary clone
# using default -SourceRepo resolution)
  WARNING: no .env.agent in the source clone.
    Falling back to .env, the operator's UNRESTRICTED Cloudflare token. ...
  copied  .env
  (second run, no -Force)  exists  .env (use -Force to overwrite)

# Cleanup
  removed .env; removed terraform\terraform.tfvars; fixture directory deleted
  git status --porcelain --untracked-files=all
   M scripts/bootstrap-worktree.ps1
```

No secret file contents were printed at any point; only filenames appear in output. Every secret
file copied during testing was deleted and `git status --porcelain --untracked-files=all` shows
only the script itself.

## Files changed

- `scripts/bootstrap-worktree.ps1`
- `handoff/notes/20260912-bootstrap-secret-scoping.md` (this note)

## Decisions and assumptions

- **Refusal, not failure.** `-WithServiceAccount` without the acknowledgement prints to the host
  and clears the flag rather than throwing. The spec asked for the bootstrap to continue, so the
  script still exits 0. A caller scripting around this cannot detect the refusal by exit code —
  it has to pass the acknowledgement flag deliberately, which is the intent.
- **`.env.agent` is never written into the worktree under that name.** It is copied to `.env`, per
  the spec, so downstream code needs no change. The console line reads `copied .env.agent -> .env`
  so the operator can see which token class landed.
- **check-ignore covers "placed", not strictly "copied".** A file that already existed at the
  destination and was left alone (no `-Force`) is still checked. That is deliberately broader than
  the spec's wording; verifying one extra path is free and a stale unignored secret is still a
  leak.
- **The `-Force` semantics are unchanged**: it both recreates the virtualenv and overwrites secret
  files. That coupling predates this task and was left alone.
- Terraform init runs before the secrets phase, exactly as before. It succeeded on every test run.

## Risks / follow-ups

- `.env.agent` does not exist in the primary clone yet, so every real bootstrap today takes the
  fallback path and hands agents the unrestricted operator token. The warning is now loud, but the
  actual fix is minting the restricted token. `docs/cloudflare-api-token-runbook.md` (untracked,
  orchestrator-owned) appears to cover this; the script does not reference that doc by path, to
  avoid pointing at a file that may not land.
- If a future editor adds a help line starting with a dot (e.g. `.env` or `.gitignore` at the start
  of a line), the entire comment-based help block silently vanishes again. There is an inline note
  in the help block, but nothing enforces it. A PSScriptAnalyzer rule or a tiny `Get-Help` smoke
  test in CI would catch it.
- No automated test covers this script. Everything above was verified by hand.

## For the next worker

Start at the `# ---- secrets (granular opt-in)` section. The flow is: resolve the three `$want*`
booleans at the top (including the `-WithSecrets` expansion and the service-account gate), then a
single `Copy-SecretFile` helper does source-exists / dest-exists / copy and appends to
`$script:TouchedPaths`, which the check-ignore net consumes. Adding a fourth secret category means
one `$want` flag, one `Copy-SecretFile` call, and one line in the "No secrets copied" hint block.

To test without touching real credentials, build a throwaway directory containing placeholder
`.env`, `.env.agent`, `service_account.json`, and `terraform/*.tfvars` files and pass it as
`-SourceRepo`. Always finish with `git status --porcelain --untracked-files=all` and delete
anything that landed in the worktree.
