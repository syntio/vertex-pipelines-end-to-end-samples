# GitHub Actions Deployment Guide

This document outlines the automated deployment pipeline using GitHub Actions for the Vertex AI ML Pipelines project.

## Overview

The GitHub Actions deployment workflow provides:
- **Automated dev deployments** on merge to `develop` branch
- **Manual prod deployments** with approval on releases/tags
- **Secure authentication** via Workload Identity Federation (keyless)
- **Two-environment support** (dev, prod) - optimized for current requirements
- **Infrastructure + Pipeline deployment** in a single workflow

## Architecture

### Authentication Flow
```
GitHub Actions → OIDC Token → Workload Identity Federation → GCP Service Account
```

### Dynamic Resource Naming
To prevent conflicts when multiple repositories deploy to the same project:
- **Workload Identity Pool**: `gh-{repo-initials}-{project-hash}`
- **Example**: `vertex-pipelines-end-to-end-samples` → `gh-vpetes-4d532027c607`
- **Benefits**: Unique per repository, conflict-free, under GCP 32-character limit

### Deployment Triggers
- **Push to develop** → Auto-deploy to dev environment (only for relevant file changes)
- **Release/Tag** → Manual-approve deploy to prod environment  
- **Workflow dispatch** → Manual deploy to dev environment only (production requires release/tag)

### Smart Path-Based Triggers
The workflow only runs when files that affect deployment are changed:

**✅ Will trigger deployment:**
- `terraform/**` - Infrastructure changes
- `pipelines/**` - Pipeline code changes  
- `.github/workflows/**` - Workflow changes
- `components/**` - Custom component changes
- `Makefile` - Build script changes

**❌ Will NOT trigger deployment:**
- `docs/**` - Documentation changes
- `README.md` - Readme changes  
- `*.md` - Any markdown files

This prevents unnecessary deployments and resource usage when only documentation is updated.

## Setup Instructions

### 1. Configure Variables and Deploy Infrastructure

#### Configure Environment Variables

```bash
cd terraform/envs/dev

# Copy and edit configuration
cp dev.tfvars.example dev.tfvars
# Edit dev.tfvars with your values:
# - project_id: Your GCP project ID
# - region: Your preferred GCP region  
# - github_repository_owner: Your GitHub org/username
# - github_repository_name: Your repository name
# - name_prefix: Prefix for resource naming
```

#### Deploy Infrastructure
```bash
# Initialize and deploy
terraform init -backend-config="bucket=YOUR_PROJECT_ID-tfstate"
terraform plan -var-file="dev.tfvars"
terraform apply -var-file="dev.tfvars"
```

### 2. Configure GitHub Repository

#### Required Secrets
Add these secrets to your GitHub repository (`Settings` → `Secrets and variables` → `Actions`):

```bash
# Authentication (get exact values from terraform output)
WORKLOAD_IDENTITY_PROVIDER=projects/304309528954/locations/global/workloadIdentityPools/gh-vpetes-4d532027c607/providers/github-provider
GHA_SERVICE_ACCOUNT=github-actions-deploy@syntio-ai-ops.iam.gserviceaccount.com

# Project Configuration (single project architecture)
PROJECT_ID_DEV=syntio-ai-ops
PROJECT_ID_TEST=syntio-ai-ops
PROJECT_ID_PROD=syntio-ai-ops
REGION=europe-west2
```

**Get these values from terraform output:**
```bash
cd terraform/envs/dev
terraform output
# Look for:
# - github_actions_service_account
# - workload_identity_provider (from module output)
```

**Actual dev.tfvars:**
```hcl
# Copy from dev.tfvars.example and update with your values
project_id = "syntio-ai-ops"
region     = "europe-west2"
github_repository_owner = "syntio"
github_repository_name  = "vertex-pipelines-end-to-end-samples"
name_prefix = "ml-ops-turbo"  # Configurable resource prefix
```

**Current Constraint**: This temporarily uses a single project architecture due to project limitations. 

**Recommended Production Setup**: Separate projects per environment:
```hcl
# Future multi-project configuration
PROJECT_ID_DEV=my-company-ml-dev
PROJECT_ID_TEST=my-company-ml-test  
PROJECT_ID_PROD=my-company-ml-prod
```

**Current single-project workaround**:
- Resources differentiated by environment suffix: `-dev-`, `-test-`, `-prod-`
- Name prefix: `ml-ops-turbo` (configurable)
- Pattern: `{project_id}-{name_prefix}-{environment}-{resource_type}`
- **Migration ready**: Code supports multi-project when constraints are lifted

#### Required Environments
Create GitHub environments (`Settings` → `Environments`):

**Development Environment:**
- Name: `development`
- No protection rules (auto-deploy)

**Test Environment:**
- Name: `test` 
- Optional: Add protection rules

**Production Environment:**
- Name: `production`
- **Required reviewers**: Add team members who can approve prod deployments
- **Restrict pushes**: Only allow `main` branch and tags
- **Wait timer**: Optional delay before deployment

### 3. Terraform State Bucket

Single project architecture uses one state bucket:

```bash
# Create state bucket (already exists for syntio-ai-ops)
gsutil mb gs://syntio-ai-ops-tfstate

# Enable versioning for state protection
gsutil versioning set on gs://syntio-ai-ops-tfstate

# Verify bucket exists
gsutil ls gs://syntio-ai-ops-tfstate/
```

**For new projects**: Replace `syntio-ai-ops` with your project ID in the bucket name.

## Workflow Details

### Pre-deployment Checks
- ✅ Run pre-commit hooks (terraform fmt, python linting, etc.)
- ✅ Determine target environment based on trigger
- ✅ Set project ID and configuration

### Development Deployment (Automatic)
**Trigger:** Push to `develop` branch or test branches (e.g., `ivanv/github-actions-deployment`)

**Steps:**
1. **Pre-checks**: Determine environment and project ID
2. **Authenticate**: Using Workload Identity Federation
3. **Setup**: Install gcloud SDK and Terraform
4. **Deploy Infrastructure**: Execute terraform plan/apply for dev environment
5. **Install Dependencies**: Python packages and pipeline components
6. **Compile Pipelines**: Generate training.json and prediction.json for both tensorflow and xgboost
7. **Upload Assets**: Copy compiled pipelines and training scripts to `gs://PROJECT_ID-pl-assets/`

**What Gets Deployed:**
- ✅ GCP infrastructure (BigQuery datasets, storage buckets, Vertex AI configs)
- ✅ Compiled Kubeflow pipeline definitions
- ✅ Training scripts (`train_tf_model.py`, `train_xgb_model.py`) 
- ✅ Pipeline assets ready for execution

### Production Deployment (Manual + Approval)
**Trigger:** Release/tag creation or workflow dispatch

**Steps:**
1. **Manual approval required** (configured in GitHub environment)
2. Deploy terraform infrastructure (`terraform/envs/prod/`)
3. Compile and upload pipelines with **versioning**
4. Upload to both versioned and `latest/` directories

### Deployment Artifacts

**GCS Structure:**
```
gs://PROJECT_ID-pl-assets/
├── training.json                    # Latest training pipeline
├── prediction.json                  # Latest prediction pipeline  
├── v1.0.0-143022/                 # Versioned release
│   ├── training/
│   └── prediction/
└── latest/                         # Symlink to latest version
    ├── training/
    └── prediction/
```

## Migration from Cloud Build

### Current Cloud Build vs New GitHub Actions

| Feature | Cloud Build | GitHub Actions |
|---------|-------------|----------------|
| Authentication | Service Account Keys | Workload Identity Federation |
| Triggers | Cloud Build Triggers | GitHub Events |
| Approval | Manual Cloud Build | GitHub Environments |
| Versioning | Basic | Advanced (tags + timestamps) |
| Multi-env | Separate triggers | Single workflow |

### Migration Steps

1. **Deploy GitHub Actions setup** (this guide)
2. **Test parallel deployment** to ensure everything works
3. **Update team processes** to use GitHub instead of Cloud Console
4. **Disable Cloud Build triggers** once confident
5. **Remove Cloud Build configurations** (optional)

### Rollback Plan

If issues arise with GitHub Actions:

1. **Re-enable Cloud Build triggers**
2. **Use Cloud Console** for manual deployments  
3. **Debug GitHub Actions** without blocking deployments
4. **Fix and re-test** GitHub Actions workflow

## Deployment Status

### ✅ Successfully Implemented

**Current Status:**
- ✅ **Workflow functional**: Automatic deployment on branch push working
- ✅ **Infrastructure deployment**: Terraform successfully updates GCP resources  
- ✅ **Pipeline compilation**: Both tensorflow and xgboost pipelines compile correctly
- ✅ **Asset upload**: Pipeline files and training scripts uploaded to GCS
- ✅ **Authentication**: Workload Identity Federation working with proper gcloud SDK setup

**Deployed Assets (verified):**
```bash
gs://syntio-ai-ops-tfstate/default.tfstate     # Terraform state
gs://syntio-ai-ops-pl-assets/training/         # Training pipeline + assets
gs://syntio-ai-ops-pl-assets/prediction/       # Prediction pipeline
```

**Key Lessons Learned:**
1. **gcloud SDK required**: `google-github-actions/setup-gcloud@v2` needed for `gsutil` commands
2. **Environment variables preferred**: Using `${{ env.PROJECT_ID_DEV }}` instead of job outputs 
3. **Pipeline paths**: Compiled files are in `pipelines/src/` not `pipelines/`
4. **Component installation**: Custom components installed via `pip install -r requirements.txt`

## Usage Examples

### Deploy to Development
```bash
# Automatic on merge to develop
git checkout develop  
git merge feature/my-changes
git push origin develop
# → Triggers automatic dev deployment

# OR push to test branch (temporary for testing)
git push origin ivanv/github-actions-deployment
# → Also triggers dev deployment
```

### Deploy to Production  
```bash
# Create and push a release tag
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin v1.2.0
# → Creates GitHub release → Triggers prod deployment (with approval)
```

### Manual Deployment
```bash
# Via GitHub UI: Actions → "Deploy Infrastructure and Pipelines" → "Run workflow"
# Select branch and environment (dev only for manual dispatch)
# Production deployments require release/tag triggers
```

### Monitor Deployment
- **GitHub Actions**: https://github.com/syntio/vertex-pipelines-end-to-end-samples/actions
- **GCP Console**: Verify infrastructure in Cloud Console
- **Storage**: `gsutil ls -r gs://syntio-ai-ops-pl-assets/` to see deployed assets  
- **Terraform**: `gsutil ls gs://syntio-ai-ops-tfstate/` to verify state updates

## Troubleshooting

### Common Issues

**Authentication Errors:**
```
ServiceException: 401 Anonymous caller does not have storage.objects.create access
```
- **Root cause**: Missing `google-github-actions/setup-gcloud@v2` step
- **Solution**: The auth action only sets environment variables, gcloud SDK needed for gsutil
- **Fixed**: Added gcloud SDK setup step after authentication in workflow

**GCS Bucket Name Errors:**
```
BadRequestException: 400 Invalid bucket name: '-pl-assets'
```  
- **Root cause**: Job outputs empty, using `needs.pre-checks.outputs.project-id` 
- **Solution**: Use environment variables directly: `${{ env.PROJECT_ID_DEV }}`
- **Fixed**: Replaced all job output dependencies with direct env vars

**Pipeline Compilation Path Errors:**
```
cp: cannot stat 'pipelines/training.json': No such file or directory
```
- **Root cause**: Compiled files are in `pipelines/src/` not `pipelines/`
- **Solution**: Update copy paths to `cp pipelines/src/training.json`
- **Fixed**: Corrected all pipeline asset copy paths in workflow

**Component Compilation Errors:**
```
make: *** No rule to make target 'compile-all-components'
```
- **Root cause**: Missing Makefile target, but components installed via requirements.txt
- **Solution**: Remove redundant compile step, use pip install only
- **Fixed**: Removed unnecessary component compilation, use requirements.txt install

**Terraform Backend Errors:**
```  
Error: Failed to configure backend "gcs"
```
- Ensure GCS state bucket exists: `gsutil ls gs://PROJECT_ID-tfstate`
- Check service account has Storage Admin permissions on bucket
- **Current**: `gsutil iam ch serviceAccount:github-actions@syntio-ai-ops.iam.gserviceaccount.com:roles/storage.objectAdmin gs://syntio-ai-ops-tfstate`

### Debug Commands

```bash
# Check Workload Identity setup (use actual pool name)
gcloud iam workload-identity-pools describe gh-vpetes-4d532027c607 \
  --location=global --project=syntio-ai-ops

# Test authentication locally (for debugging)
gcloud auth print-access-token --impersonate-service-account=github-actions-deploy@syntio-ai-ops.iam.gserviceaccount.com

# Check terraform state
gsutil ls -la gs://syntio-ai-ops-tfstate/

# Verify pipeline assets
gsutil ls -r gs://syntio-ai-ops-ml_ops_turbo-dev-pl-assets/
```

## Security Considerations

### Workload Identity Federation Security
- ✅ **No long-lived keys** stored in GitHub
- ✅ **Repository-specific** access (only this repo can authenticate)
- ✅ **Branch restrictions** (only develop/main/tags)
- ✅ **Short-lived tokens** (expire automatically)

### GitHub Environment Protection
- ✅ **Production approval** required (configured reviewers)
- ✅ **Branch restrictions** (only main/tags can deploy to prod)
- ✅ **Audit trail** (all deployments logged)

### GCP IAM Least Privilege
- ✅ **Minimal required permissions** only
- ✅ **Environment-specific** service accounts
- ✅ **Regular permission reviews** recommended

## Monitoring and Alerts

### GitHub Actions Monitoring
- **Workflow failures** → GitHub notifications
- **Deployment status** → GitHub commit status checks
- **Manual approval pending** → GitHub notifications

### GCP Resource Monitoring  
- **Infrastructure changes** → Cloud Console audit logs
- **Cost monitoring** → Billing alerts on unexpected changes
- **Pipeline execution** → Vertex AI monitoring

## Migration to Multi-Project Architecture

### Current State vs Recommended
| Aspect | Current (Single Project) | Recommended (Multi-Project) |
|--------|--------------------------|----------------------------|
| **Security** | Shared IAM, resources visible across environments | Complete isolation, environment-specific IAM |
| **Cost Control** | Mixed billing, hard to track per environment | Clear cost separation and budgeting |
| **Blast Radius** | Dev issues can affect prod resources | Complete environment isolation |
| **Compliance** | Single audit scope | Environment-specific compliance |

### Migration Steps (When Ready)

1. **Create separate GCP projects**:
   ```bash
   # Create projects
   gcloud projects create my-company-ml-dev
   gcloud projects create my-company-ml-prod
   
   # Enable billing and APIs
   gcloud services enable aiplatform.googleapis.com --project=my-company-ml-dev
   gcloud services enable aiplatform.googleapis.com --project=my-company-ml-prod
   ```

2. **Update tfvars per environment**:
   ```hcl
   # terraform/envs/dev/dev.tfvars
   project_id = "my-company-ml-dev"
   
   # terraform/envs/prod/prod.tfvars  
   project_id = "my-company-ml-prod"
   ```

3. **Update GitHub secrets**:
   ```bash
   PROJECT_ID_DEV=my-company-ml-dev
   PROJECT_ID_PROD=my-company-ml-prod
   ```

4. **Deploy to new projects**:
   ```bash
   # No code changes needed - already supports multi-project!
   terraform init && terraform apply
   ```

### Dynamic WIF Pool Benefits for Multi-Project
- Each environment gets unique pool: `gh-vpetes-{dev-project-hash}`, `gh-vpetes-{prod-project-hash}`
- No conflicts during migration
- Gradual rollout possible (migrate dev first, then prod)

## Next Steps

1. **Test the deployment** in current dev environment  
2. **Set up production approval** workflow with team
3. **Plan multi-project migration** when constraints are lifted
4. **Create runbooks** for common deployment scenarios  
5. **Monitor costs** and optimize resource allocation
6. **Add integration tests** to validate deployments
7. **Set up alerting** for deployment failures
