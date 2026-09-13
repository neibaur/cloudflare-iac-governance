# Handoff Note

- **Task ID:** 20260913-secret-fixture-hygiene
- **Slot:** wt-03
- **Agent:** Claude
- **Branch:** agent/wt-03
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

Removed every literal secret-shaped AWS access-key string from tracked files, without losing the
operational knowledge those fixtures encoded.

`docs/agent-worktree-security.md`, "Test that it actually blocks":

- The block-test recipe no longer embeds a fixture key. It now generates one at run time:
  `key="AKIA$(LC_ALL=C tr -dc 'A-Z0-9' < /dev/urandom | head -c 16)"`, writes it to the scratch
  file, and unsets it on cleanup. The recipe is still copy-pasteable end to end, and the file
  itself contains nothing a scanner can match.
- Added a short sentence stating *why* the doc holds no literal key, so a future editor does not
  helpfully paste one back in.
- Removed the inline `gitleaks:allow` comment — it guarded a literal that no longer exists, and a
  stale allowlist comment is its own hazard.
- The AWS-documentation-key warning was kept and sharpened, now as a blockquote. It names the key
  descriptively (`AKIA…EXAMPLE`, begins `AKIAIOSF…`, ends `…EXAMPLE`) rather than quoting it, and
  states the failure mode plainly: gitleaks allowlists it by design, so it yields a **false pass**
  and the reader wrongly concludes the hook is broken.
- Also added the manual alternative ("any `AKIA` plus 16 uppercase letters or digits of your own
  invention") so the hand-typing path is still documented.

`handoff/notes/20260912-gitleaks-precommit-hook.md` (historical record — literal only):

- Lesson 7's heading changed from the verbatim key to ``The `AKIA…EXAMPLE` documentation key``.
  The body is unchanged in wording; the paragraph was re-wrapped to the file's 100-col style, and
  the now-redundant restatement of the key name in the heading was avoided. No other content in
  that note was touched.

## What was NOT done

- `.gitleaks.toml` and `.secrets.baseline` were not modified, by design. The baseline is
  byte-identical to what was already committed.
- Lesson 6 of the 2026-09-12 note still says the doc's fake key "carries an inline
  `gitleaks:allow`". That is now historically true but presently stale. It was left alone because
  the spec restricts that file to the literal-string change only. Flagging it rather than
  silently editing it.
- No secrets acquired. Bootstrap run with no secret flags; no `.env` / `.env.agent` / tfvars /
  service-account material read, copied, or printed. No live API calls. No terraform apply.

## Verification

`detect-secrets` 1.5.0 from the freshly bootstrapped worktree venv.

Before the edits the scan added three findings to the baseline (reproduced, then reverted):

```
+  "results": {
+        "type": "AWS Access Key",
+        "filename": "docs\agent-worktree-security.md",
+        "line_number": 125
+        "type": "AWS Access Key",
+        "filename": "docs\agent-worktree-security.md",
+        "line_number": 131
+        "type": "AWS Access Key",
+        "filename": "handoff\notes\20260912-gitleaks-precommit-hook.md",
+        "line_number": 166
```

After the edits, `.venv\Scripts\detect-secrets.exe scan --baseline .secrets.baseline` produced
this and only this diff:

```
@@ -90,6 +90,10 @@
     {
       "path": "detect_secrets.filters.allowlist.is_line_allowlisted"
     },
+    {
+      "path": "detect_secrets.filters.common.is_baseline_file",
+      "filename": ".secrets.baseline"
+    },
     {
       "path": "detect_secrets.filters.common.is_ignored_due_to_verification_policies",
       "min_level": 2
@@ -123,5 +127,5 @@
     }
   ],
   "results": {},
-  "generated_at": "2026-04-29T20:37:10Z"
+  "generated_at": "2026-09-13T11:42:55Z"
 }
```

`"results": {}` — empty, as required. The two remaining hunks are noise, not findings: a filter
entry that detect-secrets 1.5.0 writes into every baseline it regenerates, and the timestamp. The
file was then reverted with `git checkout -- .secrets.baseline`; `git status` confirms it clean.

Other checks:

```
gitleaks git --staged --config .gitleaks.toml --no-banner --redact --exit-code 2
  -> INF no leaks found, exit 0        (gitleaks 8.30.1)

git config --get core.hooksPath -> .githooks   (hook IS active in this worktree)
git commit                      -> succeeded, hook passed, --no-verify NOT used
git status --porcelain --untracked-files=all -> clean
```

## Files changed

- `docs/agent-worktree-security.md`
- `handoff/notes/20260912-gitleaks-precommit-hook.md`
- `handoff/notes/20260913-secret-fixture-hygiene.md` (this note)

## Decisions and assumptions

- **Generate the key instead of placeholder-ing it.** The spec suggested `AKIA` plus a bracketed
  description. A run-time generator was chosen instead because it keeps the recipe literally
  executable — copy, paste, watch it block — which a `<PLACEHOLDER>` does not. The bracketed-
  placeholder idea survives as the prose fallback for hand-typing. `/dev/urandom` and `tr` are
  available in Git Bash, which is the shell the rest of this doc's `bash` blocks assume.
- **The warning is preserved without any matchable string.** `AKIA…EXAMPLE`, `AKIAIOSF…` and
  `…EXAMPLE` are all shorter than the 16-character tail the AWS rules require, so none of them
  match gitleaks or detect-secrets. They are, together, enough for a reader to recognize the key
  the moment they reach for it. The meaning did not have to be dropped.
- **Lesson 6 staleness left in place** rather than corrected — see "What was NOT done".

## Risks / follow-ups

- If anyone later adds a literal fake key back into these docs "for clarity", detect-secrets will
  flag it again and the baseline will grow. The added sentence in the doc is the guardrail.
- Lesson 6 of the 2026-09-12 note is now stale (see above). One-line fix for whoever owns that
  file next, if the orchestrator wants it corrected.
- `detect-secrets` is confirmed working again in this worktree's venv (1.5.0). The
  "detect-secrets is broken on this machine" follow-up from the 2026-09-12 note is resolved for
  the worktree venv; whether the operator's primary-clone venv is also repaired was not checked
  from here.

## For the next worker

Nothing is blocked. The commit is on `agent/wt-03` and is NOT pushed and NOT merged.

If you are testing the pre-commit hook: use the generator in
`docs/agent-worktree-security.md` → "Test that it actually blocks". Read the blockquote under it
before you reach for a key you remember from AWS's docs — that one passes on purpose and will
cost you an hour.
