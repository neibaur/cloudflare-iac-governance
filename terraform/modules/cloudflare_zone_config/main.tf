terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.22"
    }
  }
}

module "security_control_catalog" {
  source = "../security_control_catalog"
}

locals {
  # Configured value for each policy control key.
  control_values = {
    always_use_https = var.always_use_https
    bot_fight_mode   = var.bot_fight_mode
    browser_check    = var.browser_integrity_check
    min_tls_version  = var.min_tls_version
    security_level   = var.security_level
    ssl              = var.ssl
  }

  zone_setting_controls = {
    for key, control in module.security_control_catalog.managed_controls : key => control
    if control.resource == "cloudflare_zone_setting"
  }
  bot_management_controls = {
    for key, control in module.security_control_catalog.managed_controls : key => control
    if control.resource == "cloudflare_bot_management"
  }

  # Controls the filters above would silently skip: an unsupported resource type, a zone setting
  # without a setting ID, or bot management with one. Mirrors validate_controls in
  # scripts/security_standard.py.
  unsupported_controls = [
    for key, control in module.security_control_catalog.managed_controls : key
    if !(
      (control.resource == "cloudflare_zone_setting" && control.setting_id != "") ||
      (control.resource == "cloudflare_bot_management" && control.setting_id == "")
    )
  ]
  zone_setting_ids = [for control in values(local.zone_setting_controls) : control.setting_id]
}

# Resource addresses are keyed by setting ID; outputs are keyed by policy control key.
resource "cloudflare_zone_setting" "this" {
  for_each = {
    for key, control in local.zone_setting_controls : control.setting_id => local.control_values[key]
  }

  zone_id    = var.zone_id
  setting_id = each.key
  value      = each.value
}

resource "cloudflare_bot_management" "this" {
  zone_id    = var.zone_id
  enable_js  = true
  fight_mode = local.control_values["bot_fight_mode"] == "on"

  lifecycle {
    create_before_destroy = true

    # A zone has one bot management object, so this resource is not iterated from the catalog.
    # Fail the plan instead if the catalog stops listing it as exactly the bot_fight_mode control.
    precondition {
      condition     = jsonencode(keys(local.bot_management_controls)) == jsonencode(["bot_fight_mode"])
      error_message = "The security control catalog must list bot_fight_mode as its only cloudflare_bot_management control, because the zone module always manages Bot Fight Mode."
    }
  }
}
