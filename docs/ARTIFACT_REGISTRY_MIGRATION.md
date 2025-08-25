# Artifact Registry Migration Guide

This document outlines the migration from hardcoded container images to Artifact Registry for ML pipeline components.

## Changes Made

### Terraform Infrastructure

1. **Added Artifact Registry repository** in `terraform/modules/vertex_deployment/main.tf`:
   - Repository ID: `ml-pipeline-containers`
   - Format: Docker
   - Location: Same as project region

2. **Added Secret Manager resources**:
   - `pipeline-config`: General pipeline configuration
   - `model-config`: Model-specific configuration and hyperparameters

3. **Updated IAM permissions**:
   - Added `roles/artifactregistry.reader` to Vertex Pipelines service account
   - Maintained existing `roles/secretmanager.secretAccessor` permission

4. **Added new Terraform outputs**:
   - `artifact_registry_repository_url`: Full URL for pushing/pulling images
   - `pipeline_config_secret_id`: Reference to pipeline configuration secret
   - `model_config_secret_id`: Reference to model configuration secret

### API Dependencies

The following Google Cloud APIs are already enabled in the default service list:
- `artifactregistry.googleapis.com`
- `secretmanager.googleapis.com`

## Migration Steps for Container Images

### Current State
Components currently use hardcoded `python:3.11` base images:
- `components/vertex-components/src/vertex_components/*.py`
- `components/bigquery-components/src/bigquery_components/*.py`

### Next Steps (Future Implementation)
1. **Build custom container images** with pre-installed dependencies
2. **Push images to Artifact Registry** using the repository URL output
3. **Update component decorators** to reference Artifact Registry images:
   ```python
   # Before
   @component(base_image="python:3.11", packages_to_install=["google-cloud-aiplatform"])
   
   # After  
   @component(base_image=f"{artifact_registry_url}/ml-pipeline-base:latest")
   ```

### Container Image References Found
- **Training containers**: `train_container_uri` and `serving_container_uri` in custom_train_job.py
- **Component base images**: All components use `python:3.11`

## Secret Manager Usage

### Available Secrets
- `pipeline-config`: Environment settings, debug mode, batch size
- `model-config`: Hyperparameters, model version

### Usage in Pipeline Code
```python
from google.cloud import secretmanager

client = secretmanager.SecretManagerServiceClient()
config = client.access_secret_version(
    request={"name": f"projects/{project_id}/secrets/pipeline-config/versions/latest"}
)
```

## Testing

Before deployment, run:
```bash
# Test Terraform plan
cd terraform/envs/dev
terraform plan

# Verify all APIs are enabled
gcloud services list --enabled --filter="name:artifactregistry OR name:secretmanager"
```

## Breaking Changes

None - this is an additive change that maintains backward compatibility.