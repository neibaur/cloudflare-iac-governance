variable "cloudflare_account_id" {
  description = "Optional Cloudflare account ID, supplied through TF_VAR_cloudflare_account_id when needed."
  type        = string
  sensitive   = true
  default     = ""
}

variable "domains" {
  description = "Inventory of domain names and their Cloudflare zone IDs."
  # A map rather than an object type: Terraform silently discards undeclared object attributes, so an
  # inventory still carrying per-domain overrides would lose them without an error.
  type = map(map(string))

  validation {
    condition     = alltrue([for domain in values(var.domains) : jsonencode(keys(domain)) == jsonencode(["zone_id"])])
    error_message = "Each domains entry must contain only zone_id. Move per-domain security overrides to security_overrides."
  }

  validation {
    condition = alltrue([
      for domain in values(var.domains) :
      lookup(domain, "zone_id", "") != "" && trimspace(lookup(domain, "zone_id", "")) == lookup(domain, "zone_id", "")
    ])
    error_message = "Every inventory zone_id must be non-empty and have no surrounding whitespace, because it becomes part of each import ID."
  }

  # Two domains sharing a zone would import the same Cloudflare objects into two resource addresses.
  validation {
    condition     = length(distinct([for domain in values(var.domains) : lookup(domain, "zone_id", "")])) == length(var.domains)
    error_message = "Every inventory zone_id must be unique."
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

  validation {
    condition = alltrue([
      for override_set in values(var.security_overrides) :
      anytrue([for override in values(override_set) : override != null])
    ])
    error_message = "Each security_overrides entry must set at least one override. Remove entries with no overrides."
  }
}

variable "import_existing_zones" {
  description = "Whether root-module import blocks adopt existing zone resources. Operators enable this only for the acceptance plan."
  type        = bool
  default     = false
}
