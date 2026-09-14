locals {
  security_standard = {
    for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected
  }
}

module "cloudflare_zone_config" {
  source = "./modules/cloudflare_zone_config"

  for_each = var.domains

  zone_id                 = each.value.zone_id
  zone_name               = each.key
  ssl                     = coalesce(each.value.ssl, local.security_standard["ssl"])
  security_level          = coalesce(each.value.security_level, local.security_standard["security_level"])
  always_use_https        = coalesce(each.value.always_use_https, local.security_standard["always_use_https"])
  min_tls_version         = coalesce(each.value.min_tls_version, local.security_standard["min_tls_version"])
  browser_integrity_check = coalesce(each.value.browser_integrity_check, local.security_standard["browser_check"])
  bot_fight_mode          = coalesce(each.value.bot_fight_mode, local.security_standard["bot_fight_mode"])
}
