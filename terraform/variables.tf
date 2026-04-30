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
    ssl                     = optional(string, "full")
    always_use_https        = optional(string, "on")
    min_tls_version         = optional(string, "1.2")
    browser_integrity_check = optional(string, "on")
  }))
}
