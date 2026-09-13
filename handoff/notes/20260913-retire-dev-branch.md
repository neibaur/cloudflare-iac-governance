# Handoff Note

- **Task ID:** 20260913-retire-dev-branch
- **Slot:** wt-05
- **Agent:** Codex
- **Branch:** agent/wt-05
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

Documented the single-trunk branch model in `AGENTS.md` and `README.md`, removed the retired branch from the CodeQL, quality, and secret-scan workflow triggers, and removed the duplicate README Governance section.

## What was NOT done

Nothing in scope was skipped. No Git branch was created, deleted, or renamed.

## Verification

The first Python quality-gate attempt reached pytest collection but failed because the execution environment did not define `APPDATA`; `gspread` raised `KeyError: 'APPDATA'`. The same command passed after setting `APPDATA` to the standard Windows roaming application-data path for the process.

```text
$env:APPDATA = [Environment]::GetFolderPath('ApplicationData'); .venv\Scripts\python scripts\run_all_checks.py
All checks passed!
Success: no issues found in 16 source files
No issues identified.
71 passed in 1.47s
Required test coverage of 75% reached. Total coverage: 92.71%
All quality checks passed.

terraform -chdir=terraform fmt -check -recursive
Exit code 0; no output.

Workflow YAML parse
Parsed 4 workflow YAML files successfully.

README Governance heading count
1
```

## Files changed

- `.github/workflows/codeql.yml`
- `.github/workflows/quality.yml`
- `.github/workflows/secrets.yml`
- `AGENTS.md`
- `README.md`
- `handoff/notes/20260913-retire-dev-branch.md`

## Decisions and assumptions

Kept non-branch uses of the string `dev`, including `requirements-dev.txt`, development-dependency prose, and `/dev/null`, as required by the task.

## Risks / follow-ups

- The maintainer still needs to perform any desired branch deletion.

## For the next worker

Review the single-trunk wording and workflow-trigger removals. The initial quality-gate environment issue and successful rerun are recorded above.
