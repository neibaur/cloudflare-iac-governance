variable "cloudflare_api_token" {
  description = "Cloudflare API token used by the Terraform provider."
  type        = string
  sensitive   = true

  validation {
    condition     = var.cloudflare_api_token != ""
    error_message = "cloudflare_api_token must not be empty."
  }
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID used for account-scoped API operations."
  type        = string
  sensitive   = true

  validation {
    condition     = var.cloudflare_account_id != ""
    error_message = "cloudflare_account_id must not be empty."
  }
}

variable "domains" {
  description = "Map of domain names to Cloudflare zone IDs and optional security posture overrides."
  type = map(object({
    zone_id                 = string
    ssl                     = optional(string, "full")
    always_use_https        = optional(string, "on")
    min_tls_version         = optional(string, "1.2")
    browser_integrity_check = optional(string, "on")
  }))
}
