mock_provider "cloudflare" {}

variables {
  domains = {
    "standard.example" = {
      zone_id = "023e105f4ecef8ad9ca31a8372d0c353"
    }
    "override.example" = {
      zone_id = "023e105f4ecef8ad9ca31a8372d0c354"
      ssl     = "strict"
    }
  }
}

run "defaults_come_from_policy" {
  command = plan

  assert {
    condition     = module.cloudflare_zone_config["standard.example"].settings.ssl == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["ssl"]
    error_message = "The SSL setting must come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["standard.example"].settings.security_level == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["security_level"]
    error_message = "The security level must come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["standard.example"].settings.always_use_https == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["always_use_https"]
    error_message = "The HTTPS redirect setting must come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["standard.example"].settings.min_tls_version == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["min_tls_version"]
    error_message = "The minimum TLS version must come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["standard.example"].settings.browser_check == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["browser_check"]
    error_message = "The browser integrity setting must come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["standard.example"].bot_fight_mode == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["bot_fight_mode"]
    error_message = "Bot Fight Mode must come from the security standard."
  }
}

run "override_wins" {
  command = plan

  assert {
    condition     = module.cloudflare_zone_config["override.example"].settings.ssl == "strict"
    error_message = "A per-domain SSL override must take precedence over the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["override.example"].settings.security_level == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["security_level"]
    error_message = "The security level must still come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["override.example"].settings.always_use_https == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["always_use_https"]
    error_message = "The HTTPS redirect setting must still come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["override.example"].settings.min_tls_version == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["min_tls_version"]
    error_message = "The minimum TLS version must still come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["override.example"].settings.browser_check == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["browser_check"]
    error_message = "The browser integrity setting must still come from the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["override.example"].bot_fight_mode == { for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls : control.key => control.expected }["bot_fight_mode"]
    error_message = "Bot Fight Mode must still come from the security standard."
  }
}
