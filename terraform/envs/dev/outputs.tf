/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

# Vertex Pipelines infrastructure outputs
output "vertex_pipelines_sa_email" {
  value       = module.vertex_deployment.vertex_pipelines_sa_email
  description = "Email of the Vertex Pipelines service account"
}

output "cloudfunction_sa_email" {
  value       = module.vertex_deployment.cloudfunction_sa_email
  description = "Email of the Cloud Function service account"
}

output "pubsub_topic_id" {
  value       = module.vertex_deployment.pubsub_topic_id
  description = "ID of the Pub/Sub topic for triggering pipelines"
}

output "artifact_registry_repository_url" {
  value       = module.vertex_deployment.artifact_registry_repository_url
  description = "URL of the Artifact Registry repository"
}

output "pipeline_config_secret_id" {
  value       = module.vertex_deployment.pipeline_config_secret_id
  description = "ID of the pipeline configuration secret"
}

output "model_config_secret_id" {
  value       = module.vertex_deployment.model_config_secret_id
  description = "ID of the model configuration secret"
}

# GitHub Actions authentication outputs
output "github_actions_workload_identity_provider" {
  value       = module.github_actions_auth.workload_identity_provider
  description = "Workload Identity Provider for GitHub Actions"
  sensitive   = true
}

output "github_actions_service_account" {
  value       = module.github_actions_auth.service_account_email
  description = "Service account email for GitHub Actions"
}

output "github_actions_setup_instructions" {
  value       = module.github_actions_auth.github_actions_setup_instructions
  description = "Instructions for setting up GitHub Actions secrets"
}

output "terraform_backend_bucket" {
  value       = module.github_actions_auth.terraform_backend_bucket
  description = "GCS bucket for terraform state storage"
}