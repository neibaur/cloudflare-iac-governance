module "cloudflare_zone_config" {
  source = "./modules/cloudflare_zone_config"

  for_each = var.domains

  zone_id                 = each.value.zone_id
  zone_name               = each.key
  ssl                     = try(each.value.ssl, "full")
  always_use_https        = try(each.value.always_use_https, "on")
  min_tls_version         = try(each.value.min_tls_version, "1.2")
  browser_integrity_check = try(each.value.browser_integrity_check, "on")
}
