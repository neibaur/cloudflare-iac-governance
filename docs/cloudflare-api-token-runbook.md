# Cloudflare API Token Runbook

Maintenance guide for the three `CLOUDFLARE_API_TOKEN` credentials used by
GitHub Actions, a local operator, and agent worktrees. They are deliberately
different credentials: do not reuse one token in another role.

## Choose the token you are setting up

| Token | Stored in | Permissions | Expiry | Client IP filter |
| --- | --- | --- | --- | --- |
| **CI** | GitHub Secret `CLOUDFLARE_API_TOKEN` | Zone:Read, Zone Settings:Read, Bot Management:Read | None | None |
| **Local operator** | `.env` | Zone:Read, Zone Settings:Edit, Bot Management:Edit | Set one according to operator policy | Operator egress IP |
| **Agent worktrees** | `.env.agent` in the primary clone | Zone:Read, Zone Settings:Read, Bot Management:Read | Short, for example 30 days | Optional |

The CI and agent tokens can only audit. The local operator token can also make
attended changes. No workflow changes infrastructure, so CI never holds an edit
token; a separate, environment-gated apply token arrives with ADR 0001.
`Zone:Zone` is **Read on every token, never Edit**: this repository
only lists zones with `GET /zones?account.id=`
(`_zones_path` in [cloudflare_client.py](../scripts/cloudflare_client.py)). Zone:Edit
would permit zone deletion, a capability this repository never exercises.

Cloudflare Edit implies Read. Consequently, Zone Settings:Edit and Bot
Management:Edit cover both reading and changing settings for the local operator
token. Only Zone:Zone needs a separate Read grant. The underlying
read calls are
`GET /zones/{id}/settings/{id}` (`_get_zone_setting`) and
`GET /zones/{id}/bot_management` (`_get_bot_fight_mode`), both in
[cloudflare_client.py](../scripts/cloudflare_client.py); the
Terraform edit resources are `cloudflare_zone_setting` and `cloudflare_bot_management`
in [the zone config module](../terraform/modules/cloudflare_zone_config/main.tf).

For every token, set **Zone Resources** to `Include` ->
`All zones from an account` -> the account matching
`CLOUDFLARE_ACCOUNT_ID`. Never select individual zones. The audit discovers
zones, so a per-zone scope silently omits every domain added later.

## Dashboard token type: User or Account

Cloudflare maintains two separate lists. Either token type works with this
project:

| Type | Dashboard path | Lifecycle |
| --- | --- | --- |
| User API Token | **My Profile** -> **API Tokens** | Tied to the login and can span accounts |
| Account API Token | Select account -> **Manage Account** -> **API Tokens** | Tied to the account and survives membership changes |

Choose the list whose ownership model matches the role, then create a custom
token there. Account tokens are usually clearer for CI; a named operator may
prefer a User token. Both still must be scoped to the account in
`CLOUDFLARE_ACCOUNT_ID`.

The client supports both namespaces. `verify_connection()` first calls
`/accounts/{id}/tokens/verify`, then falls back to `/user/tokens/verify` after
an authentication-shaped failure
(`verify_connection` in [cloudflare_client.py](../scripts/cloudflare_client.py)). A valid User
token therefore returns HTTP 401 / code 1000 at the first endpoint before
succeeding at the second. Do not rebuild it merely because the wrong namespace
rejected it.

## Set up the CI token

Use this credential for scheduled and manually dispatched `Compliance Audit` runs.

1. In either dashboard token list, choose **Create Token** -> **Create Custom
   Token** and give it a CI-specific name.
2. Grant exactly Zone:Read, Zone Settings:Read, and Bot Management:Read. Do not
   grant any Edit permission: the `Compliance Audit` workflow only reads.
3. Include all zones from the account.
4. Leave the expiry unset. A weekly job can fail unnoticed; an expired CI token
   previously left five consecutive scheduled runs failing.
5. Leave Client IP Address Filtering empty. GitHub-hosted runners have no
   stable egress IP, so an allowlist creates intermittent 9109 failures that
   look exactly like expiry.
6. Copy the secret when Cloudflare shows it once, then install it without
   putting it on the command line:

   ```powershell
   gh secret set CLOUDFLARE_API_TOKEN
   ```

7. Verify by dispatching `Compliance Audit` with `sync_to_sheets` left at `N`.
   The run should pass **Run compliance audit**.

If this token expires, is revoked, is deleted, or is rejected, scheduled and
dispatched `Compliance Audit` fails at **Run compliance audit**. Local operator and
agent audits are unaffected because they use separate credentials.

When rolling the CI token, update the GitHub Secret
`CLOUDFLARE_API_TOKEN`; neither local file changes. When extending only its
expiry, the secret remains unchanged.

## Set up the local operator token

Use this credential for trusted, attended commands from the primary clone. It
is edit-capable because the operator performs attended changes that agents and
the read-only audit never make.

1. Create a custom User or Account API Token with a local-operator-specific
   name.
2. Grant exactly Zone:Read, Zone Settings:Edit, and Bot Management:Edit. Do not
   grant Zone:Edit.
3. Include all zones from the account.
4. Set an expiry required by your operator policy and schedule renewal before
   it. Unlike unattended CI, the operator is present when this credential is
   used and sees a failure immediately.
5. Restrict it to the operator workstation's egress IP. This is the
   edit-capable credential used from one stable-enough location, so the filter
   meaningfully reduces its blast radius.

On Windows, use one of these commands to find the current egress IP:

```powershell
curl.exe -s https://api.ipify.org
Invoke-RestMethod https://api.ipify.org
```

In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`; it does
not accept `-s` and prompts for `Uri`. Use `curl.exe`, including the `.exe`, or
`Invoke-RestMethod` as shown. If the ISP changes the address, Cloudflare fails
closed with code 9109. Check the egress IP before assuming the token expired.

### Allowlist both IPv4 and IPv6

A dual-stack machine has an address in both families, and which one a given
request uses depends on the destination and the route. The two sources disagree
by design:

| Source | Returns | Family |
| --- | --- | --- |
| `api.ipify.org` | `n.n.n.n` | IPv4 |
| Cloudflare's **Use my IP** button | hex groups separated by `:` | IPv6 |

Both addresses are genuinely yours. Cloudflare's dashboard saw the browser over
IPv6; ipify answered over IPv4.

**Add both.** Allowlisting only one family leaves the token working from the
browser and failing from the API client, or the reverse, and the rejection is
code 9109 — indistinguishable from expiry and from revocation. On a token that
also carries an expiry date, that is three separate causes behind one error.

For the IPv6 entry, allowlist the exact address your API client sends from. A
machine holds several IPv6 addresses at once, and only one of them is used as
the source of outbound connections. Check which one, and whether it is stable:

```powershell
$src = .venv\Scripts\python -c "import socket;s=socket.create_connection(('api.cloudflare.com',443));print(s.getsockname()[0]);s.close()"
Get-NetIPAddress | Where-Object IPAddress -eq $src | Select-Object IPAddress, SuffixOrigin
```

- **`SuffixOrigin` is `Link`** — a stable address. Allowlist it exactly as shown.
  It does not rotate on a timer.
- **`SuffixOrigin` is `Random`** — a temporary privacy address, which Windows
  replaces within about a week. A single-address allowlist will break when it
  does. Prefer IPv4-only filtering in that case, because Cloudflare's filter
  field rejected a `/64` range when this was tested.
- **The output is an IPv4 private address** such as `192.168.x.x` — the client is
  using IPv4 behind NAT. Use the public address from `api.ipify.org` instead.

Either address changes if the ISP reassigns your prefix, typically after a
router restart. The symptom is the same 9109.

Verify the allowlist accepts real traffic before relying on it:

```powershell
.venv\Scripts\python run_tools.py --verify
.venv\Scripts\python run_tools.py --audit
```

`--verify` alone is not sufficient. It confirms the token is active but exercises
only one endpoint; `--audit` proves the allowlist accepts the zone, settings, and
bot-management reads the workflow actually performs.

Install the values in the primary clone's gitignored `.env`:

```dotenv
CLOUDFLARE_API_TOKEN=<local-operator-token>
CLOUDFLARE_ACCOUNT_ID=<account-id>
```

Add `GOOGLE_SHEET_ID=<sheet-id>` only when the Sheets workflow needs it. It is
an identifier, not the service-account credential. Confirm the file is ignored
without reading it:

```powershell
git check-ignore -v .env
```

Verify from the repository root:

```powershell
python run_tools.py --verify
python run_tools.py --audit
```

If this token is rejected, those local `--verify` and `--audit` commands fail.
CI and agent worktrees are unaffected. Rolling it requires updating only
`.env`; extending its expiry does not change the stored secret.

## Set up the agent worktree token

Use a second, separate credential for AI agent worktrees. An agent that can use
a credential can also read it, so prompt instructions and file permissions are
not the security boundary. Cloudflare-enforced read-only scope ensures a
worktree cannot change infrastructure regardless of what an agent decides to
do.

1. Create a custom User or Account API Token with an unmistakable agent/read-
   only name.
2. Grant exactly Zone:Read, Zone Settings:Read, and Bot Management:Read. Grant
   no Edit permission, including Zone:Edit.
3. Include all zones from the account.
4. Set a short expiry, for example 30 days, so a forgotten exposed credential
   self-revokes. The operator is present when agents need it, so renewal is a
   small cost.
5. IP filtering is optional. Enable it when the worktrees consistently use a
   stable egress IP; leave it unset when addresses rotate or agents run from
   multiple trusted networks. Read-only scope is the primary control.

Install it in `.env.agent` at the **primary clone** repository root:

```dotenv
CLOUDFLARE_API_TOKEN=<read-only-agent-token>
CLOUDFLARE_ACCOUNT_ID=<account-id>
GOOGLE_SHEET_ID=<sheet-id>
```

`GOOGLE_SHEET_ID` only addresses the spreadsheet. The credential that opens it
is `service_account.json`, which must stay out of worktrees. `.env` is ignored
explicitly and `.env.agent` is covered by `.env.*`
(see the `.env.*` rule in [.gitignore](../.gitignore)). Confirm without reading the file:

```powershell
git check-ignore -v .env.agent
```

Provisioning is explicit and must be run from the selected worktree:

```powershell
.\scripts\bootstrap-worktree.ps1 -WithCloudflareToken
python run_tools.py --verify
python run_tools.py --audit
```

The bootstrap prefers `.env.agent` and warns if it would fall back to `.env`.
Treat that warning as a stop sign: an edit-capable local token must not silently
enter a worktree.

If this token expires or is rejected, worktree agents cannot verify or audit;
nothing else is affected. Rolling it requires updating only `.env.agent` in
the primary clone. CI's GitHub Secret and the operator's `.env` remain
unchanged. Extending its expiry does not change the secret.

This separation still matters if `.env` and `.env.agent` temporarily contain
tokens with similar access. It prevents an edit-capable operator token from
silently propagating when the credentials later diverge.

## Recognizing an expired token

The **Run compliance audit** step commonly fails with:

```text
httpx.HTTPStatusError: Client error '403 Forbidden' for url
  'https://api.cloudflare.com/client/v4/zones?account.id=***&page=1&per_page=50'
CloudflareAPIError: Cloudflare API returned HTTP 403:
  {"success":false,"errors":[{"code":9109,"message":"Invalid access token"}], ...}
CloudflareAPIError: Unable to list zones. Confirm the token includes Zone:Read permissions.
```

The final line is generic and can be misleading. A failure beginning on a
scheduled run with no corresponding code change, after earlier runs on the
same commit succeeded, is a strong expiry signal. It is not proof: revocation,
deletion, and an IP mismatch produce the same code.

| Code | Meaning | First checks |
| --- | --- | --- |
| **1000** | The installed value is wrong or truncated, or verification used the wrong User/Account namespace | Confirm the installed value and try the other verify endpoint. It says nothing about the account ID. |
| **9109** | Expired, revoked, deleted, **or blocked by the client IP allowlist** | Read verification status when available, check the dashboard, and compare current egress IP with the allowlist. |

The shorthand is: **1000 can be the wrong door; 9109 means the credential was
not accepted.** An IP mismatch and expiry are intentionally indistinguishable
at the API error-code level.

Use the failure location to identify which credential to inspect:

| Failure | Token to inspect | Other paths affected? |
| --- | --- | --- |
| `Compliance Audit` fails at **Run compliance audit** | CI GitHub Secret | No |
| Local `python run_tools.py --verify` or `--audit` fails | Local `.env` | No |
| A provisioned worktree cannot verify or audit | Primary clone `.env.agent` | No |

## Verifying the current token

From an environment where the intended local token has already been installed,
run:

```powershell
python run_tools.py --verify
```

Read the returned `status`, not merely the process exit code or HTTP status. A
verify endpoint can return HTTP 200 with `success: true` while reporting
`status: expired` or `status: disabled`; the command can exit 0 for that
response. `active` is healthy, `expired` is past `expires_on`, and `disabled`
means manually deactivated. A deleted token returns an authentication error.

There are two verify endpoints:

| Endpoint | Accepts |
| --- | --- |
| `GET /accounts/{account_id}/tokens/verify` | Account API Tokens |
| `GET /user/tokens/verify` | User API Tokens |

The client tries both in the order described under [Dashboard token type](#dashboard-token-type-user-or-account).
Its exception text redacts the account ID so it does not land in CI logs or
tracebacks. Do not use a direct API call from an agent worktree; the repository
command is the supported verification path.

For an operator diagnosing the installed local token, these are the equivalent
direct calls. Use the endpoint matching the token type, and do not mistake HTTP
200 alone for health:

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/tokens/verify" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"

curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN"
```

An expired token can still produce a successful envelope such as:

```json
{"result":{"status":"expired","expires_on":"<timestamp>"},"success":true}
```

## Where the token lives in the dashboard

Return to the same User or Account API Token list where the credential was
created. Tokens are invisible from the other list, so search both before
concluding one was deleted. Also confirm the selected dashboard account matches
`CLOUDFLARE_ACCOUNT_ID`; with multiple accounts it is easy to inspect the wrong
one.

If a token appears in neither list, it was deleted. Cloudflare does not retain
deleted tokens, and their secret values cannot be recovered. Create the
appropriate replacement using the role-specific section above.

## Extending or rolling an existing token

These actions are available only while the token remains in a dashboard list:

- **Extend an expiry:** open the token, choose **Edit**, change or clear its
  TTL, and save. The secret is unchanged, so no storage location needs an
  update. Preserve the role's intended expiry policy: no expiry for CI, an
  operator-policy expiry for `.env`, and a short expiry for `.env.agent`.
- **Roll the secret:** open the token and choose **Roll**. Scopes and expiry are
  preserved, but Cloudflare issues a new secret. Update only that role's
  location: GitHub Secret for CI, `.env` for local operator, or `.env.agent`
  for worktrees. Re-run the matching verification afterward.

Roll immediately after suspected exposure. A deleted token cannot be extended
or rolled; recreate it. Never copy one role's replacement into another role's
storage.

## Related

- [Agent worktree security](agent-worktree-security.md)
- [Compliance Audit workflow](../.github/workflows/compliance-audit.yml)
