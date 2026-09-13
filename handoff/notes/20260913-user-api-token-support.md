# Handoff Note

- **Task ID:** 20260913-user-api-token-support
- **Slot:** wt-02
- **Agent:** Claude
- **Branch:** agent/wt-02 (commit `7abfd51`, not pushed, not merged)
- **Status:** DONE
- **Completed:** 2026-09-13

## What was done

`scripts/cloudflare_client.py`:

- `verify_connection()` now tries `/accounts/{id}/tokens/verify` first and falls back to
  `/user/tokens/verify` when the first attempt fails in an auth-shaped way (code 1000, code 9109,
  or HTTP 400/401/403). A User API Token therefore verifies, which also unblocks `--audit` —
  `_list_zones()` -> `_assert_zone_read_permission()` -> `verify_connection()` runs as a
  precondition before any zone read.
- If both endpoints fail, a single `CloudflareAPIError` is raised naming both attempts and both
  underlying failures. Nothing is swallowed.
- A failure that is *not* auth-shaped (network error, malformed JSON, missing result object) is
  re-raised immediately without a second call, so a genuine outage is not disguised as a token
  problem.
- The account ID no longer appears in exception text. All client errors route through `_redact()`,
  which substitutes `REDACTED_ACCOUNT_ID` (`<redacted-account-id>`). The httpx `HTTPStatusError`
  cause is no longer chained, because httpx embeds the full request URL in its own message and that
  URL carried `CLOUDFLARE_ACCOUNT_ID` into tracebacks and CI logs.
- `CloudflareAPIError` gained `status_code` and `error_codes`. That is what lets the message
  distinguish **1000** (wrong endpoint for this token type, or a bad secret) from **9109**
  (expired, revoked, deleted, or IP-filtered). The old message blamed `CLOUDFLARE_ACCOUNT_ID` for
  both cases.
- Expiry semantics are unchanged: a successful verification can still carry `status: expired` or
  `disabled`, and callers still read `status`. Tests pin this for both endpoints.

`scripts/tests/test_cloudflare_token_verification.py` (new, 18 tests) covers account-token success,
user-token fallback (both via the 401 path and the HTTP-200/`success: false` path), both-endpoints-
fail, `expired` and `disabled` passthrough, no-retry on non-auth failure, the 1000 vs 9109 hint
text, error-code extraction, and two redaction tests that assert the account ID appears in neither
the message nor the rendered traceback.

`scripts/tests/test_auditor.py`: `test_verify_connection_reports_invalid_token_helpfully` used to
assert the message contained `CLOUDFLARE_ACCOUNT_ID`. That assertion enforced the bug, so it was
inverted — it now asserts the string is absent and that the 1000 hint is present.

`docs/cloudflare-api-token-runbook.md`:

- "Either type works for this project" was false before this commit. Corrected, with the version
  boundary stated explicitly (older checkouts lacking `USER_TOKEN_VERIFY_PATH` need an Account API
  Token; current `main` takes either), plus a note that the fallback fixes verification, not scopes.
- New "1000 vs 9109" subsection in the diagnosis area with a comparison table and the shorthand
  "1000 = wrong door, 9109 = the key no longer works".
- Verification section now documents both verify endpoints, the `curl` for `/user/tokens/verify`,
  the fallback behaviour, and the redaction placeholder.
- Fixed stale `cloudflare_client.py` line anchors in the scope table (245/165/143 -> 364/236/214)
  and one mangled path, `.\scriptsootstrap-worktree.ps1` -> `.\scripts\bootstrap-worktree.ps1`.

## What was NOT done

- No live Cloudflare API call was made, per the task constraints. The fallback is verified only
  against mocked HTTP. The spec's live evidence (401/1000 on the account endpoint, 200 on the user
  endpoint) was taken as given and not re-confirmed.
- Terraform checks were not run; no Terraform source was touched.
- Nothing pushed or merged. The orchestrator merges.

## Verification

`.venv\Scripts\python scripts/run_all_checks.py` — all five gates pass (Ruff lint, Ruff format,
mypy, Bandit, pytest). Coverage **92.71%**, threshold 75.

```
Running pytest coverage...
collected 71 items
scripts\tests\test_cloudflare_token_verification.py ..................   [ 85%]
scripts\cloudflare_client.py                            261     25    90%
TOTAL                                                  1125     82    93%
Required test coverage of 75% reached. Total coverage: 92.71%
============================= 71 passed in 3.33s ==============================
All quality checks passed.
```

Revert check — done for real, not assumed. Reverting the whole client file made the new module
fail to import, which is a weak signal, so the revert was redone as a **behavioural-only** revert:
`verify_connection()` restored to the account-only version and `_request()` restored to the
chained, unredacted errors, while keeping the new module names importable. Result:

```
13 failed, 28 passed in 0.54s
FAILED ...::test_user_token_falls_back_to_the_user_verify_endpoint
FAILED ...::test_user_token_falls_back_when_the_account_endpoint_returns_success_false
FAILED ...::test_both_endpoints_failing_raises_naming_both_attempts
FAILED ...::test_expired_status_is_passed_through_from_the_user_endpoint
FAILED ...::test_non_auth_failure_is_not_retried_and_is_not_swallowed
FAILED ...::test_code_1000_hint_does_not_blame_the_account_id
FAILED ...::test_code_9109_hint_reports_expiry_or_revocation
FAILED ...::test_unclassified_failure_still_gets_a_generic_hint
FAILED ...::test_account_id_never_appears_in_verification_failure_text
FAILED ...::test_account_id_never_appears_in_zone_request_failure_text
FAILED ...::test_request_error_codes_are_captured_from_the_response_body
FAILED ...::test_verify_connection_reaches_the_user_endpoint_over_http
FAILED scripts/tests/test_auditor.py::test_verify_connection_reports_invalid_token_helpfully
```

Restored, re-ran: `71 passed`, coverage 92.71%.

The gitleaks pre-commit hook ran (`core.hooksPath=.githooks`) and passed with no findings.
`--no-verify` was not used.

## Files changed

- `scripts/cloudflare_client.py`
- `scripts/tests/test_cloudflare_token_verification.py` (new)
- `scripts/tests/test_auditor.py`
- `docs/cloudflare-api-token-runbook.md`

## Decisions and assumptions

- **Fallback trigger.** The spec says fall back "on an auth failure that indicates a token-type
  mismatch". Code 1000 is the mismatch signal, but Cloudflare returns it identically for a bad
  secret, so 1000 alone cannot be a precise discriminator. I widened the trigger to 1000, 9109, or
  HTTP 400/401/403. Consequence: an expired token (9109) costs one extra HTTP call before failing.
  I judged that acceptable because the resulting combined error is strictly more informative, and
  because the spec's harder requirement is that genuine failures are not swallowed.
- **Breaking the httpx exception chain.** `raise ... from None` on `HTTPStatusError` is the only
  way to keep the URL out of a rendered traceback while still surfacing status and body. The
  status code and the (redacted) response body are preserved in our own message, so no diagnostic
  information is lost — only the httpx frame's repr. `RequestError` is likewise unchained;
  `ValueError` (bad JSON) still chains, as it carries no URL.
- **`_redact` redacts both the raw and the URL-quoted account ID**, since `_zones_path()` and
  `_account_path` percent-encode it.
- **Inverting the existing test** rather than deleting it. It documented the old misleading message;
  it now documents that the message must not return.
- Test fixtures use `placeholder-account-id` / `placeholder-token-secret` and `2099-01-01` expiry
  dates. No real account ID, zone ID, domain, or token appears anywhere in the diff.

## Risks / follow-ups

- `CloudflareAPIError.__init__` now takes keyword-only `status_code` / `error_codes`. Positional
  single-argument construction still works, so existing call sites are unaffected, but any future
  subclass should keep the signature.
- Redaction is a substring replace on `self.account_id`. A pathologically short account ID would
  over-redact unrelated text. Real Cloudflare account IDs are 32 hex chars, so this is theoretical.
- `_is_auth_failure()` treats HTTP 400 as auth-shaped. That is deliberately generous; if a future
  endpoint returns 400 for a malformed request, verification will make one wasted retry.
- Not covered by tests: `_get_bot_fight_mode` and `_zones_from_payload` still raise
  `CloudflareAPIError` directly rather than through `self._error`. Their messages embed only
  Cloudflare's `errors` array, which should not contain the account ID — but if a future Cloudflare
  response echoes it, that path is unredacted. Converting those static methods to instance methods
  would close the gap and is a reasonable follow-up.

## For the next worker

Start at `verify_connection()` and `_error()` in `scripts/cloudflare_client.py` — every raise in
the class should go through `_error()`, and the two static methods noted above are the remaining
exceptions to that rule.

If you need to re-run the revert check, do the behavioural revert rather than
`git checkout -- scripts/cloudflare_client.py`; a whole-file revert only produces an ImportError,
which proves nothing about behaviour.

The fallback has never been exercised against the live API. The first real `python run_tools.py
--verify` with the operator's User API Token is the actual confirmation, and is a safe read-only
call.
