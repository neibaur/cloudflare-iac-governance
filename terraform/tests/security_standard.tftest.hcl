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

run "standard_is_read_from_policy_file" {
  command = plan

  assert {
    condition = output.security_standard == {
      for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls :
      control.key => control.expected
    }
    error_message = "Terraform must read the security standard from policy/zone-security-standard.json."
  }

  # Tripwire: a control added to the policy must also be wired into terraform/main.tf.
  assert {
    condition = toset(keys(output.security_standard)) == toset([
      "always_use_https",
      "bot_fight_mode",
      "browser_check",
      "min_tls_version",
      "security_level",
      "ssl",
    ])
    error_message = "The policy controls changed. Wire every control into terraform/main.tf, then update this list."
  }
}

run "defaults_come_from_policy" {
  command = plan

  assert {
    condition = alltrue([
      for key, value in module.cloudflare_zone_config["standard.example"].settings :
      value == output.security_standard[key]
    ])
    error_message = "Every zone setting without an override must equal the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["standard.example"].bot_fight_mode == output.security_standard["bot_fight_mode"]
    error_message = "Bot Fight Mode without an override must equal the security standard."
  }
}

run "override_wins" {
  command = plan

  assert {
    condition     = module.cloudflare_zone_config["override.example"].settings.ssl == "strict"
    error_message = "A per-domain SSL override must take precedence over the security standard."
  }

  assert {
    condition = alltrue([
      for key, value in module.cloudflare_zone_config["override.example"].settings :
      value == output.security_standard[key] if key != "ssl"
    ])
    error_message = "Settings without an override must still equal the security standard."
  }

  assert {
    condition     = module.cloudflare_zone_config["override.example"].bot_fight_mode == output.security_standard["bot_fight_mode"]
    error_message = "Bot Fight Mode without an override must still equal the security standard."
  }
}
