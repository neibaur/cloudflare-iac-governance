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
    {
      for key, control in local.zone_setting_controls :
      key => cloudflare_zone_setting.this[control.setting_id].value
    },
    { for key in keys(local.bot_management_controls) : key => var.bot_fight_mode },
  )
}

output "managed_controls" {
  description = "Resource type and setting ID for every security control this module manages, keyed by policy control key and read from its resources."
  value = merge(
    {
      for key, control in local.zone_setting_controls : key => {
        resource   = "cloudflare_zone_setting"
        setting_id = cloudflare_zone_setting.this[control.setting_id].setting_id
      }
    },
    {
      for key in keys(local.bot_management_controls) : key => {
        resource   = "cloudflare_bot_management"
        setting_id = ""
      }
    },
  )
}
