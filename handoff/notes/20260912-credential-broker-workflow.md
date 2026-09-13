# Handoff Note

- **Task ID:** 20260912-credential-broker-workflow
- **Slot:** wt-04
- **Agent:** Claude
- **Branch:** agent/wt-04
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

Added the credential-brokering half of the handoff protocol: the operator runs the credentialed
command, the worker gets the sanitized output, and no credential ever moves into a worktree.

- `scripts/export-audit-snapshot.ps1` (new). Runs the existing read-only audit path
  (`python run_tools.py --audit`), sanitizes `reports/security_compliance_report.csv`, and writes
  `../handoff-live/inbox/audit-snapshot-<UTC>[-<label>].csv`. Prefers `.venv\Scripts\python.exe`
  and falls back to `python`.
  - **Guard.** Refuses to run from an agent worktree, detected two ways: the repo root path
    matching `\worktrees\`, and `git rev-parse --absolute-git-dir` differing from the resolved
    `--git-common-dir`. Also refuses if `.env` is absent. Both refusals print why and throw; they
    do not fail silently. The guard runs before anything else, including before `-DryRun`.
  - **Sanitizing.** Reads `.env` to collect values for keys matching
    `TOKEN|SECRET|KEY|PASSWORD|ACCOUNT_ID` and removes exact occurrences, replacing each with
    `[REDACTED:<KEY_NAME>]`. Those values are used as match needles only — never printed, logged,
    or written. A catch-all regex then scrubs `[A-Za-z0-9_-]{40,}` as token-shaped. Domain names
    and 32-hex zone IDs survive by design; they are shorter than the catch-all threshold.
  - **`-DryRun`** prints resolved paths, the command, and the redaction policy, then returns
    without invoking Python or writing anything.
  - Closing output states plainly that the file holds real infrastructure identifiers, lives in
    untracked `handoff-live/`, and must never be committed or pasted anywhere.
- `handoff/templates/broker-request.md` (new). What the worker needs, why, the read-only command it
  believes should run, what it will do with the result, plus a four-item confirmation checklist.
  Explicitly routes write/state-changing requests to human escalation rather than brokering.
- `handoff/README.md`. Appended a `## Credential brokering` section (default zero-credential
  posture, when to file a request, where snapshots land, snapshots are real data and never get
  committed). Append-only: `git show --stat` reports 51 insertions and 0 deletions.

## What was NOT done

- **No end-to-end run against the real Cloudflare API.** Forbidden by the spec and correct: this
  worktree has no credentials and I did not acquire any. The sanitizer was proven against a
  disposable fake clone instead (see Verification). The first real invocation will be the
  operator's.
- No queue, daemon, registry, or generalized broker framework. Deliberate — the spec asked for one
  protocol section, one template, one script.
- Did not run `scripts/run_all_checks.py`. No Python changed, and this worktree has no `.venv`
  (not bootstrapped). Nothing in the diff is reachable by that gate.
- No Terraform touched, so no fmt/validate/plan run.

## Verification

All run under Windows PowerShell 5.1 (5.1.26100.9444). No network calls were made at any point.

Parse check and help rendering:

```
[Parser]::ParseFile(...) -> No parse errors
Get-Help .\scripts\export-audit-snapshot.ps1 -Full -> renders NAME/SYNOPSIS/SYNTAX/DESCRIPTION,
  all three PARAMETERS, NOTES, and both EXAMPLES. No errors.
```

Worktree guard, run from wt-04, both with and without `-DryRun`:

```
REFUSING TO RUN: this is an agent worktree, not the primary clone.
  Path          : C:\...\worktrees\wt-04
  Worktree by   : path=True gitdir=True
CAUGHT: export-audit-snapshot.ps1 must run in the primary clone.
```

Both detectors fired independently (`path=True gitdir=True`), so the guard survives a worktree
placed outside a `worktrees/` directory.

Happy path, exercised in a throwaway `git init` repo in the scratchpad with a fake `.env` and a
stub `run_tools.py` that writes a CSV deliberately leaking both fake secrets. No real credentials
and no API involved:

```
-DryRun  -> printed resolved paths, "no Cloudflare API call made, no snapshot written",
            files in inbox after DryRun: 0

full run -> Data rows: 3, Redactions: 2
snapshot:
  domain_name,zone_id,ssl_mode,always_use_https,security_level,bot_fight_mode,is_compliant
  example.test,023e105f4ecef8ad9ca31a8372d0c353,full,on,medium,on,1
  leak.test,[REDACTED:CLOUDFLARE_ACCOUNT_ID],full,on,medium,on,1
  tok.test,[REDACTED:CLOUDFLARE_API_TOKEN],off,off,low,off,0

PASS: account id absent
PASS: token absent
PASS: real-shaped zone id preserved
```

Scratch clone deleted afterwards. `git status --porcelain --untracked-files=all` clean apart from
this note.

## Files changed

- `scripts/export-audit-snapshot.ps1` (new)
- `handoff/templates/broker-request.md` (new)
- `handoff/README.md` (appended `## Credential brokering`; nothing removed or restructured)
- `handoff/notes/20260912-credential-broker-workflow.md` (this note)

## Decisions and assumptions

- **Redaction uses `.env` values as needles rather than pattern-matching alone.** A Cloudflare
  account ID and a zone ID are both 32-hex — indistinguishable by shape. Zone IDs must survive,
  so the account ID has to be removed by exact value. That requires reading `.env`. The script
  reads it, matches against it, and never emits it. If this makes anyone nervous, the alternative
  is losing zone IDs, which defeats the export.
- **The snapshot is a clean CSV with no warning banner inside it.** A `#` comment line would be
  parsed as a data row by `csv.DictReader` and by every spreadsheet tool. The warning is instead
  loud in the console output, in the template, and in the README.
- **Snapshots are not auto-deleted.** The README says the operator deletes them when the task is
  done. A self-cleaning script would be the start of the lifecycle framework the spec said not to
  build.
- **The `{40,}` catch-all assumes no legitimate 40+ character unbroken alphanumeric field.** True
  for the current CSV schema: domains contain dots, zone IDs are 32 chars. If a new column ever
  carries long opaque values, they will be redacted. Failing closed is the right direction here.

## Risks / follow-ups

- Untested against a real `.env` and real API output. Shape of the CSV is fixed by
  `SECURITY_CSV_HEADERS` in `scripts/cloudflare_client.py`, so the risk is low, but the first real
  run deserves eyes on the output before it is handed to a worker.
- The script sanitizes the CSV only. `run_tools.py --audit` also prints a summary table to the
  console, which the operator sees directly. That console text is not captured or sanitized — it
  contains no credential, but an operator who pastes it into chat bypasses the snapshot path.
- `handoff-live/inbox/` accumulates snapshots. No retention policy exists beyond the README asking
  the operator to delete them.
- Nothing has exercised the broker request template end to end. The first real request will
  probably reshape it.

## For the next worker

The guard is the load-bearing part. If you are in a worktree and this script refuses, the answer
is never to bootstrap secrets into your slot — file a broker request from
`handoff/templates/broker-request.md` and set your status to `BLOCKED` with reason
`awaiting broker`.

To re-verify the sanitizer without credentials, repeat the fake-clone recipe under Verification:
`git init` a temp dir, drop in a fake `.env` and a stub `run_tools.py` that writes
`reports/security_compliance_report.csv`, then run the script there. It never touches the network.
