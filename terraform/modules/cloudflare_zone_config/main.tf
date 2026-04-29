resource "cloudflare_zone_settings_override" "this" {
  zone_id = var.zone_id

  settings {
    ssl                     = var.ssl
    always_use_https        = var.always_use_https
    min_tls_version         = var.min_tls_version
    browser_integrity_check = var.browser_integrity_check
  }
}
