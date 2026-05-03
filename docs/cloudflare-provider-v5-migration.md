# Cloudflare Provider v5 Migration Plan

The Cloudflare Terraform provider is intentionally pinned to `~> 4.52` for the current governance baseline. Provider v5 migration is intentionally deferred because Terraform safety is the priority.

Dependabot should not auto-upgrade `cloudflare/cloudflare` across major versions. A v5 migration is expected to require moving away from `cloudflare_zone_settings_override` toward individual `cloudflare_zone_setting` resources, along with explicit state and address planning.

Future migration work may require `moved` blocks, imports, or other controlled Terraform state migration techniques. Do not run `terraform apply` during a migration spike. Do not use `ci.auto.tfvars` against production or real state; it contains mock values for CI validation only.

## Phased Plan

### Phase 1: Inventory current resources and state addresses

List current Terraform configuration resources and read-only state addresses. Identify all `cloudflare_zone_settings_override` and related Cloudflare resources before making changes.

### Phase 2: Create dedicated migration branch

Use a branch dedicated only to the provider v5 migration. Avoid unrelated cleanup or broad refactors.

### Phase 3: Update provider constraint and lockfile

Update the Cloudflare provider constraint and regenerate the lockfile in the migration branch only.

### Phase 4: Replace deprecated or removed resources

Replace v4-only resources with v5-compatible resources. In particular, evaluate replacing `cloudflare_zone_settings_override` with individual `cloudflare_zone_setting` resources.

### Phase 5: Review moved block/import/state migration requirements

Map old resource addresses to new resource addresses. Decide whether `moved` blocks, imports, or other controlled state migration steps are required. Do not manually edit state files.

### Phase 6: Run safe validation and non-destructive plan using the correct values/state strategy

Run formatting and validation first. Run any plan only with the correct values and state strategy for the environment under review.

Do not use `ci.auto.tfvars` against production or real local state. Any plan using `ci.auto.tfvars` must run only in a safe mock-state/no-real-state context.

### Phase 7: Merge only after clean validation and manual plan review

Merge only after validation passes and the Terraform plan has been manually reviewed for unexpected creates, updates, replacements, or destroys.
