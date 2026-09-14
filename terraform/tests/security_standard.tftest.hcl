mock_provider "cloudflare" {}

variables {
  domains = {
    "standard.example" = {
      zone_id = "023e105f4ecef8ad9ca31a8372d0c353"
    }
    "override.example" = {
      zone_id = "023e105f4ecef8ad9ca31a8372d0c354"
    }
  }

  security_overrides = {
    "override.example" = {
      ssl = "strict"
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
}

run "catalog_manages_exactly_the_policy_controls" {
  command = plan

  # The zone module uses this catalog for its zone-setting resources, so a control, resource, or
  # setting ID added to the policy fails until Terraform actually manages it.
  assert {
    condition = jsonencode(module.security_control_catalog.managed_controls) == jsonencode({
      for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls :
      control.key => {
        resource   = control.resource
        setting_id = control.setting_id == null ? "" : control.setting_id
      }
    })
    error_message = "The control catalog must list exactly the controls, resources, and setting IDs in the policy file."
  }

  # The catalog is only a source of truth if the zone module's resources actually follow it.
  assert {
    condition     = jsonencode(module.cloudflare_zone_config["standard.example"].managed_controls) == jsonencode(module.security_control_catalog.managed_controls)
    error_message = "The zone module's resources must manage exactly the controls in the security control catalog."
  }
}

run "empty_domain_map_rejects_policy_catalog_mismatch" {
  command = plan

  variables {
    domains            = {}
    security_overrides = {}
  }

  override_module {
    target = module.security_control_catalog
    outputs = {
      managed_controls = {}
    }
  }

  expect_failures = [
    output.security_standard,
  ]
}

run "defaults_come_from_policy" {
  command = plan

  assert {
    condition = alltrue([
      for key, value in module.cloudflare_zone_config["standard.example"].controls :
      value == output.security_standard[key]
    ])
    error_message = "Every control without an override must equal the security standard."
  }
}

run "override_wins" {
  command = plan

  assert {
    condition     = module.cloudflare_zone_config["override.example"].controls["ssl"] == "strict"
    error_message = "A per-domain SSL override must take precedence over the security standard."
  }

  assert {
    condition = alltrue([
      for key, value in module.cloudflare_zone_config["override.example"].controls :
      value == output.security_standard[key] if key != "ssl"
    ])
    error_message = "Controls without an override must still equal the security standard."
  }
}

run "empty_override_is_rejected" {
  command = plan

  variables {
    domains = {
      "empty.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c355"
      }
    }

    security_overrides = {
      "empty.example" = {
        ssl = ""
      }
    }
  }

  expect_failures = [
    var.security_overrides,
  ]
}

run "every_override_field_wins_for_its_domain_only" {
  command = plan

  variables {
    domains = {
      "values.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c360"
      }
      "https.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c365"
      }
      "browser.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c366"
      }
      "bot.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c367"
      }
      "plain.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c361"
      }
    }

    # The on/off controls share their only non-policy value, so each gets its own domain; a wrong or
    # swapped mapping in terraform/main.tf then changes a domain that didn't override that control.
    security_overrides = {
      "values.example" = {
        ssl             = "strict"
        security_level  = "high"
        min_tls_version = "1.3"
      }
      "https.example" = {
        always_use_https = "off"
      }
      "browser.example" = {
        browser_integrity_check = "off"
      }
      "bot.example" = {
        bot_fight_mode = "off"
      }
    }
  }

  assert {
    condition = alltrue([
      for domain, changed in {
        "values.example"  = { ssl = "strict", security_level = "high", min_tls_version = "1.3" }
        "https.example"   = { always_use_https = "off" }
        "browser.example" = { browser_check = "off" }
        "bot.example"     = { bot_fight_mode = "off" }
        "plain.example"   = {}
      } :
      jsonencode(module.cloudflare_zone_config[domain].controls) == jsonencode(merge(output.security_standard, changed))
    ])
    error_message = "Each security_overrides field must set only its own control, and only for its own domain."
  }
}

run "empty_inventory_zone_id_is_rejected" {
  command = plan

  variables {
    domains = {
      "empty.example" = {
        zone_id = ""
      }
    }
    security_overrides = {}
  }

  expect_failures = [
    var.domains,
  ]
}

run "padded_inventory_zone_id_is_rejected" {
  command = plan

  variables {
    domains = {
      "padded.example" = {
        zone_id = " 023e105f4ecef8ad9ca31a8372d0c362"
      }
    }
    security_overrides = {}
  }

  expect_failures = [
    var.domains,
  ]
}

run "duplicate_inventory_zone_id_is_rejected" {
  command = plan

  variables {
    domains = {
      "first.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c363"
      }
      "second.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c363"
      }
    }
    security_overrides = {}
  }

  expect_failures = [
    var.domains,
  ]
}

run "override_entry_without_overrides_is_rejected" {
  command = plan

  variables {
    domains = {
      "bare.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c364"
      }
    }
    security_overrides = {
      "bare.example" = {}
    }
  }

  expect_failures = [
    var.security_overrides,
  ]
}

run "misspelled_override_field_is_rejected" {
  command = plan

  variables {
    domains = {
      "typo.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c368"
      }
    }

    # A valid field next to the misspelled one, so the entry isn't rejected for being empty.
    security_overrides = {
      "typo.example" = {
        ssl           = "strict"
        securty_level = "high"
      }
    }
  }

  expect_failures = [
    output.security_standard,
  ]
}

run "override_inside_inventory_is_rejected" {
  command = plan

  variables {
    domains = {
      "legacy.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c357"
        ssl     = "strict"
      }
    }

    # Clear the file-level overrides, so only the inventory-shape validation can fail this run.
    security_overrides = {}
  }

  expect_failures = [
    var.domains,
  ]
}

run "override_for_unknown_domain_is_rejected" {
  command = plan

  variables {
    domains = {
      "known.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c356"
      }
    }

    security_overrides = {
      "unknown.example" = {
        ssl = "strict"
      }
    }
  }

  expect_failures = [
    var.domains,
  ]
}

run "empty_domain_map_plans" {
  command = plan

  variables {
    domains            = {}
    security_overrides = {}
  }

  assert {
    condition     = length(output.security_standard) > 0
    error_message = "A plan with no domains must still succeed and expose the security standard."
  }
}
