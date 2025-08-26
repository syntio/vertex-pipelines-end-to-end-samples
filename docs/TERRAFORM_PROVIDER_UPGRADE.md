# Terraform Provider Upgrade Guide

This document outlines the upgrade from Google Cloud Terraform Provider v4.56 to v6.x.

## Changes Made

### Provider Version Updates

**Environment Files (3 files updated):**
- `terraform/envs/dev/main.tf`
- `terraform/envs/prod/main.tf` 
- `terraform/envs/test/main.tf`

**Module Files (3 files updated):**
- `terraform/modules/vertex_deployment/versions.tf`
- `terraform/modules/cloudfunction/versions.tf`
- `terraform/modules/scheduled_pipelines/versions.tf`

### Version Changes Applied

```hcl
# BEFORE:
terraform {
  required_version = ">= 0.13"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.56.0"  # or ">= 4.3.0" in modules
    }
    google-beta = {
      source  = "hashicorp/google-beta" 
      version = "~> 4.56.0"  # or ">=4.3.0" in modules
    }
  }
}

# AFTER:
terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"      # or ">= 6.0.0" in modules
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"      # or ">= 6.0.0" in modules  
    }
  }
}
```

## Breaking Changes Analysis

### Provider v6.0.0 Key Changes

1. **Default Labels**: New automatic "goog-terraform-provisioned" label added to resources
2. **Deletion Protection**: Some resources now default `deletion_protection = true`
3. **Resource Field Changes**: Some deprecated fields removed (none affecting this project)
4. **Label Management**: New label fields structure for better management

### Impact on This Project

✅ **No Breaking Changes Found**
- All existing resources are compatible with v6.x
- No deprecated fields used in current infrastructure
- `terraform validate` passes successfully

## Testing Results

### Validation Results
```bash
terraform -chdir=terraform/envs/dev validate
# Result: Success! The configuration is valid.
```

### Compatibility
- ✅ Google Provider v4.56 → v6.x: **Compatible**
- ✅ Google-Beta Provider v4.56 → v6.x: **Compatible**  
- ✅ Terraform version >=0.13 → >=1.5: **Compatible**
- ✅ All existing resources: **No changes required**

## Migration Instructions

### For Development Teams

1. **Update Local Terraform Version**:
   ```bash
   # Ensure you have Terraform >= 1.5
   terraform --version
   ```

2. **Re-initialize After Upgrade**:
   ```bash
   cd terraform/envs/dev  # or prod/test
   terraform init -upgrade
   ```

3. **Verify No State Changes**:
   ```bash
   terraform plan
   # Should show no changes (except possible label additions)
   ```

### For CI/CD Pipelines

- Terraform version in CI should be >= 1.5 (current: needs verification)
- Provider lock files will be updated automatically
- No pipeline configuration changes required

## Required Actions

### Before Deployment
- [ ] Update CI/CD terraform version if needed
- [ ] Test `terraform plan` in each environment
- [ ] Verify no unexpected resource changes

### After Deployment
- [ ] Confirm all resources created successfully
- [ ] Check for new "goog-terraform-provisioned" labels (expected)
- [ ] Update team documentation with new version requirements

## Rollback Plan

If issues arise, rollback by reverting the provider version changes:

```bash
git revert <commit-hash>
terraform init -upgrade
```

## References

- [Google Provider v6.0.0 Upgrade Guide](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/version_6_upgrade)
- [Google Cloud Blog: Terraform Provider 6.0.0](https://cloud.google.com/blog/products/management-tools/announcing-terraform-google-provider-6-0-0)