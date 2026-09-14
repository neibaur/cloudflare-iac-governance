variable "cloudflare_account_id" {
  description = "Optional Cloudflare account ID, supplied through TF_VAR_cloudflare_account_id when needed."
  type        = string
  sensitive   = true
  default     = ""
}

variable "domains" {
  description = "Inventory of domain names and their Cloudflare zone IDs."
  type = map(object({
    zone_id = string
  }))

  validation {
    condition     = alltrue([for domain in values(var.domains) : trimspace(domain.zone_id) != ""])
    error_message = "Every inventory zone_id must be non-empty."
  }

  validation {
    condition     = alltrue([for domain_name in keys(var.security_overrides) : contains(keys(var.domains), domain_name)])
    error_message = "Every security_overrides key must identify a domain in var.domains."
  }
}

variable "security_overrides" {
  description = "Optional per-domain security posture overrides, keyed by a domain in var.domains."
  type = map(object({
    ssl                     = optional(string)
    security_level          = optional(string)
    always_use_https        = optional(string)
    min_tls_version         = optional(string)
    browser_integrity_check = optional(string)
    bot_fight_mode          = optional(string)
  }))
  default = {}

  validation {
    condition = alltrue([
      for override_set in values(var.security_overrides) : alltrue([
        for override in [
          override_set.ssl,
          override_set.security_level,
          override_set.always_use_https,
          override_set.min_tls_version,
          override_set.browser_integrity_check,
          override_set.bot_fight_mode,
        ] : override == null ? true : trimspace(override) != ""
      ])
    ])
    error_message = "A per-domain security override must be omitted or set to a non-empty value."
  }
}

variable "import_existing_zones" {
  description = "Whether root-module import blocks adopt existing zone resources. Operators enable this only for the acceptance plan."
  type        = bool
  default     = false
}
