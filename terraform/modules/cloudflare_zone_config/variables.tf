variable "zone_id" {
  description = "Cloudflare zone identifier to configure."
  type        = string

  validation {
    condition     = var.zone_id != ""
    error_message = "zone_id must not be empty."
  }
}

variable "zone_name" {
  description = "Human-readable Cloudflare zone name."
  type        = string

  validation {
    condition     = var.zone_name != ""
    error_message = "zone_name must not be empty."
  }
}

variable "ssl" {
  description = "Cloudflare SSL mode for the zone."
  type        = string
  default     = "full"
}

variable "always_use_https" {
  description = "Whether Cloudflare should redirect HTTP requests to HTTPS."
  type        = string
  default     = "on"
}

variable "min_tls_version" {
  description = "Minimum TLS version accepted for the zone."
  type        = string
  default     = "1.2"
}

variable "browser_integrity_check" {
  description = "Browser Integrity Check status for the zone."
  type        = string
  default     = "on"
}
