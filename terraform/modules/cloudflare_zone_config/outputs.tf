output "zone_id" {
  description = "Configured Cloudflare zone identifier."
  value       = var.zone_id
}

output "zone_name" {
  description = "Configured Cloudflare zone name."
  value       = var.zone_name
}

output "settings" {
  description = "Configured Cloudflare zone security settings."
  value       = local.zone_settings
}

output "bot_fight_mode" {
  description = "Configured Cloudflare Bot Fight Mode status."
  value       = var.bot_fight_mode
}
