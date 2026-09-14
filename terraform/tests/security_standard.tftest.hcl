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

run "override_inside_inventory_is_rejected" {
  command = plan

  variables {
    domains = {
      "legacy.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c357"
        ssl     = "strict"
      }
    }
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
