mock_provider "cloudflare" {}

run "imports_disabled_are_empty" {
  command = plan

  variables {
    domains = {
      "first.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c353"
      }
    }
  }

  assert {
    condition     = length(local.import_zone_settings) == 0 && length(local.import_bot_management) == 0
    error_message = "Imports must be empty unless import_existing_zones is true."
  }
}

run "imports_cover_every_resource_for_two_domains" {
  command = plan

  # terraform test cannot import through a mock provider. Overriding every target makes the
  # generated addresses testable without making a provider API request.
  override_resource {
    target = module.cloudflare_zone_config["first.example"].cloudflare_zone_setting.this["always_use_https"]
  }
  override_resource {
    target = module.cloudflare_zone_config["first.example"].cloudflare_zone_setting.this["browser_check"]
  }
  override_resource {
    target = module.cloudflare_zone_config["first.example"].cloudflare_zone_setting.this["min_tls_version"]
  }
  override_resource {
    target = module.cloudflare_zone_config["first.example"].cloudflare_zone_setting.this["security_level"]
  }
  override_resource {
    target = module.cloudflare_zone_config["first.example"].cloudflare_zone_setting.this["ssl"]
  }
  override_resource {
    target = module.cloudflare_zone_config["first.example"].cloudflare_bot_management.this
  }
  override_resource {
    target = module.cloudflare_zone_config["second.example"].cloudflare_zone_setting.this["always_use_https"]
  }
  override_resource {
    target = module.cloudflare_zone_config["second.example"].cloudflare_zone_setting.this["browser_check"]
  }
  override_resource {
    target = module.cloudflare_zone_config["second.example"].cloudflare_zone_setting.this["min_tls_version"]
  }
  override_resource {
    target = module.cloudflare_zone_config["second.example"].cloudflare_zone_setting.this["security_level"]
  }
  override_resource {
    target = module.cloudflare_zone_config["second.example"].cloudflare_zone_setting.this["ssl"]
  }
  override_resource {
    target = module.cloudflare_zone_config["second.example"].cloudflare_bot_management.this
  }

  variables {
    import_existing_zones = true
    domains = {
      "first.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c353"
      }
      "second.example" = {
        zone_id = "023e105f4ecef8ad9ca31a8372d0c354"
      }
    }
  }

  assert {
    condition     = length(local.import_zone_settings) + length(local.import_bot_management) == 12
    error_message = "Two domains must target twelve imports: five settings and one bot-management resource each."
  }

  assert {
    condition = alltrue([
      for setting in values(local.import_zone_settings) :
      setting.zone_id != "" && setting.setting_id != "" &&
      contains([for control in values(module.security_control_catalog.managed_controls) : control.setting_id], setting.setting_id)
    ])
    error_message = "Every generated setting import must use its zone ID and a catalog setting ID."
  }

  assert {
    condition     = alltrue([for bot in values(local.import_bot_management) : bot.zone_id != ""])
    error_message = "Every generated bot-management import must use its zone ID."
  }
}

run "enabled_imports_allow_an_empty_inventory" {
  command = plan

  variables {
    domains               = {}
    import_existing_zones = true
  }

  assert {
    condition     = length(local.import_zone_settings) == 0 && length(local.import_bot_management) == 0
    error_message = "An empty inventory must not create import targets."
  }
}
