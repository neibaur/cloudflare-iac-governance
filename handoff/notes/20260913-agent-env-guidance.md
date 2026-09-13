# Handoff Note

- **Task ID:** 20260913-agent-env-guidance
- **Slot:** wt-03
- **Agent:** Claude
- **Branch:** agent/wt-03
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

Three files, exactly the three in scope.

**`docs/cloudflare-api-token-runbook.md`** — the "Installing it" guidance under "The agent worktree
token" was wrong in both directions and is replaced.

- `GOOGLE_SHEET_ID` is now listed in the `.env.agent` sample block, with the reason: it is an
  identifier, not a credential. `scripts/aggregate_to_sheets.py` reads it to address a spreadsheet;
  it opens nothing on its own. The credential that actually gates Sheets work is
  `service_account.json`, and that still stays out of worktrees. Withholding the sheet id blocked
  legitimate work while protecting nothing.
- `FIX_DETECTED_GAPS` is documented as optional and locally inert. No Python in this repository
  reads it — it is consumed only by GitHub Actions as `vars.FIX_DETECTED_GAPS` in
  `.github/workflows/terraform-ci.yml`. The doc now says that plainly rather than implying the
  variable is a local remediation gate.
- New subsection **"Why the file separation earns its keep"**. The honest position: while `.env`
  and `.env.agent` hold the same read-only token the separation is nominal. Its value is latent —
  it is the only thing that stops every worktree silently inheriting edit capability the moment an
  edit-capable token is written to `.env`. Faster TTL on the agent token is named as the secondary
  benefit it actually is.
- The `service_account.json` bullet under "What this does not solve" gained one clause noting that
  a present `GOOGLE_SHEET_ID` does not weaken that control.

**`handoff/notes/20260912-gitleaks-precommit-hook.md`** — decision 6 (the "Superseded 2026-09-13"
item about a removed inline `gitleaks:allow` comment) is deleted outright and the following item
renumbered 7 to 6. The list now runs 1-6 with no gap. The deleted item recorded nothing that is
true of the current code, so nothing was carried forward.

**`handoff/README.md`** — new section "Documentation rule: delete, do not annotate", placed after
"File naming" and before the safety rules. States that stale documentation is deleted rather than
marked superseded, that a useful lesson gets carried into the currently-correct document, and that
workers write as if currently true with no changelog framing. The rationale is specific to this
repository: multiple agents, some lower-capability, any of which may read a note without reading
the correction that follows it.

## What was NOT done

- `scripts/bootstrap-worktree.ps1` was not touched. Another slot owns it concurrently. Note that
  its `-WithCloudflareToken` path is what materializes `.env` in a worktree from `.env.agent`; the
  runbook now documents a third variable in that file, but nothing in the bootstrap script needed
  to change for that.
- No Python or Terraform gate was run. The change is three Markdown files; `run_all_checks` and
  `terraform validate` have nothing to act on.
- No credentials were acquired. Bootstrap was run with no secret flags. No `.env`, `.env.agent`,
  `service_account.json`, or `*.tfvars` was read, copied, or displayed. No live API call was made.

## Verification

```
$ .\scripts\bootstrap-worktree.ps1          (no secret flags)
  -> "No secrets copied." ; "Bootstrap complete."

$ .venv\Scripts\detect-secrets.exe scan --baseline .secrets.baseline
  -> exit 0
$ python -c "json.load('.secrets.baseline')['results']"
  -> {}    (empty)
$ git checkout -- .secrets.baseline
  -> baseline byte-identical to HEAD

$ git commit            (core.hooksPath = .githooks, gitleaks hook ACTIVE)
  -> passed, no findings, --no-verify NOT used
  -> d062ec4 docs: correct .env.agent guidance and establish delete-don't-annotate rule

$ git status --porcelain --untracked-files=all
  -> empty
```

Renumbering checked by listing the ordered items in the Decisions section of the 2026-09-12 note:
1 through 6, sequential, no duplicate or missing number.

## Files changed

- `docs/cloudflare-api-token-runbook.md`
- `handoff/notes/20260912-gitleaks-precommit-hook.md`
- `handoff/README.md`

## Decisions and assumptions

1. **`GOOGLE_SHEET_ID` was added to the sample `.env.agent` block, not merely permitted in prose.**
   A sample block is what gets copied. Leaving the variable out of it while arguing for it in the
   paragraph below would have reproduced the original problem in softer form.

2. **The separation argument went into its own `###` subsection rather than into "Why a separate
   token".** That existing section argues blast radius — why the agent token is read-only. This is
   a different claim, about why two files exist when they may hold identical contents, and it only
   makes sense next to the file being created.

3. **The documentation rule was placed in `handoff/README.md`, not `AGENTS.md`.** The spec named
   `handoff/README.md` and the rule is about handoff notes and the multi-agent workflow, which is
   what that file governs. `AGENTS.md` remains authoritative for repository-wide rules and was not
   touched.

4. **Nothing was carried forward from the deleted lesson.** It described a `gitleaks:allow` comment
   that no longer exists next to a literal key that no longer exists. The current-state fact — the
   block-test recipe generates its key at run time — is already documented where it belongs, in
   `docs/agent-worktree-security.md`.

## Risks / follow-ups

- The runbook's claim that `FIX_DETECTED_GAPS` is read only by CI is true of the repository as it
  stands. If a future script starts reading it locally, this paragraph is the first thing that goes
  stale — and under the rule established here, it gets rewritten, not annotated.
- `handoff-live/status/wt-03.md` previously carried a follow-up asking someone to fix the stale
  lesson 6. That is now done; the status file is rewritten to reflect current state.
- The delete-don't-annotate rule is documented but not enforced by any check. It relies on workers
  reading `handoff/README.md`, which the lifecycle already requires.

## For the next worker

If you provision a worktree that needs Sheets work, `GOOGLE_SHEET_ID` will now be present in
`.env.agent` and will reach the worktree. That is intended and is not a credential. It still does
not let you run the Sheets sync — `service_account.json` is deliberately absent, and that work is
brokered per `handoff/README.md`.

If you find documentation that is wrong, delete the wrong part. Do not add a note saying it is
wrong. That is now a repository rule, written down in `handoff/README.md`.
