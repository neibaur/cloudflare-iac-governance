mock_provider "cloudflare" {}

run "zone_config_defaults_are_applied" {
  command = plan

  module {
    source = "../modules/cloudflare_zone_config"
  }

  variables {
    zone_id   = "023e105f4ecef8ad9ca31a8372d0c353"
    zone_name = "example.com"
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
    source = "../modules/cloudflare_zone_config"
  }

  variables {
    zone_id   = ""
    zone_name = "example.com"
  }

  expect_failures = [
    var.zone_id,
  ]
}
