terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.52"
    }
  }
}

resource "cloudflare_zone_settings_override" "this" {
  zone_id = var.zone_id

  settings {
    ssl              = var.ssl
    security_level   = var.security_level
    always_use_https = var.always_use_https
    min_tls_version  = var.min_tls_version
    browser_check    = var.browser_integrity_check
  }
}

resource "cloudflare_bot_management" "this" {
  zone_id    = var.zone_id
  enable_js  = true
  fight_mode = var.bot_fight_mode == "on"

  lifecycle {
    create_before_destroy = true
  }
}
