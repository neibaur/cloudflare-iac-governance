mock_provider "cloudflare" {}

run "zone_config_accepts_explicit_settings" {
  command = plan

  module {
    source = "./modules/cloudflare_zone_config"
  }

  variables {
    zone_id                 = "023e105f4ecef8ad9ca31a8372d0c353"
    zone_name               = "example.com"
    ssl                     = "full"
    security_level          = "medium"
    always_use_https        = "on"
    min_tls_version         = "1.2"
    browser_integrity_check = "on"
    bot_fight_mode          = "on"
  }

  assert {
    condition     = var.zone_id != "" && var.zone_name != ""
    error_message = "The cloudflare_zone_config module requires a zone ID and zone name."
  }

  assert {
    condition     = output.zone_id == var.zone_id
    error_message = "The module should expose the configured zone ID as output.zone_id."
  }
}

run "zone_config_rejects_empty_zone_id" {
  command = plan

  module {
    source = "./modules/cloudflare_zone_config"
  }

  variables {
    zone_id                 = ""
    zone_name               = "example.com"
    ssl                     = "full"
    security_level          = "medium"
    always_use_https        = "on"
    min_tls_version         = "1.2"
    browser_integrity_check = "on"
    bot_fight_mode          = "on"
  }

  expect_failures = [
    var.zone_id,
  ]
}

run "zone_config_rejects_catalog_without_bot_fight_mode" {
  command = plan

  module {
    source = "./modules/cloudflare_zone_config"
  }

  variables {
    zone_id                 = "023e105f4ecef8ad9ca31a8372d0c353"
    zone_name               = "example.com"
    ssl                     = "full"
    security_level          = "medium"
    always_use_https        = "on"
    min_tls_version         = "1.2"
    browser_integrity_check = "on"
    bot_fight_mode          = "on"
  }

  override_module {
    target = module.security_control_catalog
    outputs = {
      managed_controls = {
        ssl = {
          resource   = "cloudflare_zone_setting"
          setting_id = "ssl"
        }
      }
    }
  }

  expect_failures = [
    cloudflare_bot_management.this,
  ]
}

run "zone_config_outputs_are_keyed_by_control_key" {
  command = plan

  module {
    source = "./modules/cloudflare_zone_config"
  }

  variables {
    zone_id                 = "023e105f4ecef8ad9ca31a8372d0c353"
    zone_name               = "example.com"
    ssl                     = "full"
    security_level          = "medium"
    always_use_https        = "on"
    min_tls_version         = "1.2"
    browser_integrity_check = "on"
    bot_fight_mode          = "on"
  }

  # A control key that differs from its Cloudflare setting ID.
  override_module {
    target = module.security_control_catalog
    outputs = {
      managed_controls = {
        ssl = {
          resource   = "cloudflare_zone_setting"
          setting_id = "ssl_setting"
        }
        bot_fight_mode = {
          resource   = "cloudflare_bot_management"
          setting_id = ""
        }
      }
    }
  }

  assert {
    condition     = keys(cloudflare_zone_setting.this) == ["ssl_setting"]
    error_message = "Zone setting resources must be keyed by Cloudflare setting ID."
  }

  assert {
    condition     = output.controls == { bot_fight_mode = "on", ssl = "full" }
    error_message = "The controls output must be keyed by policy control key."
  }

  assert {
    condition     = output.managed_controls["ssl"].setting_id == "ssl_setting"
    error_message = "The managed_controls output must be keyed by policy control key and read the setting ID from the resource."
  }
}
