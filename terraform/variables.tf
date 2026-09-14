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

  validation {
    condition = alltrue([
      for domain in values(var.domains) : alltrue([
        for override in [
          domain.ssl,
          domain.security_level,
          domain.always_use_https,
          domain.min_tls_version,
          domain.browser_integrity_check,
          domain.bot_fight_mode,
        ] : override == null ? true : trimspace(override) != ""
      ])
    ])
    error_message = "A per-domain security override must be omitted or set to a non-empty value."
  }
}
