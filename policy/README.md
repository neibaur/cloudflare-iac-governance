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
| `controls[].key` | Stable policy and audit identifier for the control. The audit report uses it as the CSV column name, except where a compatibility mapping keeps a historical column name (`ssl` is written to `ssl_mode`). |
| `controls[].resource` | Terraform resource type that enforces the control: `cloudflare_zone_setting` or `cloudflare_bot_management`. |
| `controls[].setting_id` | Cloudflare zone setting ID for `cloudflare_zone_setting` controls, unique across controls; `null` for `cloudflare_bot_management`, of which there is at most one (Bot Fight Mode). |
| `controls[].expected` | Required value, as a string. |
| `controls[].auto_correct` | Whether guarded automatic correction may change this control. Every control is `false` until ADR 0001's canary phase. |

## Changing the standard

Change the standard only in this file, through a reviewed pull request.

- **Changing an `expected` value** needs no other edit. Terraform and the audit both read it, and
  their tests confirm it.
- **Adding, removing, or renaming a control, or changing its `resource` or `setting_id`,** also
  requires wiring the change into `terraform/main.tf` and the zone module. Until that is done, every
  Terraform plan fails its policy precondition and `terraform test` fails, so a policy change can't
  silently go unenforced. The audit follows the file automatically.

Per-domain overrides in Terraform inputs take precedence over the standard only when they are set.
An empty override is rejected.
