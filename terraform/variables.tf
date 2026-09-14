variable "cloudflare_account_id" {
  description = "Optional Cloudflare account ID, supplied through TF_VAR_cloudflare_account_id when needed."
  type        = string
  sensitive   = true
  default     = ""
}

variable "domains" {
  description = "Map of domain names to Cloudflare zone IDs and optional security posture overrides."
  type = map(object({
    zone_id                 = string
    ssl                     = optional(string)
    security_level          = optional(string)
    always_use_https        = optional(string)
    min_tls_version         = optional(string)
    browser_integrity_check = optional(string)
    bot_fight_mode          = optional(string)
  }))
}
