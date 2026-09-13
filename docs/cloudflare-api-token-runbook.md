# Cloudflare API Token Runbook

Maintenance guide for the `CLOUDFLARE_API_TOKEN` credential used by the
compliance audit and the guarded Terraform remediation path.

## Why this document exists

Cloudflare API tokens can carry an expiry date. When the token expires, the
scheduled `Terraform CI` run fails every week with a misleading message, and
nothing in the workflow log names expiry as the cause. This runbook records the
exact scopes the token needs and how to rebuild it from scratch.

## Recognizing an expired token

The `Run compliance audit` step fails with:

```
httpx.HTTPStatusError: Client error '403 Forbidden' for url
  'https://api.cloudflare.com/client/v4/zones?account.id=***&page=1&per_page=50'
CloudflareAPIError: Cloudflare API returned HTTP 403:
  {"success":false,"errors":[{"code":9109,"message":"Invalid access token"}], ...}
CloudflareAPIError: Unable to list zones. Confirm the token includes Zone:Read permissions.
```

The final line is misleading. Cloudflare error **9109 / "Invalid access token"**
is returned for an expired, revoked, or deleted token — not for a scope gap.
Confirm which it is with the verification command below before rebuilding
anything.

Corroborating signal: the failure begins on a scheduled run with no
corresponding code change, and every earlier run on the same commit was green.

## Verifying the current token

Run from the repository root with the local `.env` populated:

```powershell
python run_tools.py --verify
```

This prints the raw verification result, e.g.
`{'id': '...', 'status': 'expired', 'expires_on': '2026-07-29T23:59:59Z'}`.
Read the `status` field — the command exits 0 even for an expired token.

The equivalent direct call. Note it returns **HTTP 200 with `success: true`**
even when the token is expired, so the status code alone proves nothing:

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/tokens/verify" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"
```

```json
{"result":{"status":"expired","expires_on":"2026-07-29T23:59:59Z"},"success":true}
```

`"status"` values: `active` (healthy), `expired` (past `expires_on`), `disabled`
(manually deactivated). A deleted token returns HTTP 403 / 9109 instead.

## Where the token lives in the dashboard

Cloudflare keeps **two separate token lists**, and a token in one is invisible
from the other:

| List | Path | Notes |
| --- | --- | --- |
| User API Tokens | dash.cloudflare.com → **My Profile** → API Tokens | Tied to your login; follows you across accounts |
| Account API Tokens | dash.cloudflare.com → select account → **Manage Account** → API Tokens | Tied to the account; survives membership changes |

Either type works for this project. If the token appears in neither list, it was
deleted and must be recreated — Cloudflare does not retain deleted tokens, and
their secrets are unrecoverable regardless.

Also confirm you are browsing the account whose ID is in `CLOUDFLARE_ACCOUNT_ID`.
With multiple Cloudflare accounts it is easy to search the wrong one; the account
ID appears in the dashboard URL.

## Required scopes

Derived from the API calls the code actually makes. Grant the read scopes
always; the edit scopes are only exercised when a run is dispatched with
`run_remediation = Y`.

| Permission | Level | Access | Needed by |
| --- | --- | --- | --- |
| Zone | Zone | Read | Listing zones — `GET /zones?account.id=` ([cloudflare_client.py:245](../scripts/cloudflare_client.py#L245)) |
| Zone Settings | Zone | Read | `ssl`, `security_level`, `always_use_https` — `GET /zones/{id}/settings/{id}` ([cloudflare_client.py:165](../scripts/cloudflare_client.py#L165)) |
| Bot Management | Zone | Read | `bot_fight_mode` — `GET /zones/{id}/bot_management` ([cloudflare_client.py:143](../scripts/cloudflare_client.py#L143)) |
| Zone Settings | Zone | Edit | Remediation only — `cloudflare_zone_setting` ([modules/cloudflare_zone_config/main.tf:20](../terraform/modules/cloudflare_zone_config/main.tf#L20)) |
| Bot Management | Zone | Edit | Remediation only — `cloudflare_bot_management` ([modules/cloudflare_zone_config/main.tf:28](../terraform/modules/cloudflare_zone_config/main.tf#L28)) |

Cloudflare's Edit access implies Read, so granting Edit on Zone Settings and Bot
Management covers both rows for that permission.

**Audit-only deployment:** grant just the three Read scopes. The workflow's
remediation gate defaults to `N`, so a read-only token runs the weekly audit
indefinitely and fails loudly if someone dispatches remediation — a reasonable
circuit breaker if you prefer applying changes by hand.

## Creating a replacement token

1. Open the appropriate token list (see table above) and choose **Create Token**
   → **Create Custom Token**.
2. **Name:** include the purpose and creation date, e.g.
   `cloudflare-iac-governance CI - 2026-09-08`. The name is the only breadcrumb
   linking the token back to this repository.
3. **Permissions:** add the rows from the scope table above.
4. **Zone Resources:** `Include` → `All zones from an account` → the account
   matching `CLOUDFLARE_ACCOUNT_ID`. Do **not** scope to specific zones — the
   audit is meant to discover zones, and a per-zone scope silently drops any
   domain added later.
5. **Client IP Address Filtering:** leave empty. GitHub-hosted runners have no
   stable egress IPs; an allowlist here causes intermittent 9109 failures that
   look exactly like expiry.
6. **TTL:** leave the expiry unset. If your policy requires an expiry, set a
   calendar reminder for two weeks before it — a failing weekly cron is easy to
   miss, as it was here for five consecutive runs.
7. Copy the token secret. **It is shown exactly once.**

## Installing the new token

```powershell
gh secret set CLOUDFLARE_API_TOKEN
```

Then update the local `.env` (`CLOUDFLARE_API_TOKEN=...`). `.env` is
gitignored — never commit the token, and let the Gitleaks workflow catch it if
you slip.

Verify before relying on the schedule:

```powershell
python run_tools.py --verify
python run_tools.py --audit
gh workflow run "Terraform CI"
```

Leave both `workflow_dispatch` inputs at `N` for the verification run so it
performs an audit without applying Terraform changes.

## Extending or rolling an existing token

Only possible while the token still appears in a dashboard list:

- **Extend an expiry** — open the token → **Edit** → change or clear the TTL →
  **Save**. The secret is unchanged, so no GitHub secret update is needed. This
  reactivates an already-expired token.
- **Roll the secret** — open the token → **Roll**. Scopes and expiry are
  preserved, but a new secret is issued, so the GitHub secret and local `.env`
  must both be updated. Use this after a suspected leak.

A deleted token cannot be recovered by either route; create a new one.

## The agent worktree token

A **second, separate token** for the AI agent worktrees at `../worktrees/wt-01` .. `wt-05`. This is
not the CI token and must never be the same credential.

### Why a separate token

Agent worktrees are worked by Codex, Claude, Gemini, and Copilot, sometimes by smaller models whose
rule-following cannot be relied on. Any agent that can *use* a credential can also read it, and a
credential an agent has read is already inside a context window sent to a model provider. No hook,
file permission, or instruction prevents that.

So the control is not access, it is blast radius. A read-only, IP-locked, short-lived token is
worth close to nothing if it leaks, and an agent holding one **cannot change infrastructure no
matter what it decides to do**. That is a guarantee enforced by Cloudflare rather than by prompt
compliance.

### Scopes

Grant the three Read scopes from the table above and nothing else:

| Permission | Level | Access |
| --- | --- | --- |
| Zone | Zone | Read |
| Zone Settings | Zone | Read |
| Bot Management | Zone | Read |

**Grant no Edit scope.** The audit path needs only these three, so a read-only token runs every
agent-side check indefinitely while making remediation structurally impossible.

### Settings that differ from the CI token

The CI guidance above is written for GitHub-hosted runners. Two items invert for a token that only
ever runs on your own machine:

| Setting | CI token | Agent token | Why it differs |
| --- | --- | --- | --- |
| **TTL** | Leave unset | **Set 30 days** | A weekly cron you forget about should not silently expire. An agent token should self-revoke; you are present when it is used, so a renewal prompt costs nothing. |
| **Client IP filtering** | Leave empty | **Set to your egress IP** | GitHub runners have no stable egress IP, which is why the CI token leaves this blank. Your workstation does have one, so a leaked agent token becomes unusable from anywhere else. Free here, impossible there. |

Find your current egress IP with `curl -s https://api.ipify.org`. If your ISP rotates it, the token
fails closed with a 9109 — see the expiry section above, and note that an IP mismatch presents
exactly like expiry. Re-check the IP before assuming the token died.

Name it distinctly, e.g. `cloudflare-iac-governance AGENT ro - 2026-09-12`, so it is obvious in the
dashboard which token is the restricted one.

### Installing it

Agent worktrees read `.env.agent` from the primary clone, never your real `.env`. Create it in the
repository root:

```
CLOUDFLARE_API_TOKEN=<the read-only agent token>
CLOUDFLARE_ACCOUNT_ID=<same account id>
```

Omit `GOOGLE_SHEET_ID` and `FIX_DETECTED_GAPS` — agents have no reason to reach the Sheets sync or
the remediation gate.

`.env.agent` is covered by the `.env.*` rule in `.gitignore`. Verify before relying on it:

```powershell
git check-ignore -v .env.agent
```

Then provision a worktree:

```powershell
cd ..\worktrees\wt-02
.\scriptsootstrap-worktree.ps1 -WithCloudflareToken
```

The bootstrap prefers `.env.agent` and warns loudly if it falls back to the unrestricted `.env`.
Treat that warning as a stop sign, not noise.

### Verifying and rotating

```powershell
python run_tools.py --verify
```

Read the `status` field, as above — the command exits 0 even for an expired token.

Rotate on the 30-day expiry, and immediately if a worktree behaves unexpectedly or a transcript may
have carried the value off-machine. Rolling the agent token requires updating only `.env.agent`;
CI and GitHub Secrets are untouched, which is the point of keeping the two separate.

### What this does not solve

- It does not stop an agent reading the token, or that value landing in a provider transcript.
  Assume both will happen and rely on the scoping.
- It does not protect `service_account.json`. That is an unscoped GCP private key with no
  equivalent read-only mode; keep it out of worktrees entirely and broker Sheets work instead.
- It does not protect `terraform.tfvars`, which carries real domains and zone IDs. That is
  configuration disclosure rather than credential compromise, but it still does not belong in a
  worktree unless a task genuinely needs it.

See `docs/agent-worktree-security.md` for the full layered model.

## Related

- [cloudflare-provider-v5-migration.md](cloudflare-provider-v5-migration.md)
- `.github/workflows/terraform-ci.yml` — the weekly scheduled audit
- `docs/agent-worktree-security.md` — agent worktree threat model and controls
