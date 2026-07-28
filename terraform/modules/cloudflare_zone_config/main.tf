terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.22"
    }
  }
}

locals {
  zone_settings = {
    always_use_https = var.always_use_https
    browser_check    = var.browser_integrity_check
    min_tls_version  = var.min_tls_version
    security_level   = var.security_level
    ssl              = var.ssl
  }
}

resource "cloudflare_zone_setting" "this" {
  for_each = local.zone_settings

  zone_id    = var.zone_id
  setting_id = each.key
  value      = each.value
}

resource "cloudflare_bot_management" "this" {
  zone_id    = var.zone_id
  enable_js  = true
  fight_mode = var.bot_fight_mode == "on"

  lifecycle {
    create_before_destroy = true
  }
}
