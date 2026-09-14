terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.22"
    }
  }
}

locals {
  control_values = {
    always_use_https = var.always_use_https
    bot_fight_mode   = var.bot_fight_mode
    browser_check    = var.browser_integrity_check
    min_tls_version  = var.min_tls_version
    security_level   = var.security_level
    ssl              = var.ssl
  }
}

module "security_control_catalog" {
  source = "../security_control_catalog"
}

resource "cloudflare_zone_setting" "this" {
  for_each = {
    for control_key, control in module.security_control_catalog.managed_controls :
    control.setting_id => local.control_values[control_key]
    if control.resource == "cloudflare_zone_setting"
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
  }
}
