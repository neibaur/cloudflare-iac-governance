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
}

run "module_manages_exactly_the_policy_controls" {
  command = plan

  # Compares the policy with what the module derives from its own resources, so a control, resource,
  # or setting ID added to the policy fails here until Terraform actually manages it.
  assert {
    condition = jsonencode(module.cloudflare_zone_config["standard.example"].managed_controls) == jsonencode({
      for control in jsondecode(file("${path.module}/../policy/zone-security-standard.json")).controls :
      control.key => {
        resource   = control.resource
        setting_id = control.setting_id == null ? "" : control.setting_id
      }
    })
    error_message = "The zone module must manage exactly the controls, resources, and setting IDs in the policy file."
  }
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
        ssl     = ""
      }
    }
  }

  expect_failures = [
    var.domains,
  ]
}
