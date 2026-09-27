// Keep generated imports disabled: mock IDs must never trigger Cloudflare API reads in CI.
import_existing_zones = false

domains = {
  "ci-example-one.test" = {
    zone_id = "00000000000000000000000000000001"
  }

  "ci-example-two.test" = {
    zone_id = "00000000000000000000000000000002"
  }
}
