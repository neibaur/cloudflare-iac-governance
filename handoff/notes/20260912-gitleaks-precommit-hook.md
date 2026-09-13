# Handoff Note

- **Task ID:** 20260912-gitleaks-precommit-hook
- **Slot:** wt-03
- **Agent:** Claude
- **Branch:** agent/wt-03
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

Three new files, exactly the three in scope. Nothing else in the repo was touched.

**`.githooks/pre-commit`** — POSIX sh, fail-closed staged-diff secret scanner.

- Primary path: `gitleaks git --staged --config .gitleaks.toml --no-banner --redact
  --exit-code 2 --report-format json --report-path <tmp>`, with gitleaks' own stdout/stderr
  discarded. Findings are printed from the JSON report as `file:line [rule: id]` plus the rule
  description. The `Match` and `Secret` fields are never read, so no matched value can reach the
  terminal even if `--redact` were to fail.
- `--exit-code 2` is the load-bearing choice: it separates "leaks found" (2) from "gitleaks
  errored" (1), so a malformed config fails closed with an honest message instead of being
  reported as a finding.
- Fallback path: `detect-secrets-hook --baseline .secrets.baseline`, per file so the failure
  message can name the offending file.
- No-scanner path: refuses the commit with install instructions. Never silently allows.
- Every failure path names `git commit --no-verify` and warns that using it on a real finding
  writes the credential into history permanently.

**`scripts/install-git-hooks.ps1`** — sets `core.hooksPath` to the *relative* value `.githooks`,
verifies the read-back, then enumerates every working tree from `git worktree list` and flags any
whose branch lacks `.githooks/pre-commit`. Idempotent; `-Uninstall` clears the setting; `-Force`
is required to overwrite a `core.hooksPath` pointing elsewhere. The comment-based help leads with
the shared-`.git` scope warning.

**`docs/agent-worktree-security.md`** — layered model (scoped short-lived credentials as the
primary control, this hook as the commit-path backstop, CI gitleaks last), the honest limits
section, install/verify/uninstall commands, a block-test recipe using a fake AKIA key, a
false-positive playbook ordered by preference, and a troubleshooting table.

## What was NOT done

- **The hook is not activated.** `core.hooksPath` is untouched and still unset, by design and per
  the task spec: it lives in the shared repository config, so setting it would have changed commit
  behaviour for wt-02 and wt-04 mid-task. The orchestrator must run
  `pwsh -File scripts/install-git-hooks.ps1` after merging.
- **The spec's literal command `gitleaks protect --staged` was not used.** See Decisions.
- No Python or Terraform gate was run. The change adds no Python and no Terraform; `run_all_checks`
  and `terraform validate` have nothing to act on here.
- The `detect-secrets` fallback could not be verified end-to-end on a *passing* case, because
  detect-secrets is broken on this machine. See Risks.

## Verification

All of the following were run for real on this machine. gitleaks 8.30.1.

Syntax:

```
$ sh -n .githooks/pre-commit    ->  clean, exit 0
$ [PS] Parser::ParseFile(scripts/install-git-hooks.ps1)  ->  PARSE OK (0 errors)
```

BLOCKS a real `git commit` (fake AWS key `AKIA` + 16 chars in a scratch file, hook supplied
per-invocation via `git -c core.hooksPath=.githooks` so no config was written):

```
$ git -c core.hooksPath=.githooks commit -m "test: should never be created"

COMMIT BLOCKED: pre-commit secret scan

gitleaks flagged staged content:

    tmp_fake_secret_test.txt:1  [rule: aws-access-token]
        Identified a pattern that may indicate AWS credentials, ...

Override (deliberate, audited):  git commit --no-verify
...
COMMIT EXIT=1
$ git log --oneline -1   ->  unchanged, no commit created
```

ALLOWS a clean commit — the deliverables commit itself was made through the hook:

```
$ git -c core.hooksPath=.githooks commit -F - <<'MSG' ... MSG
COMMIT EXIT=0
37e07e0 feat(security): add fail-closed gitleaks pre-commit hook and installer
```

Full install/uninstall lifecycle, exercised in a throwaway git repo in the scratchpad (never in
this repo, never against the shared config), then deleted:

```
install          -> Set core.hooksPath = .githooks; Verified; worktree list printed; exit 0
install again    -> "Already installed; nothing changed"; exit 0
real git commit of clean file, hook installed        -> succeeded
real git commit of fake AKIA key, hook installed     -> COMMIT BLOCKED, exit 1, no commit
git commit --no-verify                               -> succeeded (override works as documented)
-Uninstall       -> "Removed core.hooksPath (was '.githooks')"; exit 0
-Uninstall again -> "already unset. Nothing to do"; exit 0
core.hooksPath=.otherhooks, then install (no -Force) -> refused, exit 1
same, with -Force                                    -> replaced, verified
```

Degraded paths, exercised by removing directories from `PATH` for a single invocation:

```
gitleaks removed, detect-secrets present  -> self-check trips, "install is broken ...
                                             Failing closed", exit 1
both removed                              -> "No secret scanner is available on PATH ...
                                             fails closed on purpose", exit 1
```

Speed: ~2.6 s wall clock for a one-file staged scan, essentially all gitleaks process start-up on
Windows. Documented as 1-3 s in the troubleshooting table.

Final state checks:

```
$ git config --get core.hooksPath   ->  no output, exit 1 (UNSET, as required)
$ git status --porcelain --untracked-files=all   ->  empty after cleanup
```

All scratch files (`tmp_clean_test.txt`, `tmp_fake_secret_test.txt`, `tmp_report.json`, the
scratchpad test repo) were removed.

## Files changed

- `.githooks/pre-commit` (new)
- `scripts/install-git-hooks.ps1` (new)
- `docs/agent-worktree-security.md` (new)

## Decisions and assumptions

1. **`gitleaks git --staged` instead of the spec's `gitleaks protect --staged`.** In 8.30.1
   `protect` is deprecated and hidden from `gitleaks --help`; `git --staged` is the supported
   spelling and its help text literally says "good for pre-commit". Both were verified to work
   against 8.30.1; the non-deprecated one was chosen so the hook does not break on a future
   removal. If `protect` is required for some reason, the swap is one line.

2. **`--exit-code 2`.** Without it, a gitleaks failure and a gitleaks finding both return 1 and
   are indistinguishable, which would either produce a bogus finding report or, worse, tempt a
   future maintainer into treating errors as passes.

3. **Findings are parsed from the JSON report, not from gitleaks' console output.** Flushing each
   record on its `Fingerprint` key (gitleaks emits it last) means key-ordering changes across
   gitleaks versions cannot desync the output. Note that in 8.30.1 `RuleID` comes *first* in the
   record, not last — an earlier draft that printed on `RuleID` emitted blank file/line.

4. **detect-secrets self-check probe.** `detect-secrets-hook` uses exit 1 for "found a secret" and
   has no distinct code for "I am broken". On this machine it exits 1 on *everything*, including
   `--version` and a known-clean file, so without the probe the fallback would have blocked every
   commit while claiming a finding. The probe scans a known-clean temp file first and reports a
   broken install honestly. It still fails closed either way.

5. **Relative `core.hooksPath` value (`.githooks`, not an absolute path).** Git resolves a relative
   `core.hooksPath` against the top level of the working tree the hook runs in, so a single shared
   setting resolves to each worktree's own copy. An absolute path would have pinned every worktree
   to the primary clone's hook.

6. **The fake AKIA key in `docs/agent-worktree-security.md` carries an inline `gitleaks:allow`.**
   Without it the doc's own example blocks the doc's own commit. `.gitleaks.toml` was deliberately
   not modified — it is outside this task's file ownership.

7. **The `AKIA…EXAMPLE` documentation key is useless as a test fixture.** Gitleaks' default
   config allowlists AWS's published documentation key, so the first block test produced a false
   pass. Documented in the doc so the next person does not lose the same ten minutes.

## Risks / follow-ups

- **detect-secrets is broken on this machine.** The console script at
  `cloudflare-iac-governance/.venv/Scripts/detect-secrets` exits 1 with zero output for every
  invocation, including `detect-secrets --version`. Likely a moved/stale venv shim. This does not
  affect the hook (gitleaks is present and is the primary path, and the fallback now detects and
  reports the breakage), but `AGENTS.md` tells contributors to run `detect-secrets scan --baseline
  .secrets.baseline` for local pre-flight, and that command currently does nothing useful. Worth a
  follow-up task to reinstall it.
- **Consequently, the detect-secrets fallback's happy path is unverified.** Its blocking and its
  self-check paths were verified; a genuine "clean file passes under detect-secrets" run was not
  possible here.
- **Hook coverage is per-branch.** A worktree whose checked-out branch does not contain
  `.githooks/` runs no hook and git says nothing about it. The installer prints a per-worktree
  warning for exactly this, but it is only accurate at install time.
- **~2.6 s per commit** on this machine. Fine for humans, noticeable for an agent making many
  small commits. Mostly antivirus scanning the gitleaks binary on each start.
- The hook was never invoked through an installed `core.hooksPath` *in this repository* — only via
  `git -c ...` per-invocation here, and via a real install in a disposable scratch repo. The
  orchestrator should make one deliberate block-test after activating.

## For the next worker

The gate is written but dormant. To turn it on, from the primary clone after merging every agent
branch:

```powershell
pwsh -File scripts/install-git-hooks.ps1
git config --get core.hooksPath     # expect: .githooks
```

Then confirm with one real block test using the recipe in
`docs/agent-worktree-security.md#test-that-it-actually-blocks`, and check the worktree list the
installer prints — any slot flagged "NO .githooks on its checked-out branch" is unprotected until
`.githooks/` reaches that branch.

To undo: `pwsh -File scripts/install-git-hooks.ps1 -Uninstall`.

If you need to change what gets flagged, edit `.gitleaks.toml` (owned elsewhere), not the hook —
the hook intentionally contains no rules of its own so local and CI results stay identical.
