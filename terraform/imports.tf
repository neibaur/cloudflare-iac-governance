locals {
  import_zone_settings = var.import_existing_zones ? {
    for pair in setproduct(
      keys(var.domains),
      [for control in values(local.policy_controls) : control.setting_id if control.resource == "cloudflare_zone_setting"],
      ) : "${pair[0]}/${pair[1]}" => {
      domain_name = pair[0]
      zone_id     = var.domains[pair[0]].zone_id
      setting_id  = pair[1]
    }
  } : {}

  import_bot_management = var.import_existing_zones ? {
    for domain_name, domain in var.domains : domain_name => {
      zone_id = domain.zone_id
    }
  } : {}
}

import {
  for_each = local.import_zone_settings

  to = module.cloudflare_zone_config[each.value.domain_name].cloudflare_zone_setting.this[each.value.setting_id]
  id = "${each.value.zone_id}/${each.value.setting_id}"
}

import {
  for_each = local.import_bot_management

  to = module.cloudflare_zone_config[each.key].cloudflare_bot_management.this
  id = each.value.zone_id
}
