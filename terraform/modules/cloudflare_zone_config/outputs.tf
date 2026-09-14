output "zone_id" {
  description = "Configured Cloudflare zone identifier."
  value       = var.zone_id
}

output "zone_name" {
  description = "Configured Cloudflare zone name."
  value       = var.zone_name
}

output "controls" {
  description = "Configured value for every security control this module manages, keyed by policy control key."
  value = merge(
    { for setting_id, setting in cloudflare_zone_setting.this : setting_id => setting.value },
    { bot_fight_mode = var.bot_fight_mode },
  )
}

output "managed_controls" {
  description = "Resource type and setting ID for every security control this module manages, derived from its resources."
  value = merge(
    {
      for setting_id, setting in cloudflare_zone_setting.this : setting_id => {
        resource   = "cloudflare_zone_setting"
        setting_id = setting.setting_id
      }
    },
    {
      bot_fight_mode = {
        resource   = "cloudflare_bot_management"
        setting_id = ""
      }
    },
  )
}
