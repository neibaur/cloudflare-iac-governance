# Zone Security Standard

`zone-security-standard.json` is the single definition of the security posture every Cloudflare
zone must meet. Terraform enforces it and the Python audit checks it; neither keeps its own copy of
the expected values. See [ADR 0001](../docs/adr/0001-terraform-state-and-drift-remediation.md).

The file contains no credentials, zone identifiers, or domain names.

## Format

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer format version. Currently `1`. |
| `controls` | List of controls. Each `key` appears once. |
| `controls[].key` | Stable control name, used as the audit column and policy identifier. |
| `controls[].resource` | Terraform resource type that enforces the control: `cloudflare_zone_setting` or `cloudflare_bot_management`. |
| `controls[].setting_id` | Cloudflare zone setting ID for `cloudflare_zone_setting` controls; `null` for `cloudflare_bot_management`. |
| `controls[].expected` | Required value, as a string. |
| `controls[].auto_correct` | Whether guarded automatic correction may change this control. Every control is `false` until ADR 0001's canary phase. |

## Changing the standard

Change a value only in this file, through a reviewed pull request. The Terraform tests and the
Python tests both read this file, so a change is enforced and audited identically.
