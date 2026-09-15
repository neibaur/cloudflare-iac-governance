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

  # security_overrides field for each policy control key. Each domain's override and its policy
  # fallback are looked up through this one table, so they can't refer to different controls.
  override_fields = {
    always_use_https = "always_use_https"
    bot_fight_mode   = "bot_fight_mode"
    browser_check    = "browser_integrity_check"
    min_tls_version  = "min_tls_version"
    security_level   = "security_level"
    ssl              = "ssl"
  }

  # Effective value for each control key per domain: a set (non-null) override wins; otherwise the
  # policy value applies. Validation rejects empty overrides, so coalesce never skips a set value.
  zone_controls = {
    for domain_name in keys(var.domains) : domain_name => {
      for key, field in local.override_fields :
      key => coalesce(try(var.security_overrides[domain_name][field], null), local.security_standard[key])
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

  # Checks that span variables live here rather than in variable validations, which only reference
  # their own variable: a cross-variable validation fails to evaluate when the other variable is
  # left at its default.
  precondition {
    condition     = alltrue([for domain_name in keys(var.security_overrides) : contains(keys(var.domains), domain_name)])
    error_message = "Every security_overrides key must identify a domain in var.domains."
  }

  precondition {
    condition = alltrue(flatten([
      for override_set in values(var.security_overrides) : [
        for field in keys(override_set) : contains(values(local.override_fields), field)
      ]
    ]))
    error_message = "Every security_overrides field must be one of: always_use_https, bot_fight_mode, browser_integrity_check, min_tls_version, security_level, ssl."
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

  ssl                     = local.zone_controls[each.key]["ssl"]
  security_level          = local.zone_controls[each.key]["security_level"]
  always_use_https        = local.zone_controls[each.key]["always_use_https"]
  min_tls_version         = local.zone_controls[each.key]["min_tls_version"]
  browser_integrity_check = local.zone_controls[each.key]["browser_check"]
  bot_fight_mode          = local.zone_controls[each.key]["bot_fight_mode"]
}
