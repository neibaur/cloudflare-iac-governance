locals {
  managed_controls = {
    always_use_https = {
      resource   = "cloudflare_zone_setting"
      setting_id = "always_use_https"
    }
    browser_check = {
      resource   = "cloudflare_zone_setting"
      setting_id = "browser_check"
    }
    min_tls_version = {
      resource   = "cloudflare_zone_setting"
      setting_id = "min_tls_version"
    }
    security_level = {
      resource   = "cloudflare_zone_setting"
      setting_id = "security_level"
    }
    ssl = {
      resource   = "cloudflare_zone_setting"
      setting_id = "ssl"
    }
    bot_fight_mode = {
      resource   = "cloudflare_bot_management"
      setting_id = ""
    }
  }
}

output "managed_controls" {
  description = "Resource type and setting ID for every security control managed by the zone configuration module."
  value       = local.managed_controls
}
