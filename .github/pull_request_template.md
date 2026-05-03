## Summary

Describe the change and why it is needed.

## Type of change

- [ ] Documentation
- [ ] Python automation
- [ ] Terraform configuration
- [ ] CI/CD or governance
- [ ] Security hardening

## Validation checklist

- [ ] python scripts/run_all_checks.py
- [ ] terraform -chdir=terraform fmt -check -recursive
- [ ] terraform -chdir=terraform init -backend=false
- [ ] terraform -chdir=terraform validate

## Terraform safety checklist

- [ ] I did not run `terraform apply`.
- [ ] I did not modify Terraform state files.
- [ ] I did not commit real `.tfvars`, `.env`, state, generated reports, or local artifacts.
- [ ] Any Terraform plan was reviewed as non-destructive before proceeding.

**DO NOT use ci.auto.tfvars against production state. It contains mock data for CI validation only.**

Any Terraform plan using `ci.auto.tfvars` must only be run in a safe mock-state/no-real-state context.

## Security checklist

- [ ] No secrets, credentials, tokens, private keys, or service account material are included.
- [ ] Placeholder values are clearly fake and safe for source control.
- [ ] Secret scanning findings, if any, were reviewed.

## Notes / follow-up

List any operational notes, deferred work, or follow-up checks.
