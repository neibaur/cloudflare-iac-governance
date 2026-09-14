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

module "security_control_catalog" {
  source = "./modules/security_control_catalog"
}

output "security_standard" {
  description = "Expected value for each control in policy/zone-security-standard.json. Contains no zone identities."
  value       = local.security_standard

  precondition {
    condition     = local.policy.schema_version == 1
    error_message = "policy/zone-security-standard.json has an unsupported schema_version."
  }

  precondition {
    condition     = jsonencode(module.security_control_catalog.managed_controls) == jsonencode(local.policy_controls)
    error_message = "The policy's controls, resources, or setting IDs do not match terraform/modules/security_control_catalog. Wire the policy change into the catalog, terraform/main.tf, and the zone module."
  }
}

module "cloudflare_zone_config" {
  source = "./modules/cloudflare_zone_config"

  for_each = var.domains

  zone_id   = each.value.zone_id
  zone_name = each.key

  # A per-domain override wins only when it is set (non-null); otherwise the policy value applies.
  ssl                     = try(var.security_overrides[each.key].ssl, null) != null ? var.security_overrides[each.key].ssl : local.security_standard["ssl"]
  security_level          = try(var.security_overrides[each.key].security_level, null) != null ? var.security_overrides[each.key].security_level : local.security_standard["security_level"]
  always_use_https        = try(var.security_overrides[each.key].always_use_https, null) != null ? var.security_overrides[each.key].always_use_https : local.security_standard["always_use_https"]
  min_tls_version         = try(var.security_overrides[each.key].min_tls_version, null) != null ? var.security_overrides[each.key].min_tls_version : local.security_standard["min_tls_version"]
  browser_integrity_check = try(var.security_overrides[each.key].browser_integrity_check, null) != null ? var.security_overrides[each.key].browser_integrity_check : local.security_standard["browser_check"]
  bot_fight_mode          = try(var.security_overrides[each.key].bot_fight_mode, null) != null ? var.security_overrides[each.key].bot_fight_mode : local.security_standard["bot_fight_mode"]
}
