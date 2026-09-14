locals {
  policy = jsondecode(file("${path.module}/../policy/zone-security-standard.json"))

  # Expected value for each control key.
  security_standard = {
    for control in local.policy.controls : control.key => control.expected
  }

  # Resource type and setting ID for each control key, normalized so a null setting_id compares as "".
  policy_controls = {
    for control in local.policy.controls : control.key => {
      resource   = control.resource
      setting_id = control.setting_id == null ? "" : control.setting_id
    }
  }
}

output "security_standard" {
  description = "Expected value for each control in policy/zone-security-standard.json. Contains no zone identities."
  value       = local.security_standard

  precondition {
    condition     = local.policy.schema_version == 1
    error_message = "policy/zone-security-standard.json has an unsupported schema_version."
  }

  precondition {
    # The conditional makes the empty-domain guard explicit: with no domains, no module instance is
    # indexed. The empty_domain_map_plans test covers this case.
    condition = (
      length(module.cloudflare_zone_config) == 0
      ? true
      : jsonencode(values(module.cloudflare_zone_config)[0].managed_controls) == jsonencode(local.policy_controls)
    )
    error_message = "The policy's controls, resources, or setting IDs do not match what terraform/main.tf and the zone module manage. Wire the policy change into Terraform."
  }
}

module "cloudflare_zone_config" {
  source = "./modules/cloudflare_zone_config"

  for_each = var.domains

  zone_id   = each.value.zone_id
  zone_name = each.key

  # A per-domain override wins only when it is set (non-null); otherwise the policy value applies.
  ssl                     = each.value.ssl != null ? each.value.ssl : local.security_standard["ssl"]
  security_level          = each.value.security_level != null ? each.value.security_level : local.security_standard["security_level"]
  always_use_https        = each.value.always_use_https != null ? each.value.always_use_https : local.security_standard["always_use_https"]
  min_tls_version         = each.value.min_tls_version != null ? each.value.min_tls_version : local.security_standard["min_tls_version"]
  browser_integrity_check = each.value.browser_integrity_check != null ? each.value.browser_integrity_check : local.security_standard["browser_check"]
  bot_fight_mode          = each.value.bot_fight_mode != null ? each.value.bot_fight_mode : local.security_standard["bot_fight_mode"]
}
