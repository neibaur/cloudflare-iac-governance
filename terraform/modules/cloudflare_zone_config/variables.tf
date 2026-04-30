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

  validation {
    condition     = contains(["off", "flexible", "full", "strict"], var.ssl)
    error_message = "ssl must be one of: off, flexible, full, strict."
  }
}

variable "security_level" {
  description = "Cloudflare security level for the zone."
  type        = string
  default     = "medium"

  validation {
    condition = contains(
      ["essentially_off", "low", "medium", "high", "under_attack"],
      var.security_level,
    )
    error_message = "security_level must be one of: essentially_off, low, medium, high, under_attack."
  }
}

variable "always_use_https" {
  description = "Whether Cloudflare should redirect HTTP requests to HTTPS."
  type        = string
  default     = "on"

  validation {
    condition     = contains(["on", "off"], var.always_use_https)
    error_message = "always_use_https must be either on or off."
  }
}

variable "min_tls_version" {
  description = "Minimum TLS version accepted for the zone."
  type        = string
  default     = "1.2"

  validation {
    condition     = contains(["1.0", "1.1", "1.2", "1.3"], var.min_tls_version)
    error_message = "min_tls_version must be one of: 1.0, 1.1, 1.2, 1.3."
  }
}

variable "browser_integrity_check" {
  description = "Browser Integrity Check status for the zone."
  type        = string
  default     = "on"

  validation {
    condition     = contains(["on", "off"], var.browser_integrity_check)
    error_message = "browser_integrity_check must be either on or off."
  }
}

variable "bot_fight_mode" {
  description = "Whether Cloudflare Bot Fight Mode should be enabled."
  type        = string
  default     = "on"

  validation {
    condition     = contains(["on", "off"], var.bot_fight_mode)
    error_message = "bot_fight_mode must be either on or off."
  }
}
